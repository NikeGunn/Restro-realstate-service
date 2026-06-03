"""Billing URLs (mounted at /api/v1/billing/)."""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    CreditBalanceView, UsageSummaryView, UsageLimitView,
    UsageEventViewSet, MonthlyUsageSummaryViewSet,
)

app_name = 'billing'

router = DefaultRouter()
router.register(r'usage-events', UsageEventViewSet, basename='usage-event')
router.register(r'monthly-summaries', MonthlyUsageSummaryViewSet, basename='monthly-summary')

urlpatterns = [
    path('balance/', CreditBalanceView.as_view(), name='credit-balance'),
    path('summary/', UsageSummaryView.as_view(), name='usage-summary'),
    path('limit/', UsageLimitView.as_view(), name='usage-limit'),
    path('', include(router.urls)),
]
