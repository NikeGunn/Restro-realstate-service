"""
Shared fixtures for Coffee Pass tests.

Mirrors the inventory/lucky_draw fixture conventions (org / owner / manager /
outsider / cross-org twin) so the tenancy matrix is testable the same way
everywhere in this codebase.
"""
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Location, Organization, OrganizationMembership, User
from apps.crm.models import CRMCustomer, CustomerSource
from apps.restaurant.models import MenuCategory, MenuItem, MenuItemType

from apps.coffee_pass.models import (
    CoffeePass, CoffeePassPlan, CoffeePassPurchase, PassStatus, PlanStatus,
    PurchaseStatus,
)


# ──────────────────────────────────────────────────────────────────────
# Tenancy
# ──────────────────────────────────────────────────────────────────────
@pytest.fixture
def org(db):
    return Organization.objects.create(
        name='Cafe Test Org', business_type=Organization.BusinessType.RESTAURANT,
    )


@pytest.fixture
def org_b(db):
    """A second tenant — every isolation assertion needs a real neighbour."""
    return Organization.objects.create(
        name='Other Cafe Org', business_type=Organization.BusinessType.RESTAURANT,
    )


@pytest.fixture
def location(db, org):
    return Location.objects.create(
        organization=org, name='Central Branch', timezone='Asia/Hong_Kong',
        is_primary=True,
    )


@pytest.fixture
def location_2(db, org):
    """A SECOND location in the SAME org — proves passes are location-bound."""
    return Location.objects.create(
        organization=org, name='Wan Chai Branch', timezone='Asia/Hong_Kong',
    )


@pytest.fixture
def location_b(db, org_b):
    return Location.objects.create(
        organization=org_b, name='Rival Branch', timezone='Asia/Hong_Kong',
    )


@pytest.fixture
def owner(db, org):
    user = User.objects.create_user(
        email='cp_owner@t.test', username='cp_owner', password='pw',
    )
    OrganizationMembership.objects.create(
        user=user, organization=org, role=OrganizationMembership.Role.OWNER,
    )
    return user


@pytest.fixture
def manager(db, org):
    user = User.objects.create_user(
        email='cp_mgr@t.test', username='cp_mgr', password='pw',
    )
    OrganizationMembership.objects.create(
        user=user, organization=org, role=OrganizationMembership.Role.MANAGER,
    )
    return user


@pytest.fixture
def owner_b(db, org_b):
    user = User.objects.create_user(
        email='cp_owner_b@t.test', username='cp_owner_b', password='pw',
    )
    OrganizationMembership.objects.create(
        user=user, organization=org_b, role=OrganizationMembership.Role.OWNER,
    )
    return user


@pytest.fixture
def outsider(db):
    """Authenticated but belongs to no organization."""
    return User.objects.create_user(
        email='cp_rando@t.test', username='cp_rando', password='pw',
    )


# ──────────────────────────────────────────────────────────────────────
# Menu
# ──────────────────────────────────────────────────────────────────────
@pytest.fixture
def category(db, org):
    return MenuCategory.objects.create(organization=org, name='Coffee')


@pytest.fixture
def category_b(db, org_b):
    return MenuCategory.objects.create(organization=org_b, name='Rival Coffee')


@pytest.fixture
def coffee_items(db, category):
    """Three coffees averaging HK$40 — break-even math is hand-checkable."""
    return [
        MenuItem.objects.create(
            category=category, name=name, price=Decimal(price),
            item_type=MenuItemType.DRINK, is_available=True,
        )
        for name, price in [('Latte', '40.00'), ('Flat White', '38.00'),
                            ('Cold Brew', '42.00')]
    ]


@pytest.fixture
def espresso_item(db, category):
    """An item on the NEW dedicated coffee type (the intended classification)."""
    return MenuItem.objects.create(
        category=category, name='Espresso', price=Decimal('28.00'),
        item_type=MenuItemType.COFFEE, is_available=True,
    )


@pytest.fixture
def food_item(db, category):
    """
    A FOOD item in the same org. The bug this guards: a Coffee Pass was sold
    against 'Aloo Nimki' and a HK$175 mixed platter because the dashboard filter
    matched nothing and silently fell back to the whole menu.
    """
    return MenuItem.objects.create(
        category=category, name='Mixed Platter', price=Decimal('175.00'),
        item_type=MenuItemType.FOOD, is_available=True,
    )


@pytest.fixture
def foreign_item(db, category_b):
    """An item owned by the OTHER org — must never be attachable to our plan."""
    return MenuItem.objects.create(
        category=category_b, name='Rival Latte', price=Decimal('40.00'),
        item_type=MenuItemType.DRINK, is_available=True,
    )


# ──────────────────────────────────────────────────────────────────────
# Customers
# ──────────────────────────────────────────────────────────────────────
@pytest.fixture
def customer(db, org):
    return CRMCustomer.objects.create(
        organization=org, name='Ada Wong', phone='+85251234567',
        source=CustomerSource.WALK_IN,
    )


@pytest.fixture
def customer_2(db, org):
    return CRMCustomer.objects.create(
        organization=org, name='Bo Chan', phone='+85251234568',
        source=CustomerSource.WALK_IN,
    )


@pytest.fixture
def customer_b(db, org_b):
    return CRMCustomer.objects.create(
        organization=org_b, name='Rival Customer', phone='+85259999999',
        source=CustomerSource.WALK_IN,
    )


# ──────────────────────────────────────────────────────────────────────
# Plans / passes
# ──────────────────────────────────────────────────────────────────────
@pytest.fixture
def draft_plan(db, org, location, coffee_items):
    """HK$120 / 30% off an avg HK$40 coffee -> saving 12 -> break-even 10 visits."""
    plan = CoffeePassPlan.objects.create(
        organization=org, location=location,
        name='Coffee Pass — 30 days',
        price_hkd=Decimal('120.00'), discount_percent=Decimal('30.00'),
        duration_days=30, status=PlanStatus.DRAFT,
    )
    plan.eligible_items.set(coffee_items)
    return plan


@pytest.fixture
def active_plan(db, draft_plan):
    draft_plan.status = PlanStatus.ACTIVE
    draft_plan.save(update_fields=['status'])
    return draft_plan


@pytest.fixture
def plan_b(db, org_b, location_b):
    """An active plan at the OTHER tenant, for cross-org assertions."""
    item = MenuItem.objects.create(
        category=MenuCategory.objects.create(organization=org_b, name='B Coffee'),
        name='B Latte', price=Decimal('40.00'), item_type=MenuItemType.DRINK,
    )
    plan = CoffeePassPlan.objects.create(
        organization=org_b, location=location_b, name='Rival Pass',
        price_hkd=Decimal('100.00'), discount_percent=Decimal('30.00'),
        duration_days=30, status=PlanStatus.ACTIVE,
    )
    plan.eligible_items.set([item])
    return plan


def make_active_pass(plan, customer, *, days=30, status=PassStatus.ACTIVE):
    """
    Build a paid purchase + active pass without going through Stripe.

    Used by every test that needs an entitlement but is not testing payment.
    """
    now = timezone.now()
    purchase = CoffeePassPurchase.objects.create(
        organization=plan.organization, location=plan.location,
        customer=customer, plan=plan, status=PurchaseStatus.PAID,
        plan_snapshot=plan.build_snapshot(), amount_hkd=plan.price_hkd,
        activated=True, paid_at=now,
    )
    return CoffeePass.objects.create(
        organization=plan.organization, location=plan.location,
        customer=customer, plan=plan, purchase=purchase, status=status,
        plan_snapshot=purchase.plan_snapshot,
        starts_at=now, expires_at=now + timezone.timedelta(days=days),
    )


@pytest.fixture
def active_pass(db, active_plan, customer):
    return make_active_pass(active_plan, customer)


# ──────────────────────────────────────────────────────────────────────
# Experiences (the quality gate's input)
# ──────────────────────────────────────────────────────────────────────
@pytest.fixture
def good_experience(db, active_plan, customer):
    """Good coffee + a nearby routine — the fully eligible case."""
    from apps.coffee_pass.models import CoffeeExperience, Sentiment
    return CoffeeExperience.objects.create(
        organization=active_plan.organization, location=active_plan.location,
        customer=customer, plan=active_plan,
        sentiment=Sentiment.GOOD, routine_context='work_nearby',
    )


@pytest.fixture
def negative_experience(db, active_plan, customer):
    """Bad coffee — must block every offer path, however good the score."""
    from apps.coffee_pass.models import CoffeeExperience, Sentiment
    return CoffeeExperience.objects.create(
        organization=active_plan.organization, location=active_plan.location,
        customer=customer, plan=active_plan,
        sentiment=Sentiment.NOT_GOOD, routine_context='work_nearby',
        comment='Coffee was cold and bitter.',
    )


# ──────────────────────────────────────────────────────────────────────
# API clients
# ──────────────────────────────────────────────────────────────────────
@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def owner_api(owner):
    client = APIClient()
    client.force_authenticate(user=owner)
    return client


@pytest.fixture
def manager_api(manager):
    client = APIClient()
    client.force_authenticate(user=manager)
    return client


@pytest.fixture
def owner_b_api(owner_b):
    client = APIClient()
    client.force_authenticate(user=owner_b)
    return client


@pytest.fixture
def outsider_api(outsider):
    client = APIClient()
    client.force_authenticate(user=outsider)
    return client


@pytest.fixture(autouse=True)
def clear_cache():
    """
    Wipe Redis between tests.

    Non-negotiable here: OTP rate limits, webhook event claims and checkout
    idempotency all live in the cache, so a leaked key from one test would make
    the next one fail for an entirely fictional reason.
    """
    from django.core.cache import cache
    cache.clear()
    yield
    cache.clear()
