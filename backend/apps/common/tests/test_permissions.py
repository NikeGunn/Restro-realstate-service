"""
Permission-class tests (Phase 0): IsOrgMember / IsOrgOwner.

Also asserts the inventory aliases still resolve to the shared behavior, so the
Phase 0 refactor is backward-compatible.
"""
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.common.permissions import IsOrgMember, IsOrgOwner

pytestmark = pytest.mark.django_db
factory = APIRequestFactory()


class _MemberView(APIView):
    permission_classes = [IsOrgMember]

    def get(self, request):
        return Response({'ok': True})

    def post(self, request):
        return Response({'ok': True})


class _OwnerView(APIView):
    permission_classes = [IsOrgOwner]

    def get(self, request):
        return Response({'ok': True})


def _call(view_cls, method, user):
    view = view_cls.as_view()
    request = getattr(factory, method)('/x/')
    force_authenticate(request, user=user)
    return view(request)


# IsOrgMember: manager reads, manager cannot write, owner can write.
def test_member_manager_can_read(manager):
    assert _call(_MemberView, 'get', manager).status_code == 200


def test_member_manager_cannot_write(manager):
    assert _call(_MemberView, 'post', manager).status_code == 403


def test_member_owner_can_write(owner):
    assert _call(_MemberView, 'post', owner).status_code == 200


def test_member_outsider_denied(outsider):
    assert _call(_MemberView, 'get', outsider).status_code == 403


# IsOrgOwner: owner-only even for reads.
def test_owner_only_manager_denied(manager):
    assert _call(_OwnerView, 'get', manager).status_code == 403


def test_owner_only_owner_allowed(owner):
    assert _call(_OwnerView, 'get', owner).status_code == 200


# Backward-compat: inventory aliases still point at the shared behavior.
def test_inventory_alias_is_subclass():
    from apps.inventory.permissions import IsInventoryAdmin
    from apps.inventory.mixins import InventoryOrgScopeMixin
    from apps.common.mixins import OrgScopeMixin
    assert issubclass(IsInventoryAdmin, IsOrgMember)
    assert issubclass(InventoryOrgScopeMixin, OrgScopeMixin)
