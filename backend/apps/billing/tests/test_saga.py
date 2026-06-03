"""Saga: reserve→confirm, reserve→refund (zero charge), stale reconciliation."""
from decimal import Decimal

import pytest

from apps.billing.models import UsageCreditBalance, UsageEvent, EventStatus
from apps.billing.services import credit_service as cs
from apps.billing.tasks import reconcile_stale_reservations_task
from .conftest import new_key

pytestmark = pytest.mark.django_db


def _reserve(org, credits, key, cost='0.50'):
    return cs.reserve_credits(
        org, credits, event_type='content_studio_image', provider='openai',
        model='gpt-image', cost_usd_estimate=Decimal(cost),
        reference_id=None, idempotency_key=key,
    )


def test_reserve_then_refund_nets_zero(org, balance):
    before = UsageCreditBalance.objects.get(organization=org)
    free0, paid0 = before.free_credits_remaining, before.paid_credits_remaining

    ev = _reserve(org, 7, new_key())  # 5 free + 2 paid
    cs.refund_credits(ev)  # provider failed before confirm

    bal = UsageCreditBalance.objects.get(organization=org)
    assert bal.reserved_credits == 0
    assert bal.free_credits_remaining == free0
    assert bal.paid_credits_remaining == paid0
    assert bal.current_estimated_spend_hkd == Decimal('0.00')
    ev.refresh_from_db()
    assert ev.status == EventStatus.FAILED
    assert UsageEvent.objects.filter(
        organization=org, status=EventStatus.REFUNDED).count() == 1


def test_refund_after_confirm_restores_credits_and_spend(org, balance):
    ev = _reserve(org, 7, new_key())  # 5 free + 2 paid
    cs.confirm_credits(ev, credits_actual=7, cost_usd_actual=Decimal('0.50'))
    bal = UsageCreditBalance.objects.get(organization=org)
    assert bal.paid_credits_remaining == 8
    spent = bal.current_estimated_spend_hkd
    assert spent > 0

    ev.refresh_from_db()
    cs.refund_credits(ev)
    bal.refresh_from_db()
    # Credits restored, spend backed out.
    assert bal.free_credits_remaining == 5
    assert bal.paid_credits_remaining == 10
    assert bal.current_estimated_spend_hkd == Decimal('0.00')


def test_double_refund_is_idempotent(org, balance):
    ev = _reserve(org, 3, new_key())
    cs.refund_credits(ev)
    ev.refresh_from_db()
    # Second refund on the now-failed event does nothing.
    cs.refund_credits(ev)
    assert UsageEvent.objects.filter(
        organization=org, status=EventStatus.REFUNDED).count() == 1


def test_stale_reservation_reconciled(org, balance, settings):
    settings.BILLING_SETTINGS = {**settings.BILLING_SETTINGS, 'RESERVATION_TTL_MINUTES': 15}
    ev = _reserve(org, 4, new_key())
    # Force the event to look old.
    from django.utils import timezone
    from datetime import timedelta
    UsageEvent.objects.filter(pk=ev.pk).update(
        created_at=timezone.now() - timedelta(minutes=30))

    bal = UsageCreditBalance.objects.get(organization=org)
    assert bal.reserved_credits == 4

    result = reconcile_stale_reservations_task()
    assert result['refunded'] == 1
    bal.refresh_from_db()
    assert bal.reserved_credits == 0  # hold released, no silent charge
    assert bal.current_estimated_spend_hkd == Decimal('0.00')


def test_fresh_reservation_not_reconciled(org, balance):
    ev = _reserve(org, 2, new_key())
    result = reconcile_stale_reservations_task()
    assert result['refunded'] == 0
    ev.refresh_from_db()
    assert ev.status == EventStatus.RESERVED
