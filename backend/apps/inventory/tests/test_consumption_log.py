"""Phase 4 — ConsumptionLog: written on consume, append-only, API read-only."""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.inventory.models import ConsumptionLog
from apps.inventory.services.stock_engine import StockEngine

pytestmark = pytest.mark.django_db

LOGS = '/api/v1/inventory/consumption-logs/'


def test_log_row_per_ingredient_on_consume(org, owner, recipe, item, item_b):
    # give the food recipe enough stock first
    from apps.inventory.tests.conftest import _seed_stock
    _seed_stock(item, '100')
    _seed_stock(item_b, '50')
    engine = StockEngine(organization=org, performed_by=owner)
    engine.consume_recipe(recipe, Decimal('1'))
    logs = ConsumptionLog.objects.filter(recipe=recipe)
    assert logs.count() == 2  # one per non-optional ingredient
    for log in logs:
        assert log.organization_id == org.id
        assert log.movement_id is not None
        assert log.quantity_consumed > 0


def test_consumption_log_append_only(org, owner, cocktail):
    engine = StockEngine(organization=org, performed_by=owner)
    engine.consume_recipe(cocktail, Decimal('1'))
    log = ConsumptionLog.objects.filter(recipe=cocktail).first()
    log.quantity_consumed = Decimal('999')
    with pytest.raises(ValidationError):
        log.save()


def test_consumption_log_api_read_only_list(auth_owner_client, org, owner, cocktail):
    engine = StockEngine(organization=org, performed_by=owner)
    engine.consume_recipe(cocktail, Decimal('1'))
    resp = auth_owner_client.get(LOGS)
    assert resp.status_code == 200
    data = resp.json()
    rows = data['results'] if isinstance(data, dict) and 'results' in data else data
    assert len(rows) == 2
    assert rows[0]['consumption_type'] == 'cocktail_serve'


def test_consumption_log_api_post_blocked(auth_owner_client):
    resp = auth_owner_client.post(LOGS, {}, format='json')
    assert resp.status_code == 405  # read-only viewset


def test_consumption_log_filter_by_type(auth_owner_client, org, owner, cocktail, beer_recipe, beer_promo_rule):
    engine = StockEngine(organization=org, performed_by=owner)
    engine.consume_recipe(cocktail, Decimal('1'))  # cocktail_serve
    beer_recipe.linked_promo_rule = beer_promo_rule
    beer_recipe.save()
    engine.consume_recipe(beer_recipe, Decimal('1'))  # promo_sale
    resp = auth_owner_client.get(LOGS, {'consumption_type': 'promo_sale'})
    rows = resp.json()
    rows = rows['results'] if isinstance(rows, dict) and 'results' in rows else rows
    assert len(rows) == 1
    assert rows[0]['consumption_type'] == 'promo_sale'


def test_consumption_log_filter_by_recipe(auth_owner_client, org, owner, cocktail):
    engine = StockEngine(organization=org, performed_by=owner)
    engine.consume_recipe(cocktail, Decimal('1'))
    resp = auth_owner_client.get(LOGS, {'recipe': str(cocktail.id)})
    rows = resp.json()
    rows = rows['results'] if isinstance(rows, dict) and 'results' in rows else rows
    assert all(r['recipe'] == str(cocktail.id) for r in rows)


def test_cross_org_consumption_log_isolation(auth_owner_client, org, owner, cocktail,
                                              org_b, owner_b):
    """An owner sees only their org's logs."""
    engine = StockEngine(organization=org, performed_by=owner)
    engine.consume_recipe(cocktail, Decimal('1'))
    # owner_b should see none of org's logs
    from rest_framework.test import APIClient
    client_b = APIClient()
    client_b.force_authenticate(user=owner_b)
    resp = client_b.get(LOGS)
    data = resp.json()
    rows = data['results'] if isinstance(data, dict) and 'results' in data else data
    assert rows == []
