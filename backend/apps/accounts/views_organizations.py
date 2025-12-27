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

    def get_queryset(self):
        org_id = self.kwargs.get('organization_pk')
        return Location.objects.filter(organization_id=org_id)

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
