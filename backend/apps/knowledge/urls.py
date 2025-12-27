"""
Knowledge base URL patterns.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import KnowledgeBaseViewSet, FAQViewSet

router = DefaultRouter()
router.register('bases', KnowledgeBaseViewSet, basename='knowledge-base')
router.register('faqs', FAQViewSet, basename='faq')

urlpatterns = [
    path('', include(router.urls)),
]
