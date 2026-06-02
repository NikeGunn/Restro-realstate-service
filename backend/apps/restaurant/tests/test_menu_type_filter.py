"""Phase 3 — MenuItem type / alcohol / sold-out fields and filters."""
import pytest
from decimal import Decimal

from apps.restaurant.models import MenuItem, MenuItemType

pytestmark = pytest.mark.django_db

ITEMS_URL = '/api/restaurant/items/'


def _ids(resp):
    data = resp.json()
    results = data['results'] if isinstance(data, dict) and 'results' in data else data
    return {row['id'] for row in results}


def test_item_type_defaults_to_food(category):
    item = MenuItem.objects.create(
        category=category, name='Plain', price=Decimal('10.00'))
    assert item.item_type == MenuItemType.FOOD
    assert item.is_alcohol is False
    assert item.sold_out is False


def test_all_item_type_choices_present():
    values = {c[0] for c in MenuItemType.choices}
    assert values == {
        'food', 'drink', 'alcohol', 'cocktail',
        'buffet', 'combo', 'promotion', 'addon',
    }


def test_filter_by_item_type_returns_only_matching(
        owner_client, food_item, beer_item, cocktail_item):
    resp = owner_client.get(ITEMS_URL, {'item_type': 'alcohol'})
    assert resp.status_code == 200
    assert _ids(resp) == {str(beer_item.id)}


def test_filter_by_cocktail_type(owner_client, food_item, beer_item, cocktail_item):
    resp = owner_client.get(ITEMS_URL, {'item_type': 'cocktail'})
    assert _ids(resp) == {str(cocktail_item.id)}


def test_filter_by_food_excludes_alcohol(owner_client, food_item, beer_item):
    resp = owner_client.get(ITEMS_URL, {'item_type': 'food'})
    assert _ids(resp) == {str(food_item.id)}


def test_filter_is_alcohol_true(owner_client, food_item, beer_item, cocktail_item):
    resp = owner_client.get(ITEMS_URL, {'is_alcohol': 'true'})
    assert _ids(resp) == {str(beer_item.id), str(cocktail_item.id)}


def test_filter_is_alcohol_false(owner_client, food_item, beer_item):
    resp = owner_client.get(ITEMS_URL, {'is_alcohol': 'false'})
    assert _ids(resp) == {str(food_item.id)}


def test_filter_sold_out(owner_client, category, food_item):
    sold = MenuItem.objects.create(
        category=category, name='86d Special', price=Decimal('20.00'), sold_out=True)
    resp = owner_client.get(ITEMS_URL, {'sold_out': 'true'})
    assert _ids(resp) == {str(sold.id)}


def test_serializer_exposes_new_fields(owner_client, beer_item):
    resp = owner_client.get(f'{ITEMS_URL}{beer_item.id}/')
    assert resp.status_code == 200
    body = resp.json()
    assert body['item_type'] == 'alcohol'
    assert body['is_alcohol'] is True
    assert body['alcohol_brand'] == 'Heineken'
    assert body['sold_out'] is False


def test_create_item_with_type_and_alcohol(owner_client, org, category):
    payload = {
        'category': str(category.id),
        'name': 'Gin Tonic',
        'price': '88.00',
        'item_type': 'cocktail',
        'is_alcohol': True,
        'alcohol_brand': 'Tanqueray',
    }
    resp = owner_client.post(ITEMS_URL, payload, format='json')
    assert resp.status_code == 201, resp.content
    item = MenuItem.objects.get(name='Gin Tonic')
    assert item.item_type == 'cocktail'
    assert item.is_alcohol is True
    assert item.alcohol_brand == 'Tanqueray'


def test_toggle_sold_out_via_update(owner_client, beer_item):
    resp = owner_client.patch(
        f'{ITEMS_URL}{beer_item.id}/', {'sold_out': True}, format='json')
    assert resp.status_code == 200
    beer_item.refresh_from_db()
    assert beer_item.sold_out is True
