"""
Custom permissions for accounts app.
"""
from rest_framework import permissions
from .models import OrganizationMembership


class IsOrganizationMember(permissions.BasePermission):
    """
    Check if user is a member of the organization.
    """
    def has_permission(self, request, view):
        org_id = view.kwargs.get('organization_pk') or view.kwargs.get('pk')
        if not org_id:
            return True
        return OrganizationMembership.objects.filter(
            user=request.user,
            organization_id=org_id
        ).exists()


class IsOrganizationOwner(permissions.BasePermission):
    """
    Check if user is an owner of the organization.
    """
    def has_permission(self, request, view):
        org_id = view.kwargs.get('organization_pk') or view.kwargs.get('pk')
        if not org_id:
            return True
        return OrganizationMembership.objects.filter(
            user=request.user,
            organization_id=org_id,
            role=OrganizationMembership.Role.OWNER
        ).exists()


class HasLocationAccess(permissions.BasePermission):
    """
    Check if user has access to a specific location.
    """
    def has_object_permission(self, request, view, obj):
        membership = OrganizationMembership.objects.filter(
            user=request.user,
            organization=obj.organization
        ).first()
        if not membership:
            return False
        return membership.has_location_access(obj)
