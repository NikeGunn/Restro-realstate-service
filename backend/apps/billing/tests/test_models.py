"""Model + provisioning invariants."""
from decimal import Decimal

import pytest

from apps.accounts.models import Organization
from apps.billing.models import (
    UsageCreditBalance, UsageLimit, AccountSubscription, SubscriptionPlan,
)

pytestmark = pytest.mark.django_db


def test_org_creation_bootstraps_balance_and_limit(power_plan):
    org = Organization.objects.create(
        name='Fresh Org', business_type=Organization.BusinessType.RESTAURANT,
        plan=Organization.Plan.POWER,
    )
    assert UsageCreditBalance.objects.filter(organization=org).exists()
    assert UsageLimit.objects.filter(organization=org).exists()
    bal = UsageCreditBalance.objects.get(organization=org)
    assert bal.free_credits_remaining == 20  # power grant


def test_seeded_plans_present():
    # The seed migration (0002) runs against the test DB.
    assert SubscriptionPlan.objects.filter(slug='basic').exists()
    assert SubscriptionPlan.objects.filter(slug='power').exists()


def test_total_available_property(org, balance):
    balance.free_credits_remaining = 3
    balance.paid_credits_remaining = 4
    balance.reserved_credits = 2
    balance.save()
    assert UsageCreditBalance.objects.get(organization=org).total_available == 5


def test_subscription_created_for_power_org(power_plan):
    org = Organization.objects.create(
        name='Sub Org', business_type=Organization.BusinessType.RESTAURANT,
        plan=Organization.Plan.POWER,
    )
    assert AccountSubscription.objects.filter(organization=org, status='active').exists()
