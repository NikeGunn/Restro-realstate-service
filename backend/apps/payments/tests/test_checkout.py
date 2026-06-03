"""Checkout-session creation (Stripe mocked) + concurrency double-delivery."""
import threading
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest

from django.core.cache import cache

from apps.accounts.models import Organization
from apps.billing.models import UsageCreditBalance
from apps.billing.services.provisioning import ensure_billing_for_org
from apps.payments.models import CreditPack, CreditPurchase
from apps.payments.services import StripeWebhookService as WH

pytestmark = pytest.mark.django_db

BASE = '/api/v1/payments'


def test_owner_creates_checkout_session(owner_client, org, pack):
    fake_session = {'id': 'cs_live_1', 'url': 'https://checkout.stripe.com/c/pay/cs_live_1'}
    with patch('apps.payments.services.get_stripe') as gs:
        gs.return_value.checkout.Session.create.return_value = fake_session
        r = owner_client.post(f'{BASE}/checkout/', {
            'organization': str(org.id), 'pack': str(pack.id)}, format='json')
    assert r.status_code == 200
    assert r.data['checkout_url'].startswith('https://checkout.stripe.com')
    assert r.data['credits'] == 50
    # A pending purchase was recorded with the session id.
    p = CreditPurchase.objects.get(id=r.data['purchase_id'])
    assert p.status == 'pending' and p.stripe_session_id == 'cs_live_1'


def test_checkout_packs_list_visible_to_member(manager_client, pack):
    r = manager_client.get(f'{BASE}/packs/')
    rows = r.data['results'] if isinstance(r.data, dict) else r.data
    assert any(x['slug'] == pack.slug for x in rows)


def test_config_publishable_only(owner_client):
    r = owner_client.get(f'{BASE}/config/')
    assert r.data['publishable_key'] == 'pk_test_fake'


@pytest.mark.django_db(transaction=True)
def test_concurrent_webhook_delivery_credits_once(django_db_setup):
    """Two threads deliver the SAME completed event → credits granted once."""
    cache.clear()
    from apps.billing.models import SubscriptionPlan
    SubscriptionPlan.objects.update_or_create(
        slug='power', defaults={'name': 'G', 'plan_code': 'power',
                                'price_hkd': Decimal('200'), 'monthly_image_credits': 0,
                                'enabled_modules': []})
    org = Organization.objects.create(
        name='Race Org', business_type=Organization.BusinessType.RESTAURANT,
        plan=Organization.Plan.POWER)
    ensure_billing_for_org(org)
    pack = CreditPack.objects.create(
        slug='race-pack', name='Race', credits=30, price_hkd=Decimal('60'), currency='hkd')
    purchase = CreditPurchase.objects.create(
        organization=org, pack=pack, credits=30, amount_hkd=Decimal('60'),
        status='pending', stripe_session_id='cs_race')

    session = {'id': 'cs_race', 'client_reference_id': str(purchase.id),
               'payment_intent': 'pi_race', 'metadata': {'purchase_id': str(purchase.id)}}
    event = {'id': 'evt_race', 'type': 'checkout.session.completed',
             'data': {'object': session}}

    from rest_framework.test import APIClient
    results = []
    barrier = threading.Barrier(2)

    def deliver():
        from django.db import connection
        client = APIClient()
        barrier.wait()
        with patch.object(WH, 'verify_and_construct_event', return_value=event), \
             patch.object(WH, '_fetch_receipt_url', return_value=''):
            resp = client.post(f'{BASE}/webhook/', data=b'{}',
                               content_type='application/json', HTTP_STRIPE_SIGNATURE='sig')
        results.append(resp.status_code)
        connection.close()

    t1 = threading.Thread(target=deliver); t2 = threading.Thread(target=deliver)
    t1.start(); t2.start(); t1.join(); t2.join()

    bal = UsageCreditBalance.objects.get(organization=org)
    assert bal.paid_credits_remaining == 30, f'credited more than once: {bal.paid_credits_remaining}'

    # cleanup (transaction=True doesn't roll back)
    from apps.billing.models import UsageEvent
    UsageEvent.objects.filter(organization=org).delete()
    CreditPurchase.objects.filter(organization=org).delete()
    UsageCreditBalance.objects.filter(organization=org).delete()
    pack.delete(); org.delete()
    cache.clear()
