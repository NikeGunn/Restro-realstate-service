"""Shared fixtures for restaurant Phase 3 (menu management) tests."""
import pytest
from decimal import Decimal
from rest_framework.test import APIClient

from apps.accounts.models import Organization, OrganizationMembership, User
from apps.restaurant.models import MenuCategory, MenuItem, MenuItemType


@pytest.fixture
def org(db):
    return Organization.objects.create(
        name="Resto Test Org",
        business_type=Organization.BusinessType.RESTAURANT,
    )


@pytest.fixture
def org_b(db):
    return Organization.objects.create(
        name="Resto Other Org",
        business_type=Organization.BusinessType.RESTAURANT,
    )


@pytest.fixture
def owner(db, org):
    user = User.objects.create_user(
        email='resto_owner@t.test', username='resto_owner', password='pw')
    OrganizationMembership.objects.create(
        user=user, organization=org, role=OrganizationMembership.Role.OWNER)
    return user


@pytest.fixture
def owner_b(db, org_b):
    user = User.objects.create_user(
        email='resto_owner_b@t.test', username='resto_owner_b', password='pw')
    OrganizationMembership.objects.create(
        user=user, organization=org_b, role=OrganizationMembership.Role.OWNER)
    return user


@pytest.fixture
def manager(db, org):
    user = User.objects.create_user(
        email='resto_mgr@t.test', username='resto_mgr', password='pw')
    OrganizationMembership.objects.create(
        user=user, organization=org, role=OrganizationMembership.Role.MANAGER)
    return user


@pytest.fixture
def outsider(db):
    return User.objects.create_user(
        email='resto_rando@t.test', username='resto_rando', password='pw')


@pytest.fixture
def category(db, org):
    return MenuCategory.objects.create(organization=org, name='Drinks')


@pytest.fixture
def category_b(db, org_b):
    return MenuCategory.objects.create(organization=org_b, name='Other Drinks')


@pytest.fixture
def food_item(db, category):
    return MenuItem.objects.create(
        category=category, name='Fries', price=Decimal('30.00'),
        item_type=MenuItemType.FOOD,
    )


@pytest.fixture
def beer_item(db, category):
    return MenuItem.objects.create(
        category=category, name='Draft Beer', price=Decimal('50.00'),
        item_type=MenuItemType.ALCOHOL, is_alcohol=True, alcohol_brand='Heineken',
    )


@pytest.fixture
def cocktail_item(db, category):
    return MenuItem.objects.create(
        category=category, name='Vodka Lime', price=Decimal('90.00'),
        item_type=MenuItemType.COCKTAIL, is_alcohol=True, alcohol_brand='Absolut',
    )


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
