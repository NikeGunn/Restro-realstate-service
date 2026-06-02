"""
Persist generated images to Django's default storage (S3 when
USE_OBJECT_STORAGE=true, else the media-pvc). ALWAYS called immediately after
generation — provider temp URLs expire ~1h, so we never store a provider URL
as the canonical asset.

Generates a 512px thumbnail and records dimensions/format. Pure-enough to test
with a tiny in-memory PNG.
"""
import io
import logging

from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)

THUMB_MAX = 512


def _open_image(raw: bytes):
    from PIL import Image
    return Image.open(io.BytesIO(raw))


def download_and_store(raw: bytes, job, index: int, provider_asset_id: str = ''):
    """
    Persist one image to a ContentGenerationOutput row.

    `raw` is the image bytes (the provider service already decoded base64).
    Returns the saved ContentGenerationOutput.
    """
    from apps.content_studio.models import ContentGenerationOutput

    width = height = 0
    fmt = 'PNG'
    thumb_bytes = None
    try:
        img = _open_image(raw)
        width, height = img.size
        fmt = (img.format or 'PNG').upper()
        thumb = img.copy()
        thumb.thumbnail((THUMB_MAX, THUMB_MAX))
        buf = io.BytesIO()
        # Thumbnails are always PNG for consistency.
        thumb.convert('RGB').save(buf, format='PNG')
        thumb_bytes = buf.getvalue()
    except Exception:
        # Never lose the original asset because thumbnailing failed.
        logger.exception('Thumbnail/inspect failed for job %s index %s', job.id, index)

    output = ContentGenerationOutput(
        job=job,
        width=width,
        height=height,
        format=fmt,
        file_type=f'image/{fmt.lower()}',
        provider_asset_id=provider_asset_id or '',
    )
    base = f'{job.organization_id}/{job.id}/{index}'
    output.asset.save(f'{base}.png', ContentFile(raw), save=False)
    if thumb_bytes is not None:
        output.thumbnail.save(f'{base}_thumb.png', ContentFile(thumb_bytes), save=False)
    output.save()
    return output
