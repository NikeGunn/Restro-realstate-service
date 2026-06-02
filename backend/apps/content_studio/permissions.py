"""
Content Studio permissions.

Composes the Phase 0 IsOrgMember (owner|manager read, owner write) with the
power-plan gate: Content Studio is a paid feature. The plan check uses
Organization.is_power_plan (already on the model). When Phase 6 lands, the
billing `enabled_modules` flag can be added here without touching callers.
"""
from rest_framework.permissions import BasePermission, SAFE_METHODS

from apps.common.permissions import (
    IsOrgMember, user_role_in_org, user_has_any_membership,
    user_has_any_owner_membership,
)
from apps.accounts.models import OrganizationMembership


def _org_is_power(user) -> bool:
    """True if the user belongs to at least one power-plan org."""
    org_ids = OrganizationMembership.objects.filter(
        user=user,
    ).values_list('organization_id', flat=True)
    from apps.accounts.models import Organization
    for org in Organization.objects.filter(id__in=list(org_ids)):
        if org.is_power_plan:
            return True
    return False


class ContentStudioPermission(BasePermission):
    """Owner|manager read, owner write — AND the org must be on the power plan."""
    message = 'AI Content Studio requires the Power plan.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            base = user_has_any_membership(request.user)
        else:
            base = user_has_any_owner_membership(request.user)
        return bool(base and _org_is_power(request.user))

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        # Resolve org directly, or via a parent job (outputs have no org FK).
        org = getattr(obj, 'organization', None)
        if org is None:
            job = getattr(obj, 'job', None)
            org = getattr(job, 'organization', None) if job else None
        org_id = getattr(org, 'id', None) or getattr(obj, 'organization_id', None)
        if not org_id:
            return False
        role = user_role_in_org(request.user, org_id)
        if org is not None and not org.is_power_plan:
            return False
        if request.method in SAFE_METHODS:
            return role in (
                OrganizationMembership.Role.OWNER,
                OrganizationMembership.Role.MANAGER,
            )
        return role == OrganizationMembership.Role.OWNER


# Read-only catalog (use cases) is visible to any authenticated member, no plan gate
# (so the home grid can render even on basic, with the generate button gated).
ContentStudioCatalogPermission = IsOrgMember
