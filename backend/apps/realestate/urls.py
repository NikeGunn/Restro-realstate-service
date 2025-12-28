"""
Real Estate Vertical URLs.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    PropertyListingViewSet, LeadViewSet, AppointmentViewSet,
    PublicPropertySearchView, PublicPropertyDetailView, PublicLeadCaptureView
)

app_name = 'realestate'

router = DefaultRouter()
router.register(r'properties', PropertyListingViewSet, basename='property-listing')
router.register(r'leads', LeadViewSet, basename='lead')
router.register(r'appointments', AppointmentViewSet, basename='appointment')

urlpatterns = [
    path('', include(router.urls)),
    # Public endpoints (for widget)
    path('public/properties/', PublicPropertySearchView.as_view(), name='public-properties'),
    path('public/properties/<uuid:property_id>/', PublicPropertyDetailView.as_view(), name='public-property-detail'),
    path('public/leads/capture/', PublicLeadCaptureView.as_view(), name='public-lead-capture'),
]
