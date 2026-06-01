"""
Lucky Draw PUBLIC URLs (Phase 2) — mounted at /public/lucky-draw/ (no auth).

- GET  /public/lucky-draw/{url_token}/          -> entry page (HTML, customer-facing)
- GET  /public/lucky-draw/{url_token}/config/   -> JSON campaign config
- POST /public/lucky-draw/{url_token}/enter/    -> JSON enter pipeline
"""
from django.urls import path

from .public_views import PublicCampaignConfigView, PublicEntryView
from .template_views import public_entry_page

urlpatterns = [
    path('<str:url_token>/', public_entry_page, name='lucky-draw-entry-page'),
    path('<str:url_token>/config/', PublicCampaignConfigView.as_view(), name='lucky-draw-config'),
    path('<str:url_token>/enter/', PublicEntryView.as_view(), name='lucky-draw-enter'),
]
