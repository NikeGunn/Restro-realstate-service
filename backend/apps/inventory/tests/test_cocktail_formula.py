"""Phase 4 — cocktail/drink ml formulas, pour variance, 4-dp quantization."""
from decimal import Decimal

import pytest

from apps.inventory.models import Recipe, ConsumptionLog, StockMovement, InventoryItem
from apps.inventory.services.stock_engine import StockEngine
from apps.inventory.services.tolerance_engine import ToleranceEngine

pytestmark = pytest.mark.django_db


def test_cocktail_ml_deduction(org, owner, cocktail, vodka, lime_juice):
    engine = StockEngine(organization=org, performed_by=owner)
    engine.consume_recipe(cocktail, Decimal('1'))
    vodka.refresh_from_db()
    lime_juice.refresh_from_db()
    # 45 ml vodka + 15 ml lime, yield 100%, multiplier 1
    assert vodka.current_stock == Decimal('5000') - Decimal('45')
    assert lime_juice.current_stock == Decimal('2000') - Decimal('15')


def test_pour_variance_applied_for_cocktail(cocktail, vodka):
    """For a cocktail formula, the recipe pour variance (5%) replaces the
    item's own tolerance (0.5%)."""
    es = ToleranceEngine.effective_stock_with_pour_variance(
        raw_stock=vodka.current_stock,
        reorder_level=vodka.reorder_level,
        item_tolerance_percent=vodka.tolerance_percent,
        formula_type=cocktail.formula_type,
        pour_variance_percent=cocktail.resolved_pour_variance_percent(),
    )
    assert es.tolerance_percent == Decimal('5.0')


def test_pour_variance_NOT_applied_for_food(recipe, item):
    """A food recipe keeps the item's own tolerance, never pour variance."""
    es = ToleranceEngine.effective_stock_with_pour_variance(
        raw_stock=Decimal('100'),
        reorder_level=item.reorder_level,
        item_tolerance_percent=item.tolerance_percent,
        formula_type=recipe.formula_type,  # food_recipe
        pour_variance_percent=Decimal('5.0'),
    )
    assert es.tolerance_percent == Decimal('0.5')


def test_resolved_variance_uses_settings_default_when_unset(org, owner, vodka, lime_juice):
    r = Recipe.objects.create(
        organization=org, name='Default-variance cocktail',
        formula_type=Recipe.FormulaType.COCKTAIL_FORMULA,
        yield_percent=Decimal('100'), created_by=owner,
    )
    # No explicit pour_variance_percent → falls back to settings default (5.0).
    assert r.resolved_pour_variance_percent() == Decimal('5.0')


def test_resolved_variance_none_for_food(recipe):
    assert recipe.resolved_pour_variance_percent() is None


def test_brand_specific_item_enforced(cocktail, vodka):
    """Ingredient points to a specific branded item, not a generic name."""
    ing = cocktail.ingredients.get(item=vodka)
    assert ing.item.name == 'Absolut Vodka'
    assert ing.item_id == vodka.id


def test_four_dp_quantization_on_consume(org, owner, vodka, lime_juice):
    """A 33.33% yield forces fractional required quantities; the persisted
    movement must be quantized to 4 dp (StockMovement.quantity is 4 dp)."""
    r = Recipe.objects.create(
        organization=org, name='Odd cocktail',
        formula_type=Recipe.FormulaType.COCKTAIL_FORMULA,
        yield_percent=Decimal('33.33'), created_by=owner,
    )
    from apps.inventory.models import RecipeIngredient
    RecipeIngredient.objects.create(
        recipe=r, item=vodka, quantity=Decimal('10'), unit=vodka.unit,
    )
    engine = StockEngine(organization=org, performed_by=owner)
    engine.consume_recipe(r, Decimal('1'))
    mv = StockMovement.objects.filter(
        item=vodka, movement_type=StockMovement.MovementType.RECIPE_CONSUMPTION,
    ).latest('created_at')
    # 10 / 0.3333 = 30.0030003... → quantized to 4 dp
    assert mv.quantity == Decimal('-30.0030')


def test_consume_writes_consumption_log_cocktail_serve(org, owner, cocktail):
    engine = StockEngine(organization=org, performed_by=owner)
    engine.consume_recipe(cocktail, Decimal('1'))
    logs = ConsumptionLog.objects.filter(recipe=cocktail)
    assert logs.count() == 2  # one per non-optional ingredient
    assert all(
        log.consumption_type == ConsumptionLog.ConsumptionType.COCKTAIL_SERVE
        for log in logs
    )


def test_cl_and_fl_oz_units_available():
    values = {c[0] for c in InventoryItem.Unit.choices}
    assert 'cl' in values
    assert 'fl_oz' in values
    assert 'ml' in values  # unchanged
