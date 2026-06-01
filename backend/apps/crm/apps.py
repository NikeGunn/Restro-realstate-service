from django.apps import AppConfig


class CrmConfig(AppConfig):
    """
    CRM Lite (Phase 1).

    Cross-app signals are lazy-connected here so receivers never import the
    originating app (restaurant / messaging) at module level, and never block
    the originating save.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.crm'
    verbose_name = 'CRM Lite'

    def ready(self):
        from . import signals  # noqa: F401
        signals.connect_signals()
