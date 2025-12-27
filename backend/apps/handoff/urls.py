"""
Handoff URL patterns.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import HandoffAlertViewSet, EscalationRuleViewSet

router = DefaultRouter()
router.register('alerts', HandoffAlertViewSet, basename='handoff-alert')
router.register('rules', EscalationRuleViewSet, basename='escalation-rule')

urlpatterns = [
    path('', include(router.urls)),
]
