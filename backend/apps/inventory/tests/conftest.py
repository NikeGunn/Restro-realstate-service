"""
Shared fixtures for inventory tests.
"""
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Organization, OrganizationMembership, User
from apps.inventory.models import (
    InventoryItem, Supplier, InventoryCategory,
    PurchaseOrder, PurchaseOrderItem, Recipe, RecipeIngredient,
)


@pytest.fixture
def org(db):
    return Organization.objects.create(
        name="Bargachi", business_type=Organization.BusinessType.RESTAURANT,
    )


@pytest.fixture
def org_b(db):
    return Organization.objects.create(
        name="Other Org", business_type=Organization.BusinessType.RESTAURANT,
    )


@pytest.fixture
def owner(db, org):
    user = User.objects.create_user(
        email='owner1@test.test', username='owner1', password='pw',
    )
    OrganizationMembership.objects.create(
        user=user, organization=org, role=OrganizationMembership.Role.OWNER,
    )
    return user


@pytest.fixture
def owner_b(db, org_b):
    user = User.objects.create_user(
        email='owner2@test.test', username='owner2', password='pw',
    )
    OrganizationMembership.objects.create(
        user=user, organization=org_b, role=OrganizationMembership.Role.OWNER,
    )
    return user


@pytest.fixture
def manager(db, org):
    user = User.objects.create_user(
        email='mgr1@test.test', username='mgr1', password='pw',
    )
    OrganizationMembership.objects.create(
        user=user, organization=org, role=OrganizationMembership.Role.MANAGER,
    )
    return user


@pytest.fixture
def outsider(db):
    return User.objects.create_user(
        email='rando@other.test', username='rando', password='pw',
    )


@pytest.fixture
def supplier(db, org):
    return Supplier.objects.create(
        organization=org, name='Acme Foods', tax_id='TAX-1234',
    )


@pytest.fixture
def item(db, org):
    return InventoryItem.objects.create(
        organization=org, name='Tomato', unit=InventoryItem.Unit.KG,
        unit_cost=Decimal('2.50'), reorder_level=Decimal('10'),
        tolerance_percent=Decimal('0.5'),
    )


@pytest.fixture
def item_b(db, org):
    return InventoryItem.objects.create(
        organization=org, name='Salt', unit=InventoryItem.Unit.KG,
        unit_cost=Decimal('0.80'), reorder_level=Decimal('5'),
    )


@pytest.fixture
def output_item(db, org):
    return InventoryItem.objects.create(
        organization=org, name='Tomato Soup', unit=InventoryItem.Unit.LITER,
        unit_cost=Decimal('5.0'),
    )


@pytest.fixture
def category(db, org):
    return InventoryCategory.objects.create(organization=org, name='Produce')


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_owner_client(api_client, owner):
    api_client.force_authenticate(user=owner)
    return api_client


@pytest.fixture
def auth_manager_client(api_client, manager):
    api_client.force_authenticate(user=manager)
    return api_client


@pytest.fixture
def purchase_order(db, org, supplier, item, owner):
    po = PurchaseOrder.objects.create(
        organization=org, supplier=supplier, created_by=owner,
    )
    PurchaseOrderItem.objects.create(
        purchase_order=po, item=item,
        quantity_ordered=Decimal('20'), unit_cost=Decimal('2.0'),
    )
    po.recompute_total()
    po.refresh_from_db()
    return po


@pytest.fixture
def recipe(db, org, item, item_b, output_item, owner):
    r = Recipe.objects.create(
        organization=org, name='Tomato Soup',
        output_item=output_item, output_quantity=Decimal('1'),
        yield_percent=Decimal('100'), created_by=owner,
    )
    RecipeIngredient.objects.create(
        recipe=r, item=item, quantity=Decimal('2'), unit=item.unit,
    )
    RecipeIngredient.objects.create(
        recipe=r, item=item_b, quantity=Decimal('0.1'), unit=item_b.unit,
    )
    return r
