from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.billing'
    label = 'billing'
    verbose_name = 'AI Credit & Usage Billing'

    def ready(self):
        # Lazy-connect the org→balance bootstrap signal (failure-safe, one-directional).
        from . import signals  # noqa: F401
