"""
Inventory signals.

Recomputes InventoryItem.current_stock from the StockMovement ledger
whenever a movement is created. Uses .update() to bypass the immutability
guard on InventoryItem.save() that protects unit/sku.
"""
from decimal import Decimal

from django.db.models import Sum
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

from .models import (
    StockMovement, InventoryItem, StockAlert,
    Recipe, RecipeIngredient, RecipeVersion,
)


@receiver(post_save, sender=StockMovement)
def recompute_item_stock(sender, instance, created, **kwargs):
    if not created:
        return  # immutable; should never happen, but be safe.
    item = instance.item
    total = (
        StockMovement.objects.filter(item=item, is_reversed=False)
        .aggregate(total=Sum('quantity'))['total']
        or Decimal('0')
    )
    InventoryItem.objects.filter(pk=item.pk).update(current_stock=total)

    # Inline low-stock check (no Celery dependency for phase 1).
    item.refresh_from_db(fields=['current_stock', 'reorder_level', 'is_active'])
    if not item.is_active:
        return
    if item.reorder_level > 0 and item.current_stock <= item.reorder_level:
        # Don't spam — only one open low_stock alert per item at a time.
        already_open = StockAlert.objects.filter(
            item=item, alert_type=StockAlert.AlertType.LOW_STOCK, is_resolved=False,
        ).exists()
        if not already_open:
            StockAlert.objects.create(
                organization=item.organization,
                location=item.location,
                item=item,
                alert_type=StockAlert.AlertType.LOW_STOCK,
                message=(
                    f"{item.name} is at {item.current_stock} {item.unit} "
                    f"(reorder level: {item.reorder_level} {item.unit})."
                ),
                triggered_at=timezone.now(),
            )
    if item.current_stock < 0:
        already_open = StockAlert.objects.filter(
            item=item, alert_type=StockAlert.AlertType.NEGATIVE_STOCK, is_resolved=False,
        ).exists()
        if not already_open:
            StockAlert.objects.create(
                organization=item.organization,
                location=item.location,
                item=item,
                alert_type=StockAlert.AlertType.NEGATIVE_STOCK,
                message=(
                    f"{item.name} stock has gone negative ({item.current_stock} {item.unit}). "
                    "Investigate and adjust."
                ),
            )

    # Async low-stock follow-up (WhatsApp owner alert). Lazy import so
    # tests that don't have Celery configured don't blow up.
    try:
        from .tasks import check_low_stock_task
        check_low_stock_task.delay(str(item.pk))
    except Exception:
        pass


def _snapshot_recipe(recipe):
    ingredients = list(
        recipe.ingredients.values(
            'item_id', 'item__name', 'quantity', 'unit', 'is_optional',
        )
    )
    # Stringify decimals/UUIDs so the JSON field is portable.
    for ing in ingredients:
        ing['item_id'] = str(ing['item_id'])
        ing['quantity'] = str(ing['quantity'])
    return {
        'ingredients': ingredients,
        'yield_percent': str(recipe.yield_percent),
        'output_quantity': str(recipe.output_quantity),
        'output_item_id': str(recipe.output_item_id) if recipe.output_item_id else None,
    }


@receiver(post_save, sender=RecipeIngredient)
def on_ingredient_save(sender, instance, created, **kwargs):
    _bump_recipe_version(instance.recipe)


@receiver(post_delete, sender=RecipeIngredient)
def on_ingredient_delete(sender, instance, **kwargs):
    # During cascade-delete of a Recipe, instance.recipe may already be gone.
    try:
        recipe = Recipe.objects.get(pk=instance.recipe_id)
    except Recipe.DoesNotExist:
        return
    _bump_recipe_version(recipe)


def _bump_recipe_version(recipe):
    new_version = (recipe.version or 0) + 1
    Recipe.objects.filter(pk=recipe.pk).update(version=new_version)
    recipe.refresh_from_db(fields=['version'])
    RecipeVersion.objects.create(
        recipe=recipe,
        version_number=new_version,
        snapshot=_snapshot_recipe(recipe),
    )
