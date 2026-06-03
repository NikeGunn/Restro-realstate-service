"""Billing API: summary, balance, owner-only limit PATCH, ledger isolation."""
from decimal import Decimal

import pytest

from apps.billing.models import UsageLimit, UsageEvent

pytestmark = pytest.mark.django_db

BASE = '/api/v1/billing'


def test_balance_endpoint(owner_client, org, balance):
    r = owner_client.get(f'{BASE}/balance/', {'organization': str(org.id)})
    assert r.status_code == 200
    assert r.data['free_credits_remaining'] == 5
    assert r.data['total_available'] == 15


def test_summary_endpoint(owner_client, org, balance, limit):
    r = owner_client.get(f'{BASE}/summary/', {'organization': str(org.id)})
    assert r.status_code == 200
    assert r.data['cap_status'] == 'active'
    assert r.data['monthly_ai_spend_cap_hkd'] == '200.0'
    assert 'by_module' in r.data


def test_limit_get(owner_client, org, limit):
    r = owner_client.get(f'{BASE}/limit/', {'organization': str(org.id)})
    assert r.status_code == 200
    assert r.data['alert_at_percent'] == 80


def test_limit_patch_owner_ok(owner_client, org, limit):
    r = owner_client.patch(
        f'{BASE}/limit/?organization={org.id}',
        {'monthly_ai_spend_cap_hkd': '500.00', 'alert_at_percent': 70}, format='json')
    assert r.status_code == 200
    limit.refresh_from_db()
    assert limit.monthly_ai_spend_cap_hkd == Decimal('500.00')
    assert limit.alert_at_percent == 70


def test_limit_patch_manager_forbidden(manager_client, org, limit):
    r = manager_client.patch(
        f'{BASE}/limit/?organization={org.id}',
        {'monthly_ai_spend_cap_hkd': '999.00'}, format='json')
    assert r.status_code == 403
    limit.refresh_from_db()
    assert limit.monthly_ai_spend_cap_hkd == Decimal('200')  # unchanged


def test_usage_events_list_scoped(owner_client, org, balance):
    UsageEvent.objects.create(
        organization=org, module='content_studio', event_type='content_studio_image',
        status='success', credits_used=1, cost_hkd=Decimal('1'))
    r = owner_client.get(f'{BASE}/usage-events/', {'organization': str(org.id)})
    assert r.status_code == 200
    rows = r.data['results'] if isinstance(r.data, dict) else r.data
    assert len(rows) == 1


def test_usage_events_cross_org_isolation(owner_client, org, org_b, owner_b):
    UsageEvent.objects.create(
        organization=org_b, module='content_studio', event_type='x',
        status='success', credits_used=1)
    # owner (of org) asking for org_b → PermissionDenied (not a member).
    r = owner_client.get(f'{BASE}/usage-events/', {'organization': str(org_b.id)})
    assert r.status_code in (403, 404)


def test_outsider_no_membership_403(api_client, outsider, org):
    api_client.force_authenticate(user=outsider)
    r = api_client.get(f'{BASE}/summary/', {'organization': str(org.id)})
    assert r.status_code in (403, 404)


def test_unauthenticated_401(api_client, org):
    r = api_client.get(f'{BASE}/balance/', {'organization': str(org.id)})
    assert r.status_code in (401, 403)
