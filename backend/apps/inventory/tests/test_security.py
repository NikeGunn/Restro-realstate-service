"""
Security tests — Plane B must be unreachable to non-admin users.
"""
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Organization, OrganizationMembership, User
from apps.inventory.models import InventoryItem


@pytest.fixture
def org(db):
    return Organization.objects.create(
        name="Acme", business_type=Organization.BusinessType.RESTAURANT,
    )


@pytest.fixture
def owner(db, org):
    user = User.objects.create_user(
        email="owner@acme.test", username="owner", password="pw"
    )
    OrganizationMembership.objects.create(
        user=user, organization=org, role=OrganizationMembership.Role.OWNER,
    )
    return user


@pytest.fixture
def manager(db, org):
    user = User.objects.create_user(
        email="mgr@acme.test", username="mgr", password="pw"
    )
    OrganizationMembership.objects.create(
        user=user, organization=org, role=OrganizationMembership.Role.MANAGER,
    )
    return user


@pytest.fixture
def outsider(db):
    return User.objects.create_user(
        email="rando@other.test", username="rando", password="pw"
    )


@pytest.fixture
def item(db, org):
    return InventoryItem.objects.create(
        organization=org, name="Salt", unit=InventoryItem.Unit.KG,
        unit_cost=Decimal('1'),
    )


def _auth(client, user):
    client.force_authenticate(user=user)


def test_anonymous_user_cannot_list_items(db):
    client = APIClient()
    res = client.get('/api/v1/inventory/items/')
    assert res.status_code in (401, 403)


def test_outsider_cannot_see_org_items(db, outsider, item):
    """Users with zero memberships are denied at the permission layer."""
    client = APIClient()
    _auth(client, outsider)
    res = client.get('/api/v1/inventory/items/')
    assert res.status_code == 403


def test_owner_can_create_item(db, owner, org):
    client = APIClient()
    _auth(client, owner)
    res = client.post('/api/v1/inventory/items/', {
        'organization': str(org.id),
        'name': 'Sugar',
        'unit': 'kg',
        'unit_cost': '1.5',
    }, format='json')
    assert res.status_code in (200, 201), res.content


def test_manager_cannot_create_item(db, manager, org):
    client = APIClient()
    _auth(client, manager)
    res = client.post('/api/v1/inventory/items/', {
        'organization': str(org.id),
        'name': 'Sugar', 'unit': 'kg', 'unit_cost': '1.5',
    }, format='json')
    assert res.status_code == 403


def test_manager_can_read_items(db, manager, item):
    client = APIClient()
    _auth(client, manager)
    res = client.get('/api/v1/inventory/items/')
    assert res.status_code == 200
    results = res.json().get('results', res.json())
    assert any(r['id'] == str(item.id) for r in results)
