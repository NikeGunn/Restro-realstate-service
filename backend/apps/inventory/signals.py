"""
Inventory signals.

Recomputes InventoryItem.current_stock from the StockMovement ledger
whenever a movement is created. Uses .update() to bypass the immutability
guard on InventoryItem.save() that protects unit/sku.
"""
from decimal import Decimal

from django.db.models import Sum
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import StockMovement, InventoryItem, StockAlert


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
