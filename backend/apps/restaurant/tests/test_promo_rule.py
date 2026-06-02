"""Phase 3 — MenuPromoRule model + API (org auto-derive, multipliers, 1+1)."""
import pytest
from decimal import Decimal

from apps.restaurant.models import MenuPromoRule, MenuItem

pytestmark = pytest.mark.django_db


def _nested_url(item_id):
    return f'/api/restaurant/items/{item_id}/promo-rule/'


def _flat_url():
    return '/api/restaurant/promo-rules/'


# ---- model-level ----

def test_org_auto_set_from_category_on_save(org, beer_item):
    rule = MenuPromoRule.objects.create(
        menu_item=beer_item, promo_type=MenuPromoRule.PromoType.HAPPY_HOUR,
    )
    assert rule.organization_id == org.id


def test_happy_hour_1_plus_1_multipliers(org, beer_item):
    rule = MenuPromoRule.objects.create(
        menu_item=beer_item,
        promo_type=MenuPromoRule.PromoType.HAPPY_HOUR,
        sales_quantity_multiplier=Decimal('1.00'),
        revenue_multiplier=Decimal('1.00'),
        inventory_deduction_multiplier=Decimal('2.00'),
    )
    assert rule.sales_quantity_multiplier == Decimal('1.00')
    assert rule.revenue_multiplier == Decimal('1.00')
    assert rule.inventory_deduction_multiplier == Decimal('2.00')


def test_multipliers_default_to_one(org, food_item):
    rule = MenuPromoRule.objects.create(
        menu_item=food_item, promo_type=MenuPromoRule.PromoType.COMBO)
    assert rule.sales_quantity_multiplier == Decimal('1.00')
    assert rule.revenue_multiplier == Decimal('1.00')
    assert rule.inventory_deduction_multiplier == Decimal('1.00')


def test_one_to_one_per_item(org, beer_item):
    MenuPromoRule.objects.create(
        menu_item=beer_item, promo_type=MenuPromoRule.PromoType.HAPPY_HOUR)
    with pytest.raises(Exception):
        MenuPromoRule.objects.create(
            menu_item=beer_item, promo_type=MenuPromoRule.PromoType.COMBO)


# ---- API-level ----

def test_create_promo_rule_nested(owner_client, org, beer_item):
    payload = {
        'promo_type': 'happy_hour',
        'sales_quantity_multiplier': '1.00',
        'revenue_multiplier': '1.00',
        'inventory_deduction_multiplier': '2.00',
    }
    resp = owner_client.post(_nested_url(beer_item.id), payload, format='json')
    assert resp.status_code == 201, resp.content
    body = resp.json()
    # org is denormalized + read-only, set from the item's category
    assert body['organization'] == str(org.id)
    assert body['inventory_deduction_multiplier'] == '2.00'


def test_create_promo_rule_flat(owner_client, org, beer_item):
    payload = {
        'menu_item': str(beer_item.id),
        'promo_type': 'staff_discount',
    }
    resp = owner_client.post(_flat_url(), payload, format='json')
    assert resp.status_code == 201, resp.content
    assert resp.json()['organization'] == str(org.id)


def test_multipliers_round_trip_via_api(owner_client, beer_item):
    owner_client.post(_nested_url(beer_item.id), {
        'promo_type': 'happy_hour',
        'inventory_deduction_multiplier': '2.00',
    }, format='json')
    resp = owner_client.get(_nested_url(beer_item.id))
    data = resp.json()
    rows = data['results'] if isinstance(data, dict) and 'results' in data else data
    assert rows[0]['inventory_deduction_multiplier'] == '2.00'


def test_linked_menu_items_m2m(owner_client, org, beer_item, food_item):
    payload = {
        'menu_item': str(beer_item.id),
        'promo_type': 'combo',
        'linked_menu_items': [str(food_item.id)],
    }
    resp = owner_client.post(_flat_url(), payload, format='json')
    assert resp.status_code == 201, resp.content
    assert str(food_item.id) in resp.json()['linked_menu_items']


def test_manager_can_read_but_not_create(manager_client, beer_item):
    # manager read is allowed
    resp = manager_client.get(_flat_url())
    assert resp.status_code == 200
    # manager write is rejected (owner-only)
    resp = manager_client.post(_nested_url(beer_item.id), {
        'promo_type': 'happy_hour'}, format='json')
    assert resp.status_code == 403


def test_cross_org_item_create_rejected(owner_client, beer_item, category_b, org_b):
    # owner of org tries to attach a rule to org_b's item → not owner of org_b
    other_item = MenuItem.objects.create(
        category=category_b, name='Foreign Beer', price=Decimal('40.00'))
    resp = owner_client.post(_nested_url(other_item.id), {
        'promo_type': 'happy_hour'}, format='json')
    assert resp.status_code in (403, 404)
    assert not MenuPromoRule.objects.filter(menu_item=other_item).exists()


def test_cross_org_list_isolation(owner_client, beer_item, category_b, org_b):
    MenuPromoRule.objects.create(
        menu_item=beer_item, promo_type=MenuPromoRule.PromoType.HAPPY_HOUR)
    other_item = MenuItem.objects.create(
        category=category_b, name='Foreign Beer', price=Decimal('40.00'))
    foreign = MenuPromoRule.objects.create(
        menu_item=other_item, promo_type=MenuPromoRule.PromoType.COMBO)
    resp = owner_client.get(_flat_url())
    data = resp.json()
    rows = data['results'] if isinstance(data, dict) and 'results' in data else data
    ids = {r['id'] for r in rows}
    assert str(foreign.id) not in ids


def test_outsider_gets_no_access(api_client, outsider, beer_item):
    api_client.force_authenticate(user=outsider)
    resp = api_client.post(_nested_url(beer_item.id), {
        'promo_type': 'happy_hour'}, format='json')
    assert resp.status_code == 403


def test_linked_item_cross_org_rejected(owner_client, beer_item, category_b, org_b):
    foreign_item = MenuItem.objects.create(
        category=category_b, name='Foreign Side', price=Decimal('15.00'))
    payload = {
        'menu_item': str(beer_item.id),
        'promo_type': 'combo',
        'linked_menu_items': [str(foreign_item.id)],
    }
    resp = owner_client.post(_flat_url(), payload, format='json')
    assert resp.status_code == 400
