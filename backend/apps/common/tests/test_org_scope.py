"""
OrgScopeMixin tests (Phase 0).

Driven against a minimal ViewSet built on the real InventoryItem model so we
exercise the shared mixin exactly as a Phase 1+ app would use it.
"""
import pytest
from rest_framework import serializers, viewsets
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.common.mixins import OrgScopeMixin
from apps.inventory.models import InventoryItem

pytestmark = pytest.mark.django_db


class _ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryItem
        fields = ['id', 'organization', 'name', 'unit', 'unit_cost', 'reorder_level']


class _ItemViewSet(OrgScopeMixin, viewsets.ModelViewSet):
    queryset = InventoryItem.objects.all()
    serializer_class = _ItemSerializer


factory = APIRequestFactory()


def _list_for(user, query=''):
    view = _ItemViewSet.as_view({'get': 'list'})
    request = factory.get(f'/x/{query}')
    force_authenticate(request, user=user)
    return view(request)


def test_member_sees_only_own_org(owner, item, item_b):
    resp = _list_for(owner)
    assert resp.status_code == 200
    names = {row['name'] for row in resp.data['results']}
    assert 'CommonTomato' in names
    assert 'OtherOrgSalt' not in names  # belongs to org_b


def test_outsider_sees_empty(outsider, item):
    resp = _list_for(outsider)
    assert resp.status_code == 200
    assert resp.data['count'] == 0


def test_manager_can_read(manager, item):
    resp = _list_for(manager)
    assert resp.status_code == 200
    assert resp.data['count'] >= 1


def test_cross_org_query_param_denied(owner, org_b, item):
    # Owner of org asks to narrow to org_b they don't belong to -> PermissionDenied.
    view = _ItemViewSet.as_view({'get': 'list'})
    request = factory.get(f'/x/?organization={org_b.id}')
    force_authenticate(request, user=owner)
    resp = view(request)
    assert resp.status_code == 403


def test_own_org_query_param_allowed(owner, org, item):
    view = _ItemViewSet.as_view({'get': 'list'})
    request = factory.get(f'/x/?organization={org.id}')
    force_authenticate(request, user=owner)
    resp = view(request)
    assert resp.status_code == 200
    assert resp.data['count'] == 1


def test_cross_org_object_retrieve_is_404(owner, item_b):
    # item_b is in org_b; owner is not a member -> 404 (not 403, no existence leak).
    view = _ItemViewSet.as_view({'get': 'retrieve'})
    request = factory.get(f'/x/{item_b.id}/')
    force_authenticate(request, user=owner)
    resp = view(request, pk=str(item_b.id))
    assert resp.status_code == 404


def test_perform_create_requires_owner_of_payload_org(manager, org):
    # Manager (not owner) tries to create in their org -> PermissionDenied.
    view = _ItemViewSet.as_view({'post': 'create'})
    request = factory.post('/x/', {
        'organization': str(org.id), 'name': 'NewItem',
        'unit': InventoryItem.Unit.KG, 'unit_cost': '1.00', 'reorder_level': '1',
    })
    force_authenticate(request, user=manager)
    resp = view(request)
    assert resp.status_code in (403, 400)
    assert not InventoryItem.objects.filter(name='NewItem').exists()


def test_perform_create_owner_succeeds(owner, org):
    view = _ItemViewSet.as_view({'post': 'create'})
    request = factory.post('/x/', {
        'organization': str(org.id), 'name': 'OwnerItem',
        'unit': InventoryItem.Unit.KG, 'unit_cost': '1.00', 'reorder_level': '1',
    })
    force_authenticate(request, user=owner)
    resp = view(request)
    assert resp.status_code == 201
    assert InventoryItem.objects.filter(name='OwnerItem', organization=org).exists()
