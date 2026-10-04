"""
media.kribaat.com: listing photos served from the private R2 S3 API through our ingress.

Why not r2.dev: it is rate-limited and Cloudflare says it is not for production. Why not an
R2 custom domain: kribaat.com's DNS zone lives in a different Cloudflare account, so the bucket
cannot bind it. The A record media.kribaat.com → our server is in place, so the backend streams
objects with the authenticated S3 API (no rate limit) and long immutable cache headers.

Only `listings/<org>/<listing>/<hex>.jpg` keys are served (the names photo_storage creates), so
the endpoint can never be used to read anything else from the bucket. Objects are immutable
(random names, never overwritten): a hot object is cached in Redis for a day.
"""
import logging
import re

from django.core.cache import cache
from django.http import Http404, HttpResponse, HttpResponseNotModified
from django.views.decorators.http import require_http_methods

from .photo_storage import photo_storage, r2_configured

logger = logging.getLogger(__name__)

KEY_RE = re.compile(r'^listings/[0-9a-f-]{36}/[0-9a-f-]{36}/[0-9a-f]{32}\.jpg$')
CACHE_SECONDS = 24 * 3600
MAX_CACHED_BYTES = 2 * 1024 * 1024
IMMUTABLE = 'public, max-age=31536000, immutable'


@require_http_methods(['GET', 'HEAD'])
def listing_photo(request, key: str):
    key = f'listings/{key}'
    if not KEY_RE.match(key):
        raise Http404()
    etag = '"' + key.rsplit('/', 1)[-1][:-4] + '"'      # the random name is a stable validator
    if request.headers.get('If-None-Match') == etag:
        resp = HttpResponseNotModified()
        resp['ETag'], resp['Cache-Control'] = etag, IMMUTABLE
        return resp

    cache_key = f'media:{key}'
    data = cache.get(cache_key)
    if data is None:
        storage = photo_storage()
        try:
            with storage.open(key, 'rb') as fh:
                data = fh.read()
        except FileNotFoundError:
            raise Http404()
        except Exception as e:
            # S3 "NoSuchKey"/404 arrives as a botocore ClientError
            if '404' in str(e) or 'NoSuchKey' in str(e) or 'Not Found' in str(e):
                raise Http404()
            logger.exception("Photo fetch failed for %s (r2=%s)", key, r2_configured())
            return HttpResponse(status=502)
        if len(data) <= MAX_CACHED_BYTES:
            cache.set(cache_key, data, CACHE_SECONDS)

    resp = HttpResponse(b'' if request.method == 'HEAD' else data, content_type='image/jpeg')
    resp['Content-Length'] = str(len(data))
    resp['Cache-Control'] = IMMUTABLE
    resp['ETag'] = etag
    resp['X-Content-Type-Options'] = 'nosniff'
    resp['Access-Control-Allow-Origin'] = '*'
    return resp
