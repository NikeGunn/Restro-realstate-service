from django.apps import AppConfig


class AIEngineConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.ai_engine'
    verbose_name = 'AI Conversation Engine'

    def ready(self):
        from . import signals  # noqa: F401  (registers receivers)
