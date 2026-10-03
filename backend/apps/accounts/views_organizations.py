"""
Organization views for API.
"""
from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.viewsets import ModelViewSet

from .models import Organization, Location, OrganizationMembership
from .serializers import (
    OrganizationSerializer,
    OrganizationCreateSerializer,
    LocationSerializer,
    LocationCreateSerializer,
    OrganizationMembershipSerializer,
    OrganizationMembershipCreateSerializer,
)
from .permissions import IsOrganizationMember, IsOrganizationOwner


class OrganizationViewSet(ModelViewSet):
    """
    ViewSet for managing organizations.
    """
    permission_classes = [permissions.IsAuthenticated]
    # Deleting a tenant cascades every row it owns — admin-only, never via the API.
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']

    def get_permissions(self):
        # Managers can read the org; only owners may change it.
        if self.action in ('update', 'partial_update'):
            return [permissions.IsAuthenticated(), IsOrganizationOwner()]
        return super().get_permissions()

    def get_queryset(self):
        """Return organizations user is a member of."""
        return Organization.objects.filter(
            memberships__user=self.request.user
        ).distinct()

    def get_serializer_class(self):
        if self.action == 'create':
            return OrganizationCreateSerializer
        return OrganizationSerializer

    def perform_create(self, serializer):
        """Create organization and add user as owner."""
        org = serializer.save()
        # Add creator as owner
        OrganizationMembership.objects.create(
            user=self.request.user,
            organization=org,
            role=OrganizationMembership.Role.OWNER
        )
        # Create default location
        Location.objects.create(
            organization=org,
            name='Main Location',
            is_primary=True
        )


class LocationViewSet(ModelViewSet):
    """
    ViewSet for managing locations within an organization.
    """
    permission_classes = [permissions.IsAuthenticated, IsOrganizationMember]

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [permissions.IsAuthenticated(), IsOrganizationOwner()]
        return super().get_permissions()

    def get_queryset(self):
        org_id = self.kwargs.get('organization_pk')
        # Removed locations are soft-deleted (is_active=False) and hidden.
        return Location.objects.filter(organization_id=org_id, is_active=True)

    def perform_destroy(self, instance):
        """
        Soft-delete. Listings, leads, appointments and knowledge FK to Location with
        CASCADE, so a hard delete would silently wipe a branch's business data.
        """
        from rest_framework.exceptions import ValidationError

        if instance.is_primary:
            raise ValidationError({'error': 'The primary location cannot be removed. Make another location primary first.'})
        if not Location.objects.filter(organization=instance.organization, is_active=True).exclude(pk=instance.pk).exists():
            raise ValidationError({'error': 'An organization needs at least one location.'})
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_at'])

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return LocationCreateSerializer
        return LocationSerializer

    def perform_create(self, serializer):
        org_id = self.kwargs.get('organization_pk')
        org = Organization.objects.get(pk=org_id)

        # Check plan limits
        if not org.is_power_plan:
            if org.locations.filter(is_active=True).count() >= 1:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied('Basic plan allows only 1 location. Upgrade to Power plan.')

        serializer.save(organization=org)


class OrganizationMembershipViewSet(ModelViewSet):
    """
    ViewSet for managing organization memberships.
    """
    permission_classes = [permissions.IsAuthenticated, IsOrganizationOwner]

    def get_queryset(self):
        org_id = self.kwargs.get('organization_pk')
        return OrganizationMembership.objects.filter(organization_id=org_id)

    def get_serializer_class(self):
        if self.action == 'create':
            return OrganizationMembershipCreateSerializer
        return OrganizationMembershipSerializer

    def perform_create(self, serializer):
        org_id = self.kwargs.get('organization_pk')
        org = Organization.objects.get(pk=org_id)
        serializer.save(organization=org)
