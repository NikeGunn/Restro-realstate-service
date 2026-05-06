"""Tests for StockEngine — adjustments, reversals, PO receipts, recipe consumption."""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.inventory.models import StockMovement, PurchaseOrder
from apps.inventory.services.stock_engine import StockEngine


@pytest.fixture
def engine(org, owner):
    return StockEngine(organization=org, performed_by=owner)


def test_manual_adjustment_creates_movement(engine, item):
    mv = engine.manual_adjustment(
        item, quantity=Decimal('10'), reason='Initial count adjustment',
    )
    assert mv.movement_type == 'adjustment'
    assert mv.quantity == Decimal('10')
    item.refresh_from_db()
    assert item.current_stock == Decimal('10')


def test_manual_adjustment_requires_long_reason(engine, item):
    with pytest.raises(ValidationError):
        engine.manual_adjustment(item, Decimal('5'), reason='ok')


def test_reverse_movement_creates_counter_and_marks_original(engine, org, item):
    mv = StockMovement.objects.create(
        organization=org, item=item,
        movement_type=StockMovement.MovementType.PURCHASE,
        quantity=Decimal('20'),
    )
    item.refresh_from_db()
    assert item.current_stock == Decimal('20')

    reversal = engine.reverse_movement(str(mv.id), reason='Wrong supplier on receipt')
    assert reversal.quantity == Decimal('-20')
    mv.refresh_from_db()
    assert mv.is_reversed is True
    assert mv.reversed_by_id == reversal.id
    item.refresh_from_db()
    assert item.current_stock == Decimal('0')


def test_reverse_movement_idempotent(engine, org, item):
    mv = StockMovement.objects.create(
        organization=org, item=item,
        movement_type=StockMovement.MovementType.PURCHASE,
        quantity=Decimal('5'),
    )
    engine.reverse_movement(str(mv.id), reason='Reverting receipt')
    with pytest.raises(ValidationError):
        engine.reverse_movement(str(mv.id), reason='Trying again')


def test_receive_purchase_order_item_creates_purchase_movement(engine, purchase_order):
    line = purchase_order.items.first()
    mv = engine.receive_purchase_order_item(
        line, quantity_received=Decimal('20'), unit_cost=Decimal('2'),
    )
    assert mv.movement_type == 'purchase'
    assert mv.quantity == Decimal('20')
    line.refresh_from_db()
    assert line.quantity_received == Decimal('20')
    purchase_order.refresh_from_db()
    assert purchase_order.status == PurchaseOrder.Status.RECEIVED


def test_partial_receipt_marks_po_partial(engine, purchase_order):
    line = purchase_order.items.first()
    engine.receive_purchase_order_item(line, quantity_received=Decimal('5'))
    purchase_order.refresh_from_db()
    assert purchase_order.status == PurchaseOrder.Status.PARTIAL


def test_consume_recipe_succeeds_when_sufficient(engine, recipe, item, item_b):
    StockMovement.objects.create(
        organization=item.organization, item=item,
        movement_type=StockMovement.MovementType.PURCHASE,
        quantity=Decimal('100'),
    )
    StockMovement.objects.create(
        organization=item_b.organization, item=item_b,
        movement_type=StockMovement.MovementType.PURCHASE,
        quantity=Decimal('5'),
    )
    result = engine.consume_recipe(recipe, batches=Decimal('10'))
    assert result['movements_created'] == 2
    item.refresh_from_db()
    item_b.refresh_from_db()
    assert item.current_stock == Decimal('80')   # 100 - 2*10
    assert item_b.current_stock == Decimal('4')  # 5 - 0.1*10


def test_consume_recipe_blocks_when_short(engine, recipe, item, item_b):
    StockMovement.objects.create(
        organization=item.organization, item=item,
        movement_type=StockMovement.MovementType.PURCHASE,
        quantity=Decimal('1'),
    )
    StockMovement.objects.create(
        organization=item_b.organization, item=item_b,
        movement_type=StockMovement.MovementType.PURCHASE,
        quantity=Decimal('5'),
    )
    with pytest.raises(ValidationError):
        engine.consume_recipe(recipe, batches=Decimal('10'))


def test_consume_recipe_with_yield_percent_requires_more(engine, org, item, output_item, owner):
    """yield_percent < 100 means more raw input is needed."""
    from apps.inventory.models import Recipe, RecipeIngredient
    r = Recipe.objects.create(
        organization=org, name='Lossy Soup',
        output_item=output_item, output_quantity=Decimal('1'),
        yield_percent=Decimal('80'), created_by=owner,
    )
    RecipeIngredient.objects.create(
        recipe=r, item=item, quantity=Decimal('1'), unit=item.unit,
    )
    StockMovement.objects.create(
        organization=org, item=item,
        movement_type=StockMovement.MovementType.PURCHASE,
        quantity=Decimal('100'),
    )
    engine.consume_recipe(r, batches=Decimal('10'))
    item.refresh_from_db()
    # 1 * 10 / 0.80 = 12.5 consumed
    assert item.current_stock == Decimal('87.5')
