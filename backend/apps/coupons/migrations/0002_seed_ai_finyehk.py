"""Seed the AI-FINYEHK promotional coupon (idempotent)."""
from django.db import migrations


def seed(apps, schema_editor):
    Coupon = apps.get_model('coupons', 'Coupon')
    Coupon.objects.update_or_create(
        code='AI-FINYEHK',
        defaults={
            'description': '1 month free Power plan — promotional launch coupon.',
            'plan_granted': 'power',
            'duration_days': 30,
            'max_redemptions': None,
            'is_active': True,
        },
    )


def unseed(apps, schema_editor):
    Coupon = apps.get_model('coupons', 'Coupon')
    Coupon.objects.filter(code='AI-FINYEHK').delete()


class Migration(migrations.Migration):
    dependencies = [('coupons', '0001_initial')]
    operations = [migrations.RunPython(seed, unseed)]
