"""Phase 4 — promo-rule inventory deduction (Happy Hour 1+1)."""
from decimal import Decimal

import pytest

from apps.inventory.models import ConsumptionLog, StockMovement
from apps.inventory.services.stock_engine import StockEngine

pytestmark = pytest.mark.django_db


def test_no_promo_rule_multiplier_is_one(org, owner, beer_recipe, beer):
    engine = StockEngine(organization=org, performed_by=owner)
    result = engine.consume_recipe(beer_recipe, Decimal('1'))
    beer.refresh_from_db()
    assert result['deduction_multiplier'] == '1'
    assert beer.current_stock == Decimal('100') - Decimal('1')


def test_promo_rule_doubles_deduction(org, owner, beer_recipe, beer, beer_promo_rule):
    """1+1: inventory_deduction_multiplier=2 → 1 serve deducts 2 units."""
    beer_recipe.linked_promo_rule = beer_promo_rule
    beer_recipe.save()
    engine = StockEngine(organization=org, performed_by=owner)
    result = engine.consume_recipe(beer_recipe, Decimal('1'))
    beer.refresh_from_db()
    assert result['deduction_multiplier'] == '2.00'
    assert beer.current_stock == Decimal('100') - Decimal('2')


def test_promo_deduction_scales_with_batches(org, owner, beer_recipe, beer, beer_promo_rule):
    beer_recipe.linked_promo_rule = beer_promo_rule
    beer_recipe.save()
    engine = StockEngine(organization=org, performed_by=owner)
    engine.consume_recipe(beer_recipe, Decimal('3'))
    beer.refresh_from_db()
    # 1 unit/serve × 3 batches × 2 multiplier = 6
    assert beer.current_stock == Decimal('100') - Decimal('6')


def test_promo_consume_logs_promo_sale_type(org, owner, beer_recipe, beer, beer_promo_rule):
    beer_recipe.linked_promo_rule = beer_promo_rule
    beer_recipe.save()
    engine = StockEngine(organization=org, performed_by=owner)
    engine.consume_recipe(beer_recipe, Decimal('1'))
    log = ConsumptionLog.objects.filter(recipe=beer_recipe).latest('created_at')
    assert log.consumption_type == ConsumptionLog.ConsumptionType.PROMO_SALE
    # quantity logged is the post-multiplier deducted amount
    assert log.quantity_consumed == Decimal('2.0000')


def test_promo_movement_quantity_reflects_multiplier(org, owner, beer_recipe, beer, beer_promo_rule):
    beer_recipe.linked_promo_rule = beer_promo_rule
    beer_recipe.save()
    engine = StockEngine(organization=org, performed_by=owner)
    engine.consume_recipe(beer_recipe, Decimal('1'))
    mv = StockMovement.objects.filter(
        item=beer, movement_type=StockMovement.MovementType.RECIPE_CONSUMPTION,
    ).latest('created_at')
    assert mv.quantity == Decimal('-2.0000')
