"""Regression: media files must be served by Django (via /media/) even when
DEBUG=False, as long as we're on local FileSystemStorage (USE_OBJECT_STORAGE
=false / media-pvc).

This is the bug behind the production "404 Not Found nginx" on Content Studio
images and brand-kit logos: the old urls.py only registered the /media/ route
under `if settings.DEBUG`, so prod (DEBUG=False) had no handler at all.

We assert at the URL-resolution layer (does a /media/<path> route exist and
point at the static `serve` view?). urls.py builds its patterns at import time
off settings, so we reload it under overridden settings, clear the resolver
cache, resolve, then restore — leaving no state behind for the rest of the suite.
"""
import importlib

import pytest
from django.test.utils import override_settings
from django.urls import clear_url_caches, resolve
from django.views.static import serve


def _media_route_targets_serve():
    import config.urls
    importlib.reload(config.urls)
    clear_url_caches()
    try:
        match = resolve('/media/content_studio/demo.png')
    except Exception:
        return False
    return match.func is serve


def _restore_urlconf():
    import config.urls
    importlib.reload(config.urls)
    clear_url_caches()


@pytest.mark.django_db
def test_media_route_registered_when_debug_false_local_storage():
    with override_settings(DEBUG=False, USE_OBJECT_STORAGE=False,
                           ROOT_URLCONF='config.urls'):
        served = _media_route_targets_serve()
    _restore_urlconf()
    assert served, (
        '/media/ is not served by Django under DEBUG=False — this is the '
        'production 404 regression (urls.py gated the route behind DEBUG).'
    )


@pytest.mark.django_db
def test_media_route_skipped_when_object_storage():
    """When USE_OBJECT_STORAGE=true, files are served from S3/CDN, so the local
    /media/ serve route should NOT be registered (it falls through to the SPA)."""
    with override_settings(DEBUG=False, USE_OBJECT_STORAGE=True,
                           ROOT_URLCONF='config.urls'):
        served = _media_route_targets_serve()
    _restore_urlconf()
    assert not served
