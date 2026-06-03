"""
Provisioning — create/ensure the billing rows (balance, limit, subscription)
for an organization. Idempotent and safe to call repeatedly.

Used by the org-created signal (new orgs) and the backfill migration (existing
orgs). The monthly free-credit grant is derived from the org's current plan via
the seeded SubscriptionPlan whose `plan_code` matches `Organization.plan`.
"""
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from ..constants import DEFAULT_SPEND_CAP_HKD, DEFAULT_ALERT_PERCENT


def _plan_for_org(org):
    """The seeded SubscriptionPlan matching the org's current plan_code, or None."""
    from ..models import SubscriptionPlan
    return (
        SubscriptionPlan.objects.filter(plan_code=org.plan).order_by('-price_hkd').first()
        or SubscriptionPlan.objects.order_by('price_hkd').first()
    )


def _period_start(today=None) -> date:
    today = today or timezone.now().date()
    return today.replace(day=1)


@transaction.atomic
def ensure_billing_for_org(org):
    """Create the UsageCreditBalance + UsageLimit (+ AccountSubscription) for an
    org if missing. Returns the balance. Idempotent.
    """
    from ..models import (
        UsageCreditBalance, UsageLimit, AccountSubscription, SubscriptionStatus,
    )

    period_start = _period_start()
    plan = _plan_for_org(org)
    free_credits = plan.monthly_image_credits if plan else 0

    balance, created = UsageCreditBalance.objects.get_or_create(
        organization=org,
        defaults={
            'free_credits_remaining': free_credits,
            'period_start': period_start,
        },
    )

    UsageLimit.objects.get_or_create(
        organization=org,
        defaults={
            'monthly_ai_spend_cap_hkd': Decimal(DEFAULT_SPEND_CAP_HKD),
            'alert_at_percent': DEFAULT_ALERT_PERCENT,
        },
    )

    if plan is not None:
        today = period_start
        # current_period_end = last day before next month
        if today.month == 12:
            period_end = today.replace(year=today.year + 1, month=1, day=1)
        else:
            period_end = today.replace(month=today.month + 1, day=1)
        AccountSubscription.objects.get_or_create(
            organization=org,
            status=SubscriptionStatus.ACTIVE,
            defaults={
                'plan': plan,
                'current_period_start': today,
                'current_period_end': period_end,
                'monthly_ai_spend_cap_hkd': Decimal(DEFAULT_SPEND_CAP_HKD),
            },
        )

    return balance
