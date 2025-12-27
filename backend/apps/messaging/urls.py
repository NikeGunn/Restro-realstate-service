"""
Messaging URL patterns.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers

from .views import ConversationViewSet, MessageViewSet

router = DefaultRouter()
router.register('', ConversationViewSet, basename='conversation')

# Nested router for messages
conversations_router = routers.NestedDefaultRouter(router, '', lookup='conversation')
conversations_router.register('messages', MessageViewSet, basename='conversation-messages')

urlpatterns = [
    path('', include(router.urls)),
    path('', include(conversations_router.urls)),
]
