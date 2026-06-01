"""Shared fixtures for CRM (Phase 1) tests."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Organization, OrganizationMembership, User
from apps.crm.models import CRMCustomer, CustomerSource


@pytest.fixture
def org(db):
    return Organization.objects.create(
        name="CRM Test Org", business_type=Organization.BusinessType.RESTAURANT,
    )


@pytest.fixture
def org_b(db):
    return Organization.objects.create(
        name="CRM Other Org", business_type=Organization.BusinessType.RESTAURANT,
    )


@pytest.fixture
def owner(db, org):
    user = User.objects.create_user(email='crm_owner@t.test', username='crm_owner', password='pw')
    OrganizationMembership.objects.create(
        user=user, organization=org, role=OrganizationMembership.Role.OWNER)
    return user


@pytest.fixture
def owner_b(db, org_b):
    user = User.objects.create_user(email='crm_owner_b@t.test', username='crm_owner_b', password='pw')
    OrganizationMembership.objects.create(
        user=user, organization=org_b, role=OrganizationMembership.Role.OWNER)
    return user


@pytest.fixture
def manager(db, org):
    user = User.objects.create_user(email='crm_mgr@t.test', username='crm_mgr', password='pw')
    OrganizationMembership.objects.create(
        user=user, organization=org, role=OrganizationMembership.Role.MANAGER)
    return user


@pytest.fixture
def outsider(db):
    return User.objects.create_user(email='crm_rando@t.test', username='crm_rando', password='pw')


@pytest.fixture
def customer(db, org):
    return CRMCustomer.objects.create(
        organization=org, name='Alice Chan', phone='+85291234567',
        email='alice@example.com', source=CustomerSource.MANUAL,
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
