"""
Inventory signals.

On each StockMovement insert:
  1. Update the per-location LocationStock row (sum of non-reversed
     movements for that item+location).
  2. Recompute InventoryItem.current_stock as the sum of all
     LocationStock rows for the item, so existing queries/serializers
     that read item.current_stock keep working.
  3. Evaluate low-stock / negative-stock alerts at the per-location level.

Uses .update() to bypass the immutability guard on InventoryItem.save()
that protects unit/sku.
"""
from decimal import Decimal

from django.db.models import Sum
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

from .models import (
    StockMovement, InventoryItem, LocationStock, StockAlert,
    Recipe, RecipeIngredient, RecipeVersion,
)


def _project_location_stock(item, location_id):
    """Recompute LocationStock.current_stock for a single (item, location) bucket."""
    total = (
        StockMovement.objects.filter(
            item=item, location_id=location_id, is_reversed=False,
        )
        .aggregate(total=Sum('quantity'))['total']
        or Decimal('0')
    )
    obj, _ = LocationStock.objects.update_or_create(
        item=item,
        location_id=location_id,
        defaults={'current_stock': total},
    )
    return obj


def _recompute_item_aggregate(item):
    """Sum every LocationStock row for the item → InventoryItem.current_stock."""
    total = (
        LocationStock.objects.filter(item=item)
        .aggregate(total=Sum('current_stock'))['total']
        or Decimal('0')
    )
    InventoryItem.objects.filter(pk=item.pk).update(current_stock=total)
    return total


def _emit_alerts_for_bucket(item, location_obj, bucket_stock):
    """
    Emit per-location LOW_STOCK / NEGATIVE_STOCK alerts. Cooldown is
    "one open alert of each type per (item, location)" — same anti-spam
    rule as before, scoped to the location.
    """
    if not item.is_active:
        return
    reorder = item.reorder_level  # per-location override is read by the engine; alerts use item-level for now
    location_id = location_obj.pk if location_obj is not None else None

    if reorder > 0 and bucket_stock <= reorder:
        already_open = StockAlert.objects.filter(
            item=item, location_id=location_id,
            alert_type=StockAlert.AlertType.LOW_STOCK, is_resolved=False,
        ).exists()
        if not already_open:
            StockAlert.objects.create(
                organization=item.organization,
                location=location_obj,
                item=item,
                alert_type=StockAlert.AlertType.LOW_STOCK,
                message=(
                    f"{item.name} is at {bucket_stock} {item.unit} "
                    f"(reorder level: {reorder} {item.unit})"
                    + (f" at {location_obj.name}" if location_obj else "")
                    + "."
                ),
                triggered_at=timezone.now(),
            )

    if bucket_stock < 0:
        already_open = StockAlert.objects.filter(
            item=item, location_id=location_id,
            alert_type=StockAlert.AlertType.NEGATIVE_STOCK, is_resolved=False,
        ).exists()
        if not already_open:
            StockAlert.objects.create(
                organization=item.organization,
                location=location_obj,
                item=item,
                alert_type=StockAlert.AlertType.NEGATIVE_STOCK,
                message=(
                    f"{item.name} stock has gone negative "
                    f"({bucket_stock} {item.unit})"
                    + (f" at {location_obj.name}" if location_obj else "")
                    + ". Investigate and adjust."
                ),
            )


@receiver(post_save, sender=StockMovement)
def recompute_item_stock(sender, instance, created, **kwargs):
    if not created:
        return  # ledger is append-only.

    item = instance.item
    location_id = instance.location_id

    # 1. Per-location projection.
    bucket = _project_location_stock(item, location_id)

    # 2. Org-wide aggregate (back-compat for every existing reader).
    _recompute_item_aggregate(item)

    # 3. Per-location alerts.
    item.refresh_from_db(fields=['current_stock', 'reorder_level', 'is_active', 'unit', 'name'])
    location_obj = instance.location  # Location FK on the movement, may be None
    _emit_alerts_for_bucket(item, location_obj, bucket.current_stock)

    # 4. Async low-stock follow-up (WhatsApp owner alert).
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
