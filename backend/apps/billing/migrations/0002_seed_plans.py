"""Seed the basic + power SubscriptionPlan rows (idempotent)."""
from django.db import migrations


def seed_plans(apps, schema_editor):
    SubscriptionPlan = apps.get_model('billing', 'SubscriptionPlan')
    # Kept in sync with apps/billing/constants.py::SEED_PLANS.
    plans = [
        {
            'slug': 'basic', 'name': 'Basic', 'plan_code': 'basic',
            'price_hkd': '0.00', 'monthly_image_credits': 0,
            'enabled_modules': ['chatbot_ai'],
        },
        {
            'slug': 'power', 'name': 'Growth', 'plan_code': 'power',
            'price_hkd': '200.00', 'monthly_image_credits': 20,
            'enabled_modules': ['chatbot_ai', 'inventory_ai', 'content_studio'],
        },
    ]
    for p in plans:
        SubscriptionPlan.objects.update_or_create(
            slug=p['slug'],
            defaults={
                'name': p['name'],
                'plan_code': p['plan_code'],
                'price_hkd': p['price_hkd'],
                'monthly_image_credits': p['monthly_image_credits'],
                'enabled_modules': p['enabled_modules'],
            },
        )


def unseed(apps, schema_editor):
    SubscriptionPlan = apps.get_model('billing', 'SubscriptionPlan')
    SubscriptionPlan.objects.filter(slug__in=['basic', 'power']).delete()


class Migration(migrations.Migration):
    dependencies = [('billing', '0001_initial')]
    operations = [migrations.RunPython(seed_plans, unseed)]
