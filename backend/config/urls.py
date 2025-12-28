"""
URL configuration for AI Business Chat Platform.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path('admin/', admin.site.urls),

    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

    # API Endpoints
    path('api/auth/', include('apps.accounts.urls')),
    path('api/organizations/', include('apps.accounts.urls_organizations')),
    path('api/conversations/', include('apps.messaging.urls')),
    path('api/knowledge/', include('apps.knowledge.urls')),
    path('api/handoff/', include('apps.handoff.urls')),
    path('api/analytics/', include('apps.analytics.urls')),
    path('api/v1/widget/', include('apps.widget.urls')),
    
    # Vertical APIs (Phase 2 & 3)
    path('api/restaurant/', include('apps.restaurant.urls')),
    path('api/realestate/', include('apps.realestate.urls')),
]

# Serve static files (including widget.js)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
