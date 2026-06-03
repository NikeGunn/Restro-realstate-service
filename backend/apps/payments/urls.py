"""Payments URLs (mounted at /api/v1/payments/)."""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    StripeConfigView, CreditPackViewSet, CreateCheckoutSessionView,
    StripeWebhookView, CreditPurchaseViewSet, RefundView,
)

app_name = 'payments'

router = DefaultRouter()
router.register(r'packs', CreditPackViewSet, basename='credit-pack')
router.register(r'purchases', CreditPurchaseViewSet, basename='credit-purchase')

urlpatterns = [
    path('config/', StripeConfigView.as_view(), name='stripe-config'),
    path('checkout/', CreateCheckoutSessionView.as_view(), name='create-checkout'),
    path('refund/', RefundView.as_view(), name='refund'),
    # Webhook — public, signature-verified (no auth, CSRF-exempt).
    path('webhook/', StripeWebhookView.as_view(), name='stripe-webhook'),
    path('', include(router.urls)),
]
