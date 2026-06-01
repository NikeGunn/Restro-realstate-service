"""
Throttling tests (Phase 0).

Verifies the public_form scope blocks the 11th request in a minute (rate
'10/min') against an unauthenticated AllowAny view using PublicFormThrottle.
"""
import pytest
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from apps.common.throttling import PublicFormThrottle, PublicBurstThrottle

pytestmark = pytest.mark.django_db


class _PublicFormView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = [PublicFormThrottle]

    def post(self, request):
        return Response({'ok': True})


factory = APIRequestFactory()


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    # Throttle history lives in the cache; clear so test order doesn't matter.
    from django.core.cache import cache
    cache.clear()
    yield
    cache.clear()


def test_public_form_blocks_eleventh_request(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        'DEFAULT_THROTTLE_RATES': {'public_form': '10/min', 'public_burst': '60/min',
                                   'public_sustained': '600/hour'},
    }
    view = _PublicFormView.as_view()
    statuses = []
    for _ in range(11):
        request = factory.post('/public/x/', {})
        request.META['REMOTE_ADDR'] = '203.0.113.7'
        statuses.append(view(request).status_code)

    assert statuses[:10] == [200] * 10
    assert statuses[10] == 429  # throttled


def test_scopes_are_named_correctly():
    assert PublicFormThrottle.scope == 'public_form'
    assert PublicBurstThrottle.scope == 'public_burst'


def test_distinct_ips_not_throttled_together(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        'DEFAULT_THROTTLE_RATES': {'public_form': '10/min', 'public_burst': '60/min',
                                   'public_sustained': '600/hour'},
    }
    view = _PublicFormView.as_view()
    # Two different IPs each make 6 requests -> none throttled (limit is per-IP).
    for ip in ('198.51.100.1', '198.51.100.2'):
        for _ in range(6):
            request = factory.post('/public/x/', {})
            request.META['REMOTE_ADDR'] = ip
            assert view(request).status_code == 200
