"""
Payment security — worst-case coverage.

- No secret keys leak in any response.
- Webhook rejects missing / empty / forged signatures (sig verify replaces CSRF).
- Checkout is owner-only + member-only; cross-org → 404.
- Refund is owner-only.
- Input validation: bad UUID, SQL/XSS in path, unknown pack.
- Error responses carry no tracebacks / internal detail.
"""
import json

import pytest

pytestmark = pytest.mark.django_db

BASE = '/api/v1/payments'


# ── secret-key protection ────────────────────────────────────────────────
def test_config_returns_only_publishable_key(owner_client):
    r = owner_client.get(f'{BASE}/config/')
    body = json.dumps(r.data)
    assert 'pk_test' in body
    assert 'sk_test' not in body
    assert 'whsec_' not in body


def test_checkout_error_has_no_internal_details(owner_client, org):
    # Unknown pack → clean 404, no traceback/stack/keys.
    r = owner_client.post(f'{BASE}/checkout/', {
        'organization': str(org.id),
        'pack': '00000000-0000-0000-0000-000000000000',
    }, format='json')
    body = json.dumps(r.data).lower()
    assert 'traceback' not in body and 'sk_test' not in body and 'stack' not in body


# ── webhook signature (replaces CSRF) ──────────────────────────────────────
def test_webhook_no_signature_rejected(api_client):
    r = api_client.post(f'{BASE}/webhook/', data=b'{"x":1}',
                        content_type='application/json')
    assert r.status_code == 400


def test_webhook_empty_signature_rejected(api_client):
    r = api_client.post(f'{BASE}/webhook/', data=b'{"x":1}',
                        content_type='application/json', HTTP_STRIPE_SIGNATURE='')
    assert r.status_code == 400


def test_webhook_forged_signature_rejected(api_client):
    r = api_client.post(f'{BASE}/webhook/', data=b'{"x":1}',
                        content_type='application/json',
                        HTTP_STRIPE_SIGNATURE='t=1,v1=forged')
    assert r.status_code == 400


def test_webhook_csrf_exempt_not_403(api_client):
    # With a (bad) signature present we expect 400, never 403 (CSRF).
    api_client.handler.enforce_csrf_checks = True
    r = api_client.post(f'{BASE}/webhook/', data=b'{"x":1}',
                        content_type='application/json',
                        HTTP_STRIPE_SIGNATURE='t=1,v1=x')
    assert r.status_code == 400


# ── checkout access control ────────────────────────────────────────────────
def test_checkout_requires_auth(api_client, org, pack):
    r = api_client.post(f'{BASE}/checkout/', {
        'organization': str(org.id), 'pack': str(pack.id)}, format='json')
    assert r.status_code in (401, 403)


def test_checkout_manager_forbidden(manager_client, org, pack):
    r = manager_client.post(f'{BASE}/checkout/', {
        'organization': str(org.id), 'pack': str(pack.id)}, format='json')
    assert r.status_code == 403


def test_checkout_cross_org_404(owner_client, org_b, pack):
    # owner (of org) tries to buy for org_b they don't belong to → 404.
    r = owner_client.post(f'{BASE}/checkout/', {
        'organization': str(org_b.id), 'pack': str(pack.id)}, format='json')
    assert r.status_code == 404


def test_checkout_invalid_uuid_400(owner_client):
    r = owner_client.post(f'{BASE}/checkout/', {
        'organization': 'not-a-uuid', 'pack': 'nope'}, format='json')
    assert r.status_code == 400


# ── refund access control ──────────────────────────────────────────────────
def test_refund_requires_auth(api_client, pending_purchase):
    r = api_client.post(f'{BASE}/refund/', {'purchase': str(pending_purchase.id)},
                        format='json')
    assert r.status_code in (401, 403)


def test_refund_manager_forbidden(manager_client, pending_purchase):
    r = manager_client.post(f'{BASE}/refund/', {'purchase': str(pending_purchase.id)},
                            format='json')
    assert r.status_code == 403


# ── injection / lookup safety ──────────────────────────────────────────────
def test_purchase_list_sql_injection_safe(owner_client, org):
    r = owner_client.get(f'{BASE}/purchases/', {
        'organization': "'; DROP TABLE payments_credit_purchases;--"})
    # Bad org filter → PermissionDenied/empty, never a 500/crash.
    assert r.status_code in (200, 403, 404)


def test_purchase_cross_org_isolation(owner_client, org_b, owner_b, pack):
    from apps.payments.models import CreditPurchase
    p = CreditPurchase.objects.create(
        organization=org_b, pack=pack, status='paid', credits=50,
        amount_hkd=pack.price_hkd)
    r = owner_client.get(f'{BASE}/purchases/', {'organization': str(org_b.id)})
    assert r.status_code in (403, 404)
