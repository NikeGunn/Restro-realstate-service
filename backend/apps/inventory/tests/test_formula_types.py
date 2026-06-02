"""Phase 4 — formula_type API filter, serializer fields, unit validity."""
from decimal import Decimal

import pytest

from apps.inventory.models import InventoryItem, RecipeIngredient

pytestmark = pytest.mark.django_db

RECIPES = '/api/v1/inventory/recipes/'


def _results(resp):
    data = resp.json()
    return data['results'] if isinstance(data, dict) and 'results' in data else data


def test_filter_by_formula_type(auth_owner_client, recipe, cocktail):
    resp = auth_owner_client.get(RECIPES, {'formula_type': 'cocktail_formula'})
    assert resp.status_code == 200
    ids = {r['id'] for r in _results(resp)}
    assert str(cocktail.id) in ids
    assert str(recipe.id) not in ids


def test_filter_by_food_recipe(auth_owner_client, recipe, cocktail):
    resp = auth_owner_client.get(RECIPES, {'formula_type': 'food_recipe'})
    ids = {r['id'] for r in _results(resp)}
    assert str(recipe.id) in ids
    assert str(cocktail.id) not in ids


def test_serializer_exposes_formula_fields(auth_owner_client, cocktail):
    resp = auth_owner_client.get(f'{RECIPES}{cocktail.id}/')
    assert resp.status_code == 200
    body = resp.json()
    assert body['formula_type'] == 'cocktail_formula'
    assert body['serving_ml'] == '60.00'
    assert body['pour_variance_percent'] == '5.00'
    assert body['effective_pour_variance_percent'] == '5.00'


def test_effective_variance_falls_back_to_default(auth_owner_client, org, owner, vodka):
    from apps.inventory.models import Recipe
    r = Recipe.objects.create(
        organization=org, name='No-override cocktail',
        formula_type=Recipe.FormulaType.COCKTAIL_FORMULA,
        yield_percent=Decimal('100'), created_by=owner,
    )
    RecipeIngredient.objects.create(
        recipe=r, item=vodka, quantity=Decimal('45'), unit=vodka.unit,
    )
    resp = auth_owner_client.get(f'{RECIPES}{r.id}/')
    body = resp.json()
    assert body['pour_variance_percent'] is None
    assert body['effective_pour_variance_percent'] == '5.0'


def test_create_cocktail_recipe_via_api(auth_owner_client, org, vodka, lime_juice):
    payload = {
        'organization': str(org.id),
        'name': 'API Cocktail',
        'formula_type': 'cocktail_formula',
        'serving_ml': '130.00',
        'pour_variance_percent': '7.50',
        'yield_percent': '100',
        'ingredients': [
            {'item': str(vodka.id), 'quantity': '45'},
            {'item': str(lime_juice.id), 'quantity': '15'},
        ],
    }
    resp = auth_owner_client.post(RECIPES, payload, format='json')
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body['formula_type'] == 'cocktail_formula'
    assert body['effective_pour_variance_percent'] == '7.50'


def test_ml_cl_fl_oz_items_creatable(auth_owner_client, org):
    for unit in ('ml', 'cl', 'fl_oz'):
        resp = auth_owner_client.post('/api/v1/inventory/items/', {
            'organization': str(org.id),
            'name': f'Liquid {unit}',
            'unit': unit,
            'unit_cost': '0.10',
        }, format='json')
        assert resp.status_code == 201, resp.content
        assert resp.json()['unit'] == unit


def test_cl_fl_oz_are_valid_choices():
    valid = {c[0] for c in InventoryItem.Unit.choices}
    assert {'cl', 'fl_oz'} <= valid


def test_linked_promo_rule_label_in_serializer(auth_owner_client, beer_recipe, beer_promo_rule):
    beer_recipe.linked_promo_rule = beer_promo_rule
    beer_recipe.save()
    resp = auth_owner_client.get(f'{RECIPES}{beer_recipe.id}/')
    body = resp.json()
    assert body['linked_promo_rule'] == str(beer_promo_rule.id)
    assert 'Happy Hour Beer' in body['linked_promo_rule_label']
