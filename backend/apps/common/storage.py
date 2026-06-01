"""
Object-storage backend hook (Phase 0).

The actual STORAGES wiring is in config/settings.py, gated on the
USE_OBJECT_STORAGE env var (default False). In dev and current prod we keep
FileSystemStorage + the media-pvc; flipping USE_OBJECT_STORAGE=true moves every
ImageField/FileField to the S3-compatible bucket with ZERO model changes — that
is what unblocks raising backend `replicas` past 1 (RWO PVC can't be multi-mounted).

This module is intentionally thin and import-safe even when django-storages is
not installed, so importing `apps.common` never crashes a minimal environment.
"""
from django.conf import settings


def is_object_storage_enabled() -> bool:
    """True when the deployment has opted into S3-compatible object storage."""
    return bool(getattr(settings, 'USE_OBJECT_STORAGE', False))


# Path to the S3 backend, referenced from settings.STORAGES when enabled.
# Kept as a string (not an import) so this module loads even without boto3/storages.
S3_STORAGE_BACKEND = 'storages.backends.s3.S3Storage'
