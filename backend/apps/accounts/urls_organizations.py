"""
Organization URL patterns.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers

from .views_organizations import (
    OrganizationViewSet,
    LocationViewSet,
    OrganizationMembershipViewSet,
)

# Main router for organizations
router = DefaultRouter()
router.register('', OrganizationViewSet, basename='organization')

# Nested router for locations and memberships
organizations_router = routers.NestedDefaultRouter(router, '', lookup='organization')
organizations_router.register('locations', LocationViewSet, basename='organization-locations')
organizations_router.register('members', OrganizationMembershipViewSet, basename='organization-members')

urlpatterns = [
    path('', include(router.urls)),
    path('', include(organizations_router.urls)),
]
