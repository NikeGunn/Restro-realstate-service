"""Shared fixtures for payments (Stripe) tests."""
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Organization, OrganizationMembership, User
from apps.billing.models import SubscriptionPlan, UsageCreditBalance
from apps.payments.models import CreditPack, CreditPurchase

STRIPE_TEST_SETTINGS = dict(
    STRIPE_SECRET_KEY='sk_test_fake',
    STRIPE_PUBLISHABLE_KEY='pk_test_fake',
    STRIPE_WEBHOOK_SECRET='whsec_test_fake',
)


@pytest.fixture(autouse=True)
def _stripe_settings(settings):
    for k, v in STRIPE_TEST_SETTINGS.items():
        setattr(settings, k, v)


@pytest.fixture
def power_plan(db):
    return SubscriptionPlan.objects.update_or_create(
        slug='power', defaults={'name': 'Growth', 'plan_code': 'power',
                                'price_hkd': Decimal('200'), 'monthly_image_credits': 20,
                                'enabled_modules': ['content_studio']})[0]


@pytest.fixture
def org(db, power_plan):
    return Organization.objects.create(
        name='Pay Org', business_type=Organization.BusinessType.RESTAURANT,
        plan=Organization.Plan.POWER)


@pytest.fixture
def org_b(db, power_plan):
    return Organization.objects.create(
        name='Other Pay Org', business_type=Organization.BusinessType.RESTAURANT,
        plan=Organization.Plan.POWER)


def _member(email, org, role):
    u = User.objects.create_user(email=email, username=email.split('@')[0], password='pw')
    OrganizationMembership.objects.create(user=u, organization=org, role=role)
    return u


@pytest.fixture
def owner(db, org):
    return _member('pay_owner@t.test', org, OrganizationMembership.Role.OWNER)


@pytest.fixture
def manager(db, org):
    return _member('pay_mgr@t.test', org, OrganizationMembership.Role.MANAGER)


@pytest.fixture
def owner_b(db, org_b):
    return _member('pay_owner_b@t.test', org_b, OrganizationMembership.Role.OWNER)


@pytest.fixture
def outsider(db):
    return User.objects.create_user(email='pay_rando@t.test', username='pay_rando', password='pw')


@pytest.fixture
def pack(db):
    return CreditPack.objects.create(
        slug='test-pack', name='Test Pack', credits=50, price_hkd=Decimal('100.00'),
        currency='hkd', is_active=True)


@pytest.fixture
def balance(db, org):
    bal = UsageCreditBalance.objects.get(organization=org)
    bal.paid_credits_remaining = 0
    bal.save()
    return bal


@pytest.fixture
def pending_purchase(db, org, pack, owner):
    return CreditPurchase.objects.create(
        organization=org, pack=pack, initiated_by=owner,
        status=CreditPurchase.Status.PENDING, credits=pack.credits,
        amount_hkd=pack.price_hkd, currency='hkd',
        stripe_session_id='cs_test_123')


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


def make_event(event_type, obj, event_id='evt_test_1'):
    """Build a Stripe-event-shaped dict for handler tests."""
    return {'id': event_id, 'type': event_type, 'data': {'object': obj}}
