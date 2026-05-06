"""
Tests for inventory models — immutability, signal recompute, alerts.
"""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.accounts.models import Organization
from apps.inventory.models import (
    InventoryItem, StockMovement, StockAlert, InventoryAuditLog,
)


@pytest.fixture
def org(db):
    return Organization.objects.create(
        name="Acme Cafe", business_type=Organization.BusinessType.RESTAURANT,
    )


@pytest.fixture
def item(db, org):
    return InventoryItem.objects.create(
        organization=org,
        name="Tomato",
        unit=InventoryItem.Unit.KG,
        unit_cost=Decimal('2.50'),
        reorder_level=Decimal('10'),
    )


def test_item_auto_generates_sku(item):
    assert item.sku
    assert item.sku.startswith('INV-ACME-')


def test_item_unit_is_immutable(item):
    item.unit = InventoryItem.Unit.G
    with pytest.raises(ValidationError) as exc:
        item.save()
    assert 'unit' in str(exc.value).lower()


def test_item_sku_is_immutable(item):
    original_sku = item.sku
    item.sku = "INV-FAKE-CHANGED"
    with pytest.raises(ValidationError):
        item.save()
    item.refresh_from_db()
    assert item.sku == original_sku


def test_stock_movement_is_append_only(db, org, item):
    mv = StockMovement.objects.create(
        organization=org, item=item,
        movement_type=StockMovement.MovementType.PURCHASE,
        quantity=Decimal('20'),
    )
    mv.notes = "tampering"
    with pytest.raises(ValidationError):
        mv.save()


def test_negative_movement_rejected_for_purchase(db, org, item):
    with pytest.raises(ValidationError):
        StockMovement.objects.create(
            organization=org, item=item,
            movement_type=StockMovement.MovementType.PURCHASE,
            quantity=Decimal('-5'),
        )


def test_positive_movement_rejected_for_sale(db, org, item):
    with pytest.raises(ValidationError):
        StockMovement.objects.create(
            organization=org, item=item,
            movement_type=StockMovement.MovementType.SALE,
            quantity=Decimal('5'),
        )


def test_signal_recomputes_current_stock(db, org, item):
    StockMovement.objects.create(
        organization=org, item=item,
        movement_type=StockMovement.MovementType.PURCHASE,
        quantity=Decimal('100'),
    )
    item.refresh_from_db()
    assert item.current_stock == Decimal('100')

    StockMovement.objects.create(
        organization=org, item=item,
        movement_type=StockMovement.MovementType.SALE,
        quantity=Decimal('-30'),
    )
    item.refresh_from_db()
    assert item.current_stock == Decimal('70')


def test_low_stock_alert_triggers_at_reorder_level(db, org, item):
    StockMovement.objects.create(
        organization=org, item=item,
        movement_type=StockMovement.MovementType.PURCHASE,
        quantity=Decimal('5'),  # below reorder_level (10)
    )
    assert StockAlert.objects.filter(
        item=item,
        alert_type=StockAlert.AlertType.LOW_STOCK,
        is_resolved=False,
    ).exists()


def test_negative_stock_alert(db, org, item):
    StockMovement.objects.create(
        organization=org, item=item,
        movement_type=StockMovement.MovementType.PURCHASE,
        quantity=Decimal('5'),
    )
    StockMovement.objects.create(
        organization=org, item=item,
        movement_type=StockMovement.MovementType.SALE,
        quantity=Decimal('-10'),
    )
    item.refresh_from_db()
    assert item.current_stock == Decimal('-5')
    assert StockAlert.objects.filter(
        item=item,
        alert_type=StockAlert.AlertType.NEGATIVE_STOCK,
        is_resolved=False,
    ).exists()


def test_audit_log_cannot_be_deleted(db, org, item):
    log = InventoryAuditLog.objects.create(
        organization=org,
        action='create',
        model_name='InventoryItem',
        object_id=item.id,
        object_repr=str(item),
    )
    with pytest.raises(ValidationError):
        log.delete()
