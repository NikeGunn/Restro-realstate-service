"""Public listings site — mounted at /realestate/properties/ (see public_site.py)."""
from django.urls import path, re_path

from . import public_site

urlpatterns = [
    path('', public_site.listings, name='public-listings'),
    path('chat/', public_site.chat_needs, name='public-chat-needs'),
    re_path(r'^(?P<ref>[pP][rR][oO][pP]\d{6})/chat/$', public_site.chat_listing, name='public-chat-listing'),
    re_path(r'^(?P<ref_slug>[pP][rR][oO][pP]\d{6}(?:-[a-z0-9-]*)?)/$', public_site.detail, name='public-listing'),
    path('<slug:category>/', public_site.listings, name='public-category'),
    path('<slug:category>/<slug:city>/', public_site.listings, name='public-category-city'),
]
