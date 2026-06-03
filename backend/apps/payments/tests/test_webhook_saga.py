"""
Webhook saga + idempotency — the money-correctness heart.

Covers: completed→credits granted once, duplicate event-id dropped, replayed
completed (latch) doesn't double-credit, payment_intent reuse blocked, expired
marks order, refund claws back credits, partial then full refund, handler
failure releases the claim so Stripe's retry lands.
"""
from decimal import Decimal
from unittest.mock import patch

import pytest

from django.core.cache import cache

from apps.billing.models import UsageCreditBalance, UsageEvent
from apps.payments.models import CreditPurchase
from apps.payments.services import StripeWebhookService as WH
from .conftest import make_event

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _completed_session(purchase, pi='pi_test_1', session='cs_test_123'):
    return {
        'id': session,
        'client_reference_id': str(purchase.id),
        'payment_intent': pi,
        'metadata': {'purchase_id': str(purchase.id)},
    }


# ── happy path: credits granted exactly once ──────────────────────────────
def test_completed_grants_credits(org, balance, pending_purchase):
    with patch.object(WH, '_fetch_receipt_url', return_value=''):
        res = WH._handle_completed(_completed_session(pending_purchase))
    assert res['status'] == 'success'
    bal = UsageCreditBalance.objects.get(organization=org)
    assert bal.paid_credits_remaining == 50
    pending_purchase.refresh_from_db()
    assert pending_purchase.credited is True
    assert pending_purchase.status == 'paid'
    # A top-up UsageEvent was recorded in the Phase 6 ledger.
    assert UsageEvent.objects.filter(
        organization=org, event_type='credit_purchase').count() == 1


def test_replayed_completed_does_not_double_credit(org, balance, pending_purchase):
    with patch.object(WH, '_fetch_receipt_url', return_value=''):
        WH._handle_completed(_completed_session(pending_purchase))
        res2 = WH._handle_completed(_completed_session(pending_purchase))  # replay
    assert res2['status'] == 'duplicate'
    bal = UsageCreditBalance.objects.get(organization=org)
    assert bal.paid_credits_remaining == 50  # NOT 100


def test_payment_intent_reuse_blocked(org, balance, pack, owner):
    # Two distinct purchases, same payment_intent (forged replay) → only one credits.
    p1 = CreditPurchase.objects.create(
        organization=org, pack=pack, credits=50, amount_hkd=Decimal('100'),
        status='pending')
    p2 = CreditPurchase.objects.create(
        organization=org, pack=pack, credits=50, amount_hkd=Decimal('100'),
        status='pending')
    with patch.object(WH, '_fetch_receipt_url', return_value=''):
        WH._handle_completed(_completed_session(p1, pi='pi_shared', session='cs_1'))
        res2 = WH._handle_completed(_completed_session(p2, pi='pi_shared', session='cs_2'))
    assert res2['status'] == 'duplicate'
    assert UsageCreditBalance.objects.get(organization=org).paid_credits_remaining == 50


# ── event-id idempotency (atomic claim) ────────────────────────────────────
def test_event_claim_single_winner():
    assert WH.is_duplicate_event('evt_x') is False  # claimed
    assert WH.is_duplicate_event('evt_x') is True   # duplicate


def test_release_allows_retry():
    assert WH.is_duplicate_event('evt_y') is False
    WH.release_event('evt_y')
    assert WH.is_duplicate_event('evt_y') is False  # retry can re-claim


def test_processed_stays_duplicate():
    WH.is_duplicate_event('evt_z')
    WH.mark_event_processed('evt_z')
    assert WH.is_duplicate_event('evt_z') is True


# ── webhook view: duplicate dropped, handler-failure releases claim ─────────
def test_view_duplicate_event_dropped(api_client, pending_purchase):
    ev = make_event('checkout.session.completed',
                    _completed_session(pending_purchase), event_id='evt_dup')
    with patch.object(WH, 'verify_and_construct_event', return_value=ev), \
         patch.object(WH, '_fetch_receipt_url', return_value=''):
        r1 = api_client.post('/api/v1/payments/webhook/', data=b'{}',
                             content_type='application/json', HTTP_STRIPE_SIGNATURE='sig')
        r2 = api_client.post('/api/v1/payments/webhook/', data=b'{}',
                             content_type='application/json', HTTP_STRIPE_SIGNATURE='sig')
    assert r1.status_code == 200
    assert r2.json()['status'] == 'duplicate'
    # Credits granted once despite two deliveries.
    assert UsageCreditBalance.objects.get(
        organization=pending_purchase.organization).paid_credits_remaining == 50


def test_view_handler_failure_releases_claim(api_client):
    ev = make_event('checkout.session.completed', {'id': 'cs_x'}, event_id='evt_fail')
    with patch.object(WH, 'verify_and_construct_event', return_value=ev), \
         patch.object(WH, 'handle_event', side_effect=RuntimeError('boom')):
        r = api_client.post('/api/v1/payments/webhook/', data=b'{}',
                            content_type='application/json', HTTP_STRIPE_SIGNATURE='sig')
    assert r.status_code == 500
    # Claim released → a Stripe retry of the same event can be processed.
    assert WH.is_duplicate_event('evt_fail') is False


# ── expired ────────────────────────────────────────────────────────────────
def test_expired_marks_pending_order(pending_purchase):
    res = WH._handle_expired({
        'id': 'cs_test_123', 'client_reference_id': str(pending_purchase.id),
        'metadata': {'purchase_id': str(pending_purchase.id)}})
    assert res['status'] == 'expired'
    pending_purchase.refresh_from_db()
    assert pending_purchase.status == 'expired'


def test_expired_skips_paid_order(org, balance, pending_purchase):
    with patch.object(WH, '_fetch_receipt_url', return_value=''):
        WH._handle_completed(_completed_session(pending_purchase))
    res = WH._handle_expired({
        'id': 'cs_test_123', 'client_reference_id': str(pending_purchase.id),
        'metadata': {'purchase_id': str(pending_purchase.id)}})
    assert res['status'] == 'skipped'
    pending_purchase.refresh_from_db()
    assert pending_purchase.status == 'paid'  # untouched


# ── refund claws back credits, idempotent on delta ──────────────────────────
def test_refund_claws_back_credits(org, balance, pending_purchase):
    with patch.object(WH, '_fetch_receipt_url', return_value=''):
        WH._handle_completed(_completed_session(pending_purchase, pi='pi_refund'))
    assert UsageCreditBalance.objects.get(organization=org).paid_credits_remaining == 50

    # Full refund of HK$100 → all 50 credits removed.
    res = WH._handle_refunded({
        'id': 'ch_1', 'payment_intent': 'pi_refund', 'amount_refunded': 10000})
    assert res['status'] == 'refunded'
    assert res['credits_removed'] == 50
    assert UsageCreditBalance.objects.get(organization=org).paid_credits_remaining == 0
    pending_purchase.refresh_from_db()
    assert pending_purchase.status == 'refunded'


def test_refund_idempotent_on_same_amount(org, balance, pending_purchase):
    with patch.object(WH, '_fetch_receipt_url', return_value=''):
        WH._handle_completed(_completed_session(pending_purchase, pi='pi_r2'))
    WH._handle_refunded({'id': 'ch_2', 'payment_intent': 'pi_r2', 'amount_refunded': 10000})
    # Same refund event re-delivered → no further claw-back.
    res2 = WH._handle_refunded({'id': 'ch_2', 'payment_intent': 'pi_r2', 'amount_refunded': 10000})
    assert res2['status'] == 'duplicate'
    assert UsageCreditBalance.objects.get(organization=org).paid_credits_remaining == 0


def test_partial_then_full_refund(org, balance, pending_purchase):
    with patch.object(WH, '_fetch_receipt_url', return_value=''):
        WH._handle_completed(_completed_session(pending_purchase, pi='pi_r3'))
    # Partial HK$50 → 25 credits removed.
    WH._handle_refunded({'id': 'ch_3', 'payment_intent': 'pi_r3', 'amount_refunded': 5000})
    assert UsageCreditBalance.objects.get(organization=org).paid_credits_remaining == 25
    # Then full HK$100 total → remaining 25 removed.
    WH._handle_refunded({'id': 'ch_3', 'payment_intent': 'pi_r3', 'amount_refunded': 10000})
    assert UsageCreditBalance.objects.get(organization=org).paid_credits_remaining == 0
