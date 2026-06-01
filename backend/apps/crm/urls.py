"""CRM URL routing (Phase 1) — mounted at /api/v1/crm/."""
from rest_framework.routers import DefaultRouter

from .views import (
    CRMCustomerViewSet, CRMTagViewSet, CRMInteractionViewSet,
    CRMConsentViewSet, CRMSegmentViewSet,
)

router = DefaultRouter()
router.register('customers', CRMCustomerViewSet, basename='crm-customer')
router.register('tags', CRMTagViewSet, basename='crm-tag')
router.register('interactions', CRMInteractionViewSet, basename='crm-interaction')
router.register('consents', CRMConsentViewSet, basename='crm-consent')
router.register('segments', CRMSegmentViewSet, basename='crm-segment')

urlpatterns = router.urls
