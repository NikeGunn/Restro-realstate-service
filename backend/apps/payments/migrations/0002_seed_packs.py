"""Seed default credit packs (idempotent). Admin can edit / add more later."""
from django.db import migrations


PACKS = [
    {'slug': 'starter', 'name': 'Starter Pack', 'credits': 20, 'price_hkd': '40.00',
     'description': '20 AI credits — great for trying things out.', 'sort_order': 1},
    {'slug': 'growth', 'name': 'Growth Pack', 'credits': 60, 'price_hkd': '108.00',
     'description': '60 AI credits — 10% off the Starter rate.', 'sort_order': 2},
    {'slug': 'pro', 'name': 'Pro Pack', 'credits': 150, 'price_hkd': '240.00',
     'description': '150 AI credits — best value, 20% off.', 'sort_order': 3},
]


def seed(apps, schema_editor):
    CreditPack = apps.get_model('payments', 'CreditPack')
    for p in PACKS:
        CreditPack.objects.update_or_create(
            slug=p['slug'],
            defaults={
                'name': p['name'], 'credits': p['credits'],
                'price_hkd': p['price_hkd'], 'description': p['description'],
                'currency': 'hkd', 'is_active': True, 'sort_order': p['sort_order'],
            },
        )


def unseed(apps, schema_editor):
    CreditPack = apps.get_model('payments', 'CreditPack')
    CreditPack.objects.filter(slug__in=[p['slug'] for p in PACKS]).delete()


class Migration(migrations.Migration):
    dependencies = [('payments', '0001_initial')]
    operations = [migrations.RunPython(seed, unseed)]
