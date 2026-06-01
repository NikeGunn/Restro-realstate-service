from django.apps import AppConfig


class CommonConfig(AppConfig):
    """
    Shared cross-cutting infrastructure (Phase 0).

    Library app — no URL mount, no tables of its own (only an abstract
    AuditLog base). Holds the org-scope/permission/throttle/idempotency/storage
    machinery that Phases 1-6 reuse instead of re-inventing per app.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.common'
    verbose_name = 'Common (shared infrastructure)'
