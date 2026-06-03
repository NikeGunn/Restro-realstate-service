"""Monthly reset: free credits restored to plan grant, paid untouched, period advances."""
from decimal import Decimal
from datetime import date

import pytest

from apps.billing.models import UsageCreditBalance
from apps.billing.services import credit_service as cs
from apps.billing.tasks import reset_monthly_credits_task

pytestmark = pytest.mark.django_db


def test_reset_restores_free_keeps_paid(org, balance):
    # Spend down + accrue usage.
    balance.free_credits_remaining = 1
    balance.paid_credits_remaining = 7
    balance.free_credits_used_this_month = 4
    balance.paid_credits_used_this_month = 3
    balance.current_estimated_spend_hkd = Decimal('55')
    balance.period_start = date(2026, 5, 1)
    balance.save()

    cs.reset_monthly_credits(org)
    bal = UsageCreditBalance.objects.get(organization=org)

    assert bal.free_credits_remaining == 20  # plan grant (power = 20)
    assert bal.paid_credits_remaining == 7   # untouched
    assert bal.free_credits_used_this_month == 0
    assert bal.paid_credits_used_this_month == 0
    assert bal.current_estimated_spend_hkd == Decimal('0')
    assert bal.period_start == date.today().replace(day=1)


def test_reset_task_runs_all_orgs(org, org_b, balance):
    result = reset_monthly_credits_task()
    assert result['reset'] >= 2
