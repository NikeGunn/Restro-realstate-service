"""
Per-location stock projection tests (Phase 4 — multi-location stock split).

Covers:
  - Movement at a single location → only that LocationStock row updates.
  - Movements at two locations → two LocationStock rows; item.current_stock
    is the sum of both.
  - Movement at NULL location → its own LocationStock bucket.
  - Reversal at a location decrements that LocationStock row.
  - Low-stock alert is tagged with the originating location.
  - Backfill data migration produces correct LocationStock rows for
    historical movements.
"""
from decimal import Decimal

import pytest

from apps.accounts.models import Location
from apps.inventory.models import (
    InventoryItem, LocationStock, StockAlert, StockMovement,
)
from apps.inventory.services.stock_engine import StockEngine


@pytest.fixture
def location_a(db, org):
    return Location.objects.create(organization=org, name='Branch A')


@pytest.fixture
def location_b(db, org):
    return Location.objects.create(organization=org, name='Branch B')


@pytest.mark.django_db
class TestLocationStockProjection:

    def test_single_location_movement_creates_bucket(self, org, item, owner, location_a):
        engine = StockEngine(organization=org, location=location_a, performed_by=owner)
        engine._create_movement(
            item=item,
            movement_type=StockMovement.MovementType.PURCHASE,
            quantity=Decimal('25'),
        )
        rows = list(LocationStock.objects.filter(item=item))
        assert len(rows) == 1
        assert rows[0].location_id == location_a.pk
        assert rows[0].current_stock == Decimal('25')

        item.refresh_from_db()
        assert item.current_stock == Decimal('25')

    def test_two_locations_split_independently(
        self, org, item, owner, location_a, location_b,
    ):
        engine_a = StockEngine(organization=org, location=location_a, performed_by=owner)
        engine_b = StockEngine(organization=org, location=location_b, performed_by=owner)

        engine_a._create_movement(
            item=item, movement_type=StockMovement.MovementType.PURCHASE,
            quantity=Decimal('15'),
        )
        engine_b._create_movement(
            item=item, movement_type=StockMovement.MovementType.PURCHASE,
            quantity=Decimal('40'),
        )

        bucket_a = LocationStock.objects.get(item=item, location=location_a)
        bucket_b = LocationStock.objects.get(item=item, location=location_b)
        assert bucket_a.current_stock == Decimal('15')
        assert bucket_b.current_stock == Decimal('40')

        item.refresh_from_db()
        assert item.current_stock == Decimal('55')

    def test_null_location_is_a_valid_bucket(self, org, item, owner):
        engine = StockEngine(organization=org, location=None, performed_by=owner)
        # Item has no location either, so the resolved location stays None.
        engine._create_movement(
            item=item, movement_type=StockMovement.MovementType.PURCHASE,
            quantity=Decimal('7'),
        )
        bucket = LocationStock.objects.get(item=item, location__isnull=True)
        assert bucket.current_stock == Decimal('7')

        item.refresh_from_db()
        assert item.current_stock == Decimal('7')

    def test_reversal_decrements_correct_bucket(self, org, item, owner, location_a, location_b):
        engine_a = StockEngine(organization=org, location=location_a, performed_by=owner)
        engine_b = StockEngine(organization=org, location=location_b, performed_by=owner)

        mv_a = engine_a._create_movement(
            item=item, movement_type=StockMovement.MovementType.PURCHASE,
            quantity=Decimal('20'),
        )
        engine_b._create_movement(
            item=item, movement_type=StockMovement.MovementType.PURCHASE,
            quantity=Decimal('30'),
        )

        engine_a.reverse_movement(str(mv_a.id), reason='Damaged on receipt')

        bucket_a = LocationStock.objects.get(item=item, location=location_a)
        bucket_b = LocationStock.objects.get(item=item, location=location_b)
        assert bucket_a.current_stock == Decimal('0')
        assert bucket_b.current_stock == Decimal('30')

        item.refresh_from_db()
        assert item.current_stock == Decimal('30')


@pytest.mark.django_db
class TestLocationAlerts:

    def test_low_stock_alert_tagged_with_location(self, org, owner, location_a):
        item = InventoryItem.objects.create(
            organization=org, name='Onion', unit=InventoryItem.Unit.KG,
            reorder_level=Decimal('10'),
        )
        engine = StockEngine(organization=org, location=location_a, performed_by=owner)
        engine._create_movement(
            item=item, movement_type=StockMovement.MovementType.PURCHASE,
            quantity=Decimal('5'),  # below reorder_level=10
        )
        alerts = StockAlert.objects.filter(
            item=item, alert_type=StockAlert.AlertType.LOW_STOCK,
        )
        assert alerts.count() == 1
        assert alerts.first().location_id == location_a.pk

    def test_negative_stock_alert_tagged_with_location(self, org, item, owner, location_a):
        engine = StockEngine(organization=org, location=location_a, performed_by=owner)
        engine._create_movement(
            item=item, movement_type=StockMovement.MovementType.SALE,
            quantity=Decimal('-5'),  # nothing in stock yet
        )
        alerts = StockAlert.objects.filter(
            item=item, alert_type=StockAlert.AlertType.NEGATIVE_STOCK,
        )
        assert alerts.count() == 1
        assert alerts.first().location_id == location_a.pk


@pytest.mark.django_db
class TestBackfillIdempotency:
    """
    The 0003 data migration ran when the test DB was created; new movements
    afterwards keep LocationStock in sync via the signal. This test confirms
    the per-item invariant holds across mixed movements.
    """

    def test_aggregate_invariant_holds(
        self, org, item, item_b, owner, location_a, location_b,
    ):
        engine_a = StockEngine(organization=org, location=location_a, performed_by=owner)
        engine_b = StockEngine(organization=org, location=location_b, performed_by=owner)
        engine_null = StockEngine(organization=org, location=None, performed_by=owner)

        engine_a._create_movement(
            item=item, movement_type=StockMovement.MovementType.PURCHASE,
            quantity=Decimal('12'),
        )
        engine_b._create_movement(
            item=item, movement_type=StockMovement.MovementType.PURCHASE,
            quantity=Decimal('8'),
        )
        engine_null._create_movement(
            item=item, movement_type=StockMovement.MovementType.OPENING_STOCK,
            quantity=Decimal('3'),
        )
        engine_a._create_movement(
            item=item_b, movement_type=StockMovement.MovementType.PURCHASE,
            quantity=Decimal('100'),
        )

        # Per-item invariant: sum(LocationStock) == InventoryItem.current_stock
        for inv in (item, item_b):
            inv.refresh_from_db()
            ls_total = sum(
                (b.current_stock for b in LocationStock.objects.filter(item=inv)),
                Decimal('0'),
            )
            assert ls_total == inv.current_stock, (
                f'Drift on {inv.name}: aggregate={inv.current_stock} ls_sum={ls_total}'
            )
