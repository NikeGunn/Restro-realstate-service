"""
Showcase videos (product launches, feature films) uploaded by a superuser in Django admin and
played on kribaat.com and the public property site.

Files live in the same storage as listing photos (Cloudflare R2 in prod, the media volume
locally) under `showcase/<random>.<ext>`; prod serves them from media.kribaat.com/showcase/
with HTTP range support (views.video), so seeking works on iPhone/Safari.
"""
import os
import uuid

from django.core.exceptions import ValidationError
from django.db import models

from apps.realestate.photo_storage import photo_storage

# The edge proxy accepts request bodies up to 50 MB; keep a margin for the multipart form.
MAX_VIDEO_BYTES = 48 * 1024 * 1024
MAX_POSTER_BYTES = 5 * 1024 * 1024
VIDEO_TYPES = {'.mp4': 'video/mp4', '.webm': 'video/webm', '.mov': 'video/quicktime'}
POSTER_TYPES = {'.jpg', '.jpeg', '.png', '.webp'}


def _video_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f"showcase/{uuid.uuid4().hex}{ext}"


def _poster_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower().replace('.jpeg', '.jpg')
    return f"showcase/{uuid.uuid4().hex}{ext}"


def validate_video(f):
    ext = os.path.splitext(f.name)[1].lower()
    if ext not in VIDEO_TYPES:
        raise ValidationError('Upload an MP4 (H.264), WebM or MOV file.')
    if f.size > MAX_VIDEO_BYTES:
        raise ValidationError(f'Videos can be at most {MAX_VIDEO_BYTES // (1024 * 1024)} MB '
                              f'(this one is {f.size / (1024 * 1024):.1f} MB). Export at 1080p H.264 ~5 Mbps.')
    head = f.read(16)
    f.seek(0)
    # MP4/MOV carry 'ftyp' at byte 4; WebM starts with the EBML magic. Rejects renamed files.
    if not (head[4:8] == b'ftyp' or head[:4] == b'\x1a\x45\xdf\xa3'):
        raise ValidationError('That file is not a playable video.')


def validate_poster(f):
    if os.path.splitext(f.name)[1].lower() not in POSTER_TYPES:
        raise ValidationError('Use a JPG, PNG or WebP image.')
    if f.size > MAX_POSTER_BYTES:
        raise ValidationError('The cover image can be at most 5 MB.')


class ShowcaseVideo(models.Model):
    class Placement(models.TextChoices):
        LANDING = 'landing', 'kribaat.com landing page'
        PROPERTIES = 'properties', 'Property site (kribaat.com/realestate/properties)'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=120, help_text='Shown above the video, e.g. "Meet the Kribaat agent".')
    caption = models.CharField(max_length=240, blank=True, help_text='One line under the title.')
    video = models.FileField(upload_to=_video_path, storage=photo_storage, validators=[validate_video],
                             help_text='MP4 (H.264) recommended, up to 48 MB.')
    poster = models.FileField(upload_to=_poster_path, storage=photo_storage, validators=[validate_poster], blank=True,
                              help_text='Optional cover image shown before playback (16:9).')
    placement = models.CharField(max_length=20, choices=Placement.choices, default=Placement.LANDING)
    is_active = models.BooleanField(default=True, help_text='Only active videos are shown publicly.')
    sort_order = models.PositiveSmallIntegerField(default=0, help_text='Lower shows first.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['placement', 'sort_order', '-created_at']

    def __str__(self):
        return self.title

    @property
    def content_type(self) -> str:
        return VIDEO_TYPES.get(os.path.splitext(self.video.name)[1].lower(), 'video/mp4')

    @classmethod
    def public(cls, placement: str):
        return cls.objects.filter(placement=placement, is_active=True)
