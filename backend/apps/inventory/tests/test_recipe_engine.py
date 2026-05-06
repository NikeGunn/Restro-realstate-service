"""Tests for RecipeEngine — calculate, suggest_batches, version_diff."""
from decimal import Decimal

import pytest

from apps.inventory.models import StockMovement, RecipeIngredient
from apps.inventory.services.recipe_engine import RecipeEngine


def _stock_in(org, item, qty):
    StockMovement.objects.create(
        organization=org, item=item,
        movement_type=StockMovement.MovementType.PURCHASE,
        quantity=Decimal(qty),
    )


def test_calculate_batch_basic(recipe, org, item, item_b):
    _stock_in(org, item, '100')
    _stock_in(org, item_b, '5')
    out = RecipeEngine.calculate_batch(recipe, batches=Decimal('10'))
    assert out['feasible'] is True
    assert out['shortfalls'] == []
    assert out['recipe_name'] == 'Tomato Soup'
    assert len(out['ingredients']) == 2


def test_calculate_batch_yield_inflates_required(org, item, output_item, owner):
    from apps.inventory.models import Recipe
    r = Recipe.objects.create(
        organization=org, name='Lossy', output_item=output_item,
        output_quantity=Decimal('1'), yield_percent=Decimal('80'),
        created_by=owner,
    )
    RecipeIngredient.objects.create(
        recipe=r, item=item, quantity=Decimal('1'), unit=item.unit,
    )
    _stock_in(org, item, '100')
    out = RecipeEngine.calculate_batch(r, batches=Decimal('10'))
    # 1 * 10 / 0.80 = 12.5
    assert Decimal(out['ingredients'][0]['required_quantity']) == Decimal('12.5')


def test_suggest_batches_returns_zero_when_no_stock(recipe):
    assert RecipeEngine.suggest_batches(recipe) == Decimal('0')


def test_suggest_batches_limited_by_scarcest_ingredient(recipe, org, item, item_b):
    _stock_in(org, item, '100')   # at 2 per batch → up to 50
    _stock_in(org, item_b, '0.5')  # at 0.1 per batch → up to 5 (limiting)
    n = RecipeEngine.suggest_batches(recipe)
    # tolerance lower bound on 0.5 with 0.5% = 0.4975 → 0.4975 / 0.1 ~= 4.97
    assert n > Decimal('4')
    assert n < Decimal('6')


def test_cost_of_batch(recipe, org, item, item_b):
    cost = RecipeEngine.cost_of_batch(recipe, batches=Decimal('5'))
    # item: 2*5=10 @ 2.50 = 25; item_b: 0.1*5=0.5 @ 0.80 = 0.4 → 25.40
    assert cost == Decimal('25.4000')


def test_version_diff_after_ingredient_change(recipe, org, item):
    """Adding an ingredient should produce a new version with diff entries."""
    from apps.inventory.models import InventoryItem, RecipeVersion
    new_item = InventoryItem.objects.create(
        organization=org, name='Pepper', unit=InventoryItem.Unit.G,
    )
    v_before = recipe.versions.count()
    RecipeIngredient.objects.create(
        recipe=recipe, item=new_item, quantity=Decimal('5'), unit=new_item.unit,
    )
    recipe.refresh_from_db()
    assert recipe.versions.count() > v_before
    versions = list(recipe.versions.order_by('version_number').values_list('version_number', flat=True))
    diff = RecipeEngine.version_diff(recipe, versions[0], versions[-1])
    assert isinstance(diff['added'], list)
    assert isinstance(diff['removed'], list)
    assert isinstance(diff['changed'], list)
