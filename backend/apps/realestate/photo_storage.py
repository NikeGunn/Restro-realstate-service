"""
Listing photos: upload → validate → re-encode → store → public URL.

Storage: Cloudflare R2 when R2_* settings are present (public bucket / custom domain, so
WhatsApp can fetch images by link); otherwise Django's default storage (media-pvc, served
at PUBLIC_BASE_URL/media/). Photos have their own storage on purpose — flipping it never
moves other apps' media (content studio, QR posters).

Every image is decoded and re-encoded as JPEG: that rejects non-images and polyglot files,
strips EXIF (phones embed GPS — a landlord's home location must not leak), and caps size.
"""
import io
import logging
import uuid
from typing import Optional

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_EDGE_PX = 1600
MAX_PHOTOS_PER_LISTING = 15
ALLOWED_FORMATS = {'JPEG', 'PNG', 'WEBP'}


class PhotoError(ValueError):
    pass


def r2_configured() -> bool:
    return all(getattr(settings, k, '') for k in ('R2_BUCKET', 'R2_ENDPOINT_URL', 'R2_ACCESS_KEY_ID',
                                                  'R2_SECRET_ACCESS_KEY', 'R2_PUBLIC_DOMAIN'))


_r2 = None


def photo_storage():
    global _r2
    if not r2_configured():
        return default_storage
    if _r2 is None:
        from storages.backends.s3 import S3Storage
        _r2 = S3Storage(
            bucket_name=settings.R2_BUCKET, endpoint_url=settings.R2_ENDPOINT_URL, region_name='auto',
            access_key=settings.R2_ACCESS_KEY_ID, secret_key=settings.R2_SECRET_ACCESS_KEY,
            custom_domain=settings.R2_PUBLIC_DOMAIN, querystring_auth=False, file_overwrite=False,
            signature_version='s3v4', default_acl=None,
            object_parameters={'CacheControl': 'public, max-age=31536000, immutable'},
        )
    return _r2


def _absolute(url: str) -> str:
    if url.startswith('http'):
        return url
    return settings.PUBLIC_BASE_URL.rstrip('/') + '/' + url.lstrip('/')


def _reencode(upload) -> bytes:
    from PIL import Image, ImageOps, UnidentifiedImageError

    if upload.size > MAX_UPLOAD_BYTES:
        raise PhotoError('Photo is larger than 10 MB.')
    try:
        img = Image.open(upload)
        if img.format not in ALLOWED_FORMATS:
            raise PhotoError('Use a JPG, PNG or WebP photo.')
        img = ImageOps.exif_transpose(img)        # keep phone orientation, then drop EXIF
        img = img.convert('RGB')
        img.thumbnail((MAX_EDGE_PX, MAX_EDGE_PX))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise PhotoError('That file is not a readable image.')
    out = io.BytesIO()
    img.save(out, format='JPEG', quality=85, optimize=True)
    return out.getvalue()


def _locked(listing):
    """Re-read the listing under a row lock: two uploads at once must not drop each other's photo."""
    return type(listing).objects.select_for_update().get(pk=listing.pk)


def add_photo(listing, upload) -> str:
    if len(listing.images or []) >= MAX_PHOTOS_PER_LISTING:
        raise PhotoError(f'A listing can have at most {MAX_PHOTOS_PER_LISTING} photos.')
    data = _reencode(upload)
    name = f"listings/{listing.organization_id}/{listing.id}/{uuid.uuid4().hex}.jpg"
    storage = photo_storage()
    saved = storage.save(name, ContentFile(data))
    url = _absolute(storage.url(saved))
    with transaction.atomic():
        row = _locked(listing)
        images = list(row.images or [])
        if len(images) >= MAX_PHOTOS_PER_LISTING:
            _delete_quietly(saved)
            raise PhotoError(f'A listing can have at most {MAX_PHOTOS_PER_LISTING} photos.')
        row.images = images + [url]
        row.save(update_fields=['images', 'updated_at'])
    listing.images = row.images
    return url


def _delete_quietly(key: str):
    try:
        photo_storage().delete(key)
    except Exception:
        logger.exception("Could not delete photo object %s (listing updated anyway)", key)


def remove_photo(listing, url: str) -> bool:
    with transaction.atomic():
        row = _locked(listing)
        images = list(row.images or [])
        if url not in images:
            listing.images = images
            return False
        row.images = [u for u in images if u != url]
        row.save(update_fields=['images', 'updated_at'])
    listing.images = row.images
    key = _key_from_url(listing, url)
    if key:
        _delete_quietly(key)
    return True


def reorder_photos(listing, urls) -> list:
    """Save a new photo order (the first is the cover). Must be exactly the current photos."""
    with transaction.atomic():
        row = _locked(listing)
        current = list(row.images or [])
        if not isinstance(urls, list) or sorted(map(str, urls)) != sorted(current):
            raise PhotoError("The new order must contain exactly the listing's current photos.")
        row.images = list(urls)
        row.save(update_fields=['images', 'updated_at'])
    listing.images = row.images
    return listing.images


def _key_from_url(listing, url: str) -> Optional[str]:
    marker = f"listings/{listing.organization_id}/{listing.id}/"
    i = url.find(marker)
    return url[i:].split('?')[0] if i != -1 else None
