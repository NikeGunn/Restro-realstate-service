"""
Django-admin photo manager for listings: drag & drop upload, drag to reorder, remove.

Uploads go through the same pipeline as the dashboard (photo_storage: decode → re-encode JPEG →
strip EXIF/GPS → R2), so a photo added in /admin is exactly as safe as one added in the app.
Files are validated in the form (size, type, readable image, 15-photo limit) so a bad file is a
normal form error, never a half-saved listing.
"""
import json

from django import forms
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

from . import photo_storage


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleFileInput(attrs={'accept': 'image/jpeg,image/png,image/webp',
                                                             'data-photo-input': '1'}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, (list, tuple)):
            return [single(d, initial) for d in data if d]
        return [single(data, initial)] if data else []


class PhotoManagerWidget(forms.HiddenInput):
    """Hidden JSON list of the photos to keep, in order; the grid UI edits it."""
    def render(self, name, value, attrs=None, renderer=None):
        hidden = super().render(name, value, attrs, renderer)
        try:
            urls = json.loads(value) if isinstance(value, str) else (value or [])
        except ValueError:
            urls = []
        ui = render_to_string('admin/realestate/photo_manager.html', {
            'urls': urls, 'field_id': (attrs or {}).get('id', f'id_{name}'),
            'max_photos': photo_storage.MAX_PHOTOS_PER_LISTING,
        })
        return mark_safe(hidden + ui)


def validate_uploads(files, keep_count: int):
    from PIL import Image, UnidentifiedImageError

    errors = []
    if keep_count + len(files) > photo_storage.MAX_PHOTOS_PER_LISTING:
        errors.append(f'A listing can have at most {photo_storage.MAX_PHOTOS_PER_LISTING} photos '
                      f'({keep_count} kept + {len(files)} new).')
    for f in files:
        if f.size > photo_storage.MAX_UPLOAD_BYTES:
            errors.append(f'{f.name}: larger than 10 MB.')
            continue
        try:
            img = Image.open(f)
            fmt = img.format
            img.verify()
            if fmt not in photo_storage.ALLOWED_FORMATS:
                errors.append(f'{f.name}: use a JPG, PNG or WebP photo.')
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            errors.append(f'{f.name}: not a readable image.')
        finally:
            f.seek(0)
    if errors:
        raise forms.ValidationError(errors)


def apply_photo_changes(listing, keep, new_files):
    """Remove dropped photos, save the new order, then upload new files (in that order)."""
    current = list(listing.images or [])
    keep = [u for u in keep if u in current]
    for url in current:
        if url not in keep:
            photo_storage.remove_photo(listing, url)
    if keep and keep != list(listing.images or []):
        photo_storage.reorder_photos(listing, keep)
    added, failed = 0, []
    for f in new_files:
        try:
            photo_storage.add_photo(listing, f)
            added += 1
        except photo_storage.PhotoError as e:
            failed.append(f'{f.name}: {e}')
    return added, failed
