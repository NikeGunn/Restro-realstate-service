"""
Shared org-scoped permission classes (Phase 0).

Generalized from apps/inventory/permissions.py. The role model is unchanged:
roles live on apps.accounts.OrganizationMembership.role with choices
('owner', 'manager') — there is NO 'admin' role.

    write (create/update/delete) -> owner only
    read  (safe methods)         -> owner OR manager

Inventory's IsInventoryAdmin / IsInventoryReadOnly become thin subclasses of
these so existing behavior is byte-identical.
"""
from rest_framework.permissions import BasePermission, SAFE_METHODS
from apps.accounts.models import OrganizationMembership


def user_role_in_org(user, organization_id):
    if not user or not user.is_authenticated or not organization_id:
        return None
    m = OrganizationMembership.objects.filter(
        user=user, organization_id=organization_id
    ).first()
    return m.role if m else None


def user_has_any_owner_membership(user):
    if not user or not user.is_authenticated:
        return False
    return OrganizationMembership.objects.filter(
        user=user, role=OrganizationMembership.Role.OWNER
    ).exists()


def user_has_any_membership(user):
    if not user or not user.is_authenticated:
        return False
    return OrganizationMembership.objects.filter(user=user).exists()


class IsOrgMember(BasePermission):
    """
    Owner OR manager of *some* org for reads; gates writes to owners.

    This is the read-oriented class: managers can read, only owners can write.
    Use on ViewSets where managers should have read access.
    """
    message = "This action requires owner or manager role in the organization."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return user_has_any_membership(request.user)
        return user_has_any_owner_membership(request.user)

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        org_id = getattr(obj, 'organization_id', None)
        if not org_id:
            return False
        role = user_role_in_org(request.user, org_id)
        if request.method in SAFE_METHODS:
            return role in (
                OrganizationMembership.Role.OWNER,
                OrganizationMembership.Role.MANAGER,
            )
        return role == OrganizationMembership.Role.OWNER


class IsOrgOwner(BasePermission):
    """
    Owner-only for every method (no manager read).

    Use on ViewSets/actions that are owner-exclusive even for reads
    (e.g. spend-cap edits, merges, sensitive owner ops).
    """
    message = "This action requires owner role in the organization."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return user_has_any_owner_membership(request.user)

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        org_id = getattr(obj, 'organization_id', None)
        if not org_id:
            return False
        return user_role_in_org(request.user, org_id) == OrganizationMembership.Role.OWNER
