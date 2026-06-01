"""
Shared fixtures for common (Phase 0) tests.

Mirrors apps/inventory/tests/conftest.py: org / org_b / owner / owner_b /
manager / outsider, plus API clients. We deliberately reuse the real
InventoryItem + InventoryAuditLog models to exercise the shared mixins against
an already-migrated table (no throwaway test-only model / migration).
"""
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Organization, OrganizationMembership, User
from apps.inventory.models import InventoryItem


@pytest.fixture
def org(db):
    return Organization.objects.create(
        name="Common Test Org", business_type=Organization.BusinessType.RESTAURANT,
    )


@pytest.fixture
def org_b(db):
    return Organization.objects.create(
        name="Other Org", business_type=Organization.BusinessType.RESTAURANT,
    )


@pytest.fixture
def owner(db, org):
    user = User.objects.create_user(
        email='c_owner@test.test', username='c_owner', password='pw',
    )
    OrganizationMembership.objects.create(
        user=user, organization=org, role=OrganizationMembership.Role.OWNER,
    )
    return user


@pytest.fixture
def owner_b(db, org_b):
    user = User.objects.create_user(
        email='c_owner_b@test.test', username='c_owner_b', password='pw',
    )
    OrganizationMembership.objects.create(
        user=user, organization=org_b, role=OrganizationMembership.Role.OWNER,
    )
    return user


@pytest.fixture
def manager(db, org):
    user = User.objects.create_user(
        email='c_mgr@test.test', username='c_mgr', password='pw',
    )
    OrganizationMembership.objects.create(
        user=user, organization=org, role=OrganizationMembership.Role.MANAGER,
    )
    return user


@pytest.fixture
def outsider(db):
    return User.objects.create_user(
        email='c_rando@other.test', username='c_rando', password='pw',
    )


@pytest.fixture
def item(db, org):
    return InventoryItem.objects.create(
        organization=org, name='CommonTomato', unit=InventoryItem.Unit.KG,
        unit_cost=Decimal('2.50'), reorder_level=Decimal('10'),
    )


@pytest.fixture
def item_b(db, org_b):
    return InventoryItem.objects.create(
        organization=org_b, name='OtherOrgSalt', unit=InventoryItem.Unit.KG,
        unit_cost=Decimal('0.80'), reorder_level=Decimal('5'),
    )


@pytest.fixture
def api_client():
    return APIClient()
