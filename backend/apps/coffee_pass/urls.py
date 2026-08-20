"""
Authenticated Coffee Pass API — mounted at /api/v1/coffee-pass/.

Public customer routes live in public_urls.py under /public/coffee-pass/ so the
two surfaces can never share authentication assumptions by accident.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AnalyticsAnomaliesView, AnalyticsSummaryView, CoffeeExperienceViewSet,
    CoffeePassPlanViewSet, CoffeePassPurchaseViewSet, CoffeePassRedemptionViewSet,
    CoffeePassViewSet, RedemptionCreateView, VerificationResolveView,
)

router = DefaultRouter()
router.register('plans', CoffeePassPlanViewSet, basename='coffee-pass-plan')
router.register('passes', CoffeePassViewSet, basename='coffee-pass-pass')
router.register('purchases', CoffeePassPurchaseViewSet, basename='coffee-pass-purchase')
router.register('experiences', CoffeeExperienceViewSet, basename='coffee-pass-experience')
router.register('redemptions', CoffeePassRedemptionViewSet, basename='coffee-pass-redemption')

urlpatterns = [
    # Till operations are plain APIViews (manager-allowed POSTs), so they are
    # declared before the router to keep their paths unambiguous.
    path('verification/resolve/', VerificationResolveView.as_view(),
         name='coffee-pass-verification-resolve'),
    path('redemptions/create/', RedemptionCreateView.as_view(),
         name='coffee-pass-redemption-create'),
    path('analytics/summary/', AnalyticsSummaryView.as_view(),
         name='coffee-pass-analytics-summary'),
    path('analytics/anomalies/', AnalyticsAnomaliesView.as_view(),
         name='coffee-pass-analytics-anomalies'),
    path('', include(router.urls)),
]
