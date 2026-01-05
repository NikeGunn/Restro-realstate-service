"""
Channel URL patterns.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    WhatsAppWebhookView,
    InstagramWebhookView,
    WhatsAppConfigViewSet,
    InstagramConfigViewSet,
    WebhookLogViewSet
)

router = DefaultRouter()
router.register('whatsapp-config', WhatsAppConfigViewSet, basename='whatsapp-config')
router.register('instagram-config', InstagramConfigViewSet, basename='instagram-config')
router.register('webhook-logs', WebhookLogViewSet, basename='webhook-logs')

urlpatterns = [
    path('', include(router.urls)),
]

# Webhook URLs (separate, no auth required)
webhook_urlpatterns = [
    path('whatsapp/', WhatsAppWebhookView.as_view(), name='whatsapp-webhook'),
    path('instagram/', InstagramWebhookView.as_view(), name='instagram-webhook'),
]
