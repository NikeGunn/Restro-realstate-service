"""credit_service core: free-before-paid, cap blocking, idempotent reserve."""
from decimal import Decimal

import pytest

from apps.billing.models import UsageCreditBalance, UsageEvent
from apps.billing.services import credit_service as cs
from .conftest import new_key

pytestmark = pytest.mark.django_db


def _reserve(org, credits, key, cost='0.10'):
    return cs.reserve_credits(
        org, credits, event_type='content_studio_image', provider='openai',
        model='gpt-image', cost_usd_estimate=Decimal(cost),
        reference_id=None, idempotency_key=key,
    )


def test_reserve_then_confirm_uses_free_first(org, balance):
    # free=5, paid=10. Reserve 3 → all free.
    ev = _reserve(org, 3, new_key())
    assert ev.reserved_free == 3 and ev.reserved_paid == 0
    bal = UsageCreditBalance.objects.get(organization=org)
    assert bal.reserved_credits == 3

    cs.confirm_credits(ev, credits_actual=3, cost_usd_actual=Decimal('0.10'))
    bal.refresh_from_db()
    assert bal.free_credits_remaining == 2   # 5 - 3
    assert bal.paid_credits_remaining == 10  # untouched
    assert bal.reserved_credits == 0
    assert bal.free_credits_used_this_month == 3


def test_reserve_spans_free_then_paid(org, balance):
    # free=5, paid=10. Reserve 7 → 5 free + 2 paid.
    ev = _reserve(org, 7, new_key())
    assert ev.reserved_free == 5 and ev.reserved_paid == 2
    cs.confirm_credits(ev, credits_actual=7, cost_usd_actual=Decimal('0.50'))
    bal = UsageCreditBalance.objects.get(organization=org)
    assert bal.free_credits_remaining == 0
    assert bal.paid_credits_remaining == 8   # 10 - 2
    # Billable because paid credits were consumed.
    assert bal.current_estimated_spend_hkd > 0


def test_free_only_use_is_not_billable(org, balance):
    ev = _reserve(org, 2, new_key())
    cs.confirm_credits(ev, credits_actual=2, cost_usd_actual=Decimal('0.10'))
    ev.refresh_from_db()
    assert ev.billable_amount_hkd == Decimal('0.0000')
    bal = UsageCreditBalance.objects.get(organization=org)
    assert bal.current_estimated_spend_hkd == Decimal('0.00')


def test_insufficient_credits_blocks(org, balance):
    # total available = 15; ask for 16.
    with pytest.raises(cs.InsufficientCreditsError):
        _reserve(org, 16, new_key())


def test_cap_blocks_reservation(org, balance, limit):
    balance.current_estimated_spend_hkd = Decimal('200')  # == cap
    balance.cap_status = 'blocked'
    balance.save()
    with pytest.raises(cs.InsufficientCreditsError):
        _reserve(org, 1, new_key())


def test_idempotent_reserve_returns_same_event(org, balance):
    key = new_key()
    ev1 = _reserve(org, 2, key)
    ev2 = _reserve(org, 2, key)
    assert ev1.id == ev2.id
    bal = UsageCreditBalance.objects.get(organization=org)
    assert bal.reserved_credits == 2  # reserved ONCE, not twice
    assert UsageEvent.objects.filter(idempotency_key=key).count() == 1


def test_usd_to_hkd_conversion(org, balance, settings):
    settings.BILLING_SETTINGS = {**settings.BILLING_SETTINGS, 'USD_TO_HKD': 8.0}
    ev = _reserve(org, 7, new_key(), cost='1.00')
    cs.confirm_credits(ev, credits_actual=7, cost_usd_actual=Decimal('1.00'))
    ev.refresh_from_db()
    assert ev.cost_hkd == Decimal('8.0000')
