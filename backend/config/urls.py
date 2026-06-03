"""
URL configuration for AI Business Chat Platform.
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from django.http import JsonResponse
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

# Import webhook URLs
from apps.channels.urls import webhook_urlpatterns


def health_check(request):
    """Health check endpoint for container orchestration."""
    import os
    return JsonResponse({
        'status': 'healthy',
        'service': 'chatplatform-backend',
        'version': os.getenv('GIT_COMMIT', 'dev')[:7],
        'gitops': 'argocd',
        'deployment': 'kubernetes',
        'timestamp': __import__('datetime').datetime.utcnow().isoformat() + 'Z'
    })


urlpatterns = [
    # Health check endpoint
    path('api/health/', health_check, name='health-check'),

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
    path('api/coupons/', include('apps.coupons.urls')),

    # Vertical APIs (Phase 2 & 3)
    path('api/restaurant/', include('apps.restaurant.urls')),
    path('api/realestate/', include('apps.realestate.urls')),

    # Inventory (Plane B — admin-only)
    path('api/v1/inventory/', include('apps.inventory.urls')),

    # CRM Lite (Phase 1)
    path('api/v1/crm/', include('apps.crm.urls')),

    # Lucky Draw (Phase 2) — authenticated admin API
    path('api/v1/lucky_draw/', include('apps.lucky_draw.urls')),

    # Lucky Draw (Phase 2) — PUBLIC, no auth, throttled
    path('public/lucky-draw/', include('apps.lucky_draw.public_urls')),

    # AI Content Studio (Phase 5)
    path('api/v1/content-studio/', include('apps.content_studio.urls')),

    # AI Credit & Usage Billing (Phase 6)
    path('api/v1/billing/', include('apps.billing.urls')),

    # Payments (Stripe) — credit-pack purchases + webhook
    path('api/v1/payments/', include('apps.payments.urls')),

    # Channel configuration API (Phase 4)
    path('api/channels/', include('apps.channels.urls')),

    # Public webhook endpoints (no auth)
    path('api/webhooks/', include(webhook_urlpatterns)),
]

# Serve static files (including widget.js)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Serve user-uploaded / generated media (Content Studio images, brand-kit logos,
# lucky-draw QR/posters, inventory uploads). WhiteNoise only serves STATIC_ROOT,
# so when media lives on the local FileSystemStorage (media-pvc, i.e.
# USE_OBJECT_STORAGE=false) Django itself must serve /media/ — in prod too, not
# just under DEBUG. When USE_OBJECT_STORAGE=true the files are served from
# S3/CDN and this route is harmless (no local files to find).
if not settings.USE_OBJECT_STORAGE:
    media_prefix = settings.MEDIA_URL.lstrip('/')
    urlpatterns += [
        re_path(
            rf'^{media_prefix}(?P<path>.*)$',
            serve,
            {'document_root': settings.MEDIA_ROOT},
        ),
    ]
