"""Content Studio URLs (mounted at /api/v1/content-studio/)."""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    ContentUseCaseViewSet, BrandKitViewSet,
    ContentGenerationJobViewSet, ContentGenerationOutputViewSet,
)

app_name = 'content_studio'

router = DefaultRouter()
router.register(r'use-cases', ContentUseCaseViewSet, basename='use-case')
router.register(r'brand-kits', BrandKitViewSet, basename='brand-kit')
router.register(r'jobs', ContentGenerationJobViewSet, basename='generation-job')
router.register(r'outputs', ContentGenerationOutputViewSet, basename='generation-output')

urlpatterns = [
    path('', include(router.urls)),
]
