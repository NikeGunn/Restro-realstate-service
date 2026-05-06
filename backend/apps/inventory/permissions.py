"""
Inventory permissions — Plane B is admin-only.

Roles in this codebase live on apps.accounts.OrganizationMembership.role
with choices ('owner', 'manager'). There is no separate 'admin' role.

Inventory write access  → owner only
Inventory read access   → owner OR manager
"""
from rest_framework.permissions import BasePermission, SAFE_METHODS
from apps.accounts.models import OrganizationMembership


def _user_role_in_org(user, organization_id):
    if not user or not user.is_authenticated or not organization_id:
        return None
    m = OrganizationMembership.objects.filter(
        user=user, organization_id=organization_id
    ).first()
    return m.role if m else None


def _user_has_any_owner_membership(user):
    if not user or not user.is_authenticated:
        return False
    return OrganizationMembership.objects.filter(
        user=user, role=OrganizationMembership.Role.OWNER
    ).exists()


def _user_has_any_membership(user):
    if not user or not user.is_authenticated:
        return False
    return OrganizationMembership.objects.filter(user=user).exists()


class IsInventoryAdmin(BasePermission):
    """
    Owner-level access required. Used for write operations (create/update/delete).
    Object-level check additionally enforces that the object's organization
    matches one of the user's owner memberships.
    """
    message = "Inventory write access requires owner role in the organization."

    def has_permission(self, request, view):
        # For list/retrieve we check at queryset level; this gates writes.
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return _user_has_any_membership(request.user)
        return _user_has_any_owner_membership(request.user)

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        org_id = getattr(obj, 'organization_id', None)
        if not org_id:
            return False
        role = _user_role_in_org(request.user, org_id)
        if request.method in SAFE_METHODS:
            return role in (
                OrganizationMembership.Role.OWNER,
                OrganizationMembership.Role.MANAGER,
            )
        return role == OrganizationMembership.Role.OWNER


class IsInventoryReadOnly(BasePermission):
    """Read-only access for managers (and owners)."""
    message = "Inventory read access requires owner or manager role."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method not in SAFE_METHODS:
            return False
        return _user_has_any_membership(request.user)
