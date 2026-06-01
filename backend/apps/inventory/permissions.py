"""
Inventory permissions — Plane B is admin-only.

As of Phase 0 the role logic was promoted to `apps.common.permissions`
(`IsOrgMember` / `IsOrgOwner`). The inventory classes are kept as thin
subclasses so existing imports and behavior are unchanged:

    IsInventoryAdmin     -> owner write / owner|manager read  (== IsOrgMember)
    IsInventoryReadOnly  -> read-only for owner|manager

Roles live on apps.accounts.OrganizationMembership.role with choices
('owner', 'manager'). There is no separate 'admin' role.
"""
from rest_framework.permissions import BasePermission, SAFE_METHODS

from apps.common.permissions import (
    IsOrgMember,
    user_role_in_org,
    user_has_any_owner_membership,
    user_has_any_membership,
)

# Re-export the helpers under their original private names so any existing
# imports keep working.
_user_role_in_org = user_role_in_org
_user_has_any_owner_membership = user_has_any_owner_membership
_user_has_any_membership = user_has_any_membership


class IsInventoryAdmin(IsOrgMember):
    """
    Owner-level write, owner|manager read — identical to the shared IsOrgMember.
    Kept as a named subclass for import stability and a clearer message.
    """
    message = "Inventory write access requires owner role in the organization."


class IsInventoryReadOnly(BasePermission):
    """Read-only access for managers (and owners)."""
    message = "Inventory read access requires owner or manager role."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method not in SAFE_METHODS:
            return False
        return user_has_any_membership(request.user)
