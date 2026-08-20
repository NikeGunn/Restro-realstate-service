"""App config for Coffee Pass."""
from django.apps import AppConfig


class CoffeePassConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.coffee_pass'
    label = 'coffee_pass'
    verbose_name = 'Coffee Pass'
