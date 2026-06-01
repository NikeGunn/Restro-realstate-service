from django.apps import AppConfig


class LuckyDrawConfig(AppConfig):
    """
    Lucky Draw (Phase 2).

    Signals (campaign create -> ensure system tags exist) are lazy-connected in
    ready() so receivers never import the originating app at module level.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.lucky_draw'
    verbose_name = 'Lucky Draw'

    def ready(self):
        from . import signals  # noqa: F401
        signals.connect_signals()
