"""Shared fixtures for Billing (Phase 6) tests."""
import uuid
from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Organization, OrganizationMembership, User
from apps.billing.models import (
    SubscriptionPlan, UsageCreditBalance, UsageLimit,
)


@pytest.fixture
def power_plan(db):
    return SubscriptionPlan.objects.update_or_create(
        slug='power',
        defaults={'name': 'Growth', 'plan_code': 'power',
                  'price_hkd': Decimal('200'), 'monthly_image_credits': 20,
                  'enabled_modules': ['content_studio']},
    )[0]


@pytest.fixture
def org(db, power_plan):
    """A power-plan org. The post_save signal bootstraps its balance/limit."""
    return Organization.objects.create(
        name='Billing Org', business_type=Organization.BusinessType.RESTAURANT,
        plan=Organization.Plan.POWER,
    )


@pytest.fixture
def org_b(db, power_plan):
    return Organization.objects.create(
        name='Other Billing Org', business_type=Organization.BusinessType.RESTAURANT,
        plan=Organization.Plan.POWER,
    )


def _member(email, org, role):
    user = User.objects.create_user(email=email, username=email.split('@')[0], password='pw')
    OrganizationMembership.objects.create(user=user, organization=org, role=role)
    return user


@pytest.fixture
def owner(db, org):
    return _member('bill_owner@t.test', org, OrganizationMembership.Role.OWNER)


@pytest.fixture
def manager(db, org):
    return _member('bill_mgr@t.test', org, OrganizationMembership.Role.MANAGER)


@pytest.fixture
def owner_b(db, org_b):
    return _member('bill_owner_b@t.test', org_b, OrganizationMembership.Role.OWNER)


@pytest.fixture
def outsider(db):
    return User.objects.create_user(email='bill_rando@t.test', username='bill_rando', password='pw')


@pytest.fixture
def balance(db, org):
    """The org's balance (bootstrapped by signal). Set a known starting state."""
    bal = UsageCreditBalance.objects.get(organization=org)
    bal.free_credits_remaining = 5
    bal.paid_credits_remaining = 10
    bal.reserved_credits = 0
    bal.current_estimated_spend_hkd = Decimal('0')
    bal.cap_status = 'active'
    bal.period_start = date.today().replace(day=1)
    bal.save()
    return bal


@pytest.fixture
def limit(db, org):
    lim = UsageLimit.objects.get(organization=org)
    lim.monthly_ai_spend_cap_hkd = Decimal('200')
    lim.alert_at_percent = 80
    lim.save()
    return lim


def new_key():
    return uuid.uuid4().hex


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def owner_client(api_client, owner):
    api_client.force_authenticate(user=owner)
    return api_client


@pytest.fixture
def manager_client(api_client, manager):
    api_client.force_authenticate(user=manager)
    return api_client
