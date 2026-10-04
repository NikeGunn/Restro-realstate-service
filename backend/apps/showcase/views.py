"""
GET /api/public/showcase/?placement=landing  → active videos (JSON, no auth)
GET media.kribaat.com/showcase/<hex>.<ext>   → the file from R2, with HTTP Range (206) support
"""
import re

from django.http import Http404, HttpResponse, JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_GET, require_http_methods

from apps.realestate.photo_storage import photo_storage, r2_configured

from .models import VIDEO_TYPES, ShowcaseVideo

KEY_RE = re.compile(r'^showcase/[0-9a-f]{32}\.(mp4|webm|mov|jpg|png|webp)$')
RANGE_RE = re.compile(r'^bytes=(\d*)-(\d*)$')
CHUNK = 512 * 1024
IMMUTABLE = 'public, max-age=31536000, immutable'
TYPES = {**VIDEO_TYPES, '.jpg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}


@require_GET
def public_videos(request):
    placement = request.GET.get('placement', ShowcaseVideo.Placement.LANDING)
    if placement not in ShowcaseVideo.Placement.values:
        return JsonResponse({'error': 'unknown placement'}, status=400)
    absolute = request.build_absolute_uri    # the landing page lives on another origin in dev
    rows = [{
        'id': str(v.id), 'title': v.title, 'caption': v.caption, 'video_url': absolute(v.video.url),
        'type': v.content_type, 'poster_url': absolute(v.poster.url) if v.poster else '',
    } for v in ShowcaseVideo.public(placement)]
    resp = JsonResponse({'videos': rows})
    resp['Cache-Control'] = 'public, max-age=120'
    resp['Access-Control-Allow-Origin'] = '*'
    return resp


@require_http_methods(['GET', 'HEAD'])
def media(request, name: str):
    """Stream a showcase file from storage. Only keys showcase_video creates are served."""
    key = f'showcase/{name}'
    if not KEY_RE.match(key):
        raise Http404()
    storage = photo_storage()
    ext = '.' + key.rsplit('.', 1)[-1]
    ctype = TYPES[ext]
    if not r2_configured():  # local / PVC storage
        try:
            fh = storage.open(key, 'rb')
        except FileNotFoundError:
            raise Http404()
        size = storage.size(key)
        return _respond(request, size, ctype, lambda start, end: _file_iter(fh, start, end))

    client = storage.connection.meta.client
    bucket = storage.bucket_name
    try:
        head = client.head_object(Bucket=bucket, Key=key)
    except Exception:
        raise Http404()
    size = head['ContentLength']

    def body(start, end):
        obj = client.get_object(Bucket=bucket, Key=key, Range=f'bytes={start}-{end}')
        return obj['Body'].iter_chunks(CHUNK)

    return _respond(request, size, ctype, body)


def _file_iter(fh, start, end):
    fh.seek(start)
    left = end - start + 1
    while left > 0:
        chunk = fh.read(min(CHUNK, left))
        if not chunk:
            break
        left -= len(chunk)
        yield chunk
    fh.close()


def _respond(request, size, ctype, body):
    etag = '"' + request.path.rsplit('/', 1)[-1].split('.')[0] + '"'
    start, end, status = 0, size - 1, 200
    m = RANGE_RE.match(request.headers.get('Range', ''))
    if m and (m.group(1) or m.group(2)):
        if m.group(1):
            start = int(m.group(1))
            end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
        else:                                   # "bytes=-500": the last 500 bytes
            start = max(0, size - int(m.group(2)))
        if start > end or start >= size:
            resp = HttpResponse(status=416)
            resp['Content-Range'] = f'bytes */{size}'
            return resp
        status = 206
    if request.method == 'HEAD':
        resp = HttpResponse(status=status, content_type=ctype)
    else:
        resp = StreamingHttpResponse(body(start, end), status=status, content_type=ctype)
    resp['Content-Length'] = str(end - start + 1)
    if status == 206:
        resp['Content-Range'] = f'bytes {start}-{end}/{size}'
    resp['Accept-Ranges'] = 'bytes'
    resp['Cache-Control'] = IMMUTABLE
    resp['ETag'] = etag
    resp['X-Content-Type-Options'] = 'nosniff'
    resp['Access-Control-Allow-Origin'] = '*'
    return resp

