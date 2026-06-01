"""
Data migration: backfill the 7 system tags + a default segment for orgs that
already existed before CRM Lite landed. New orgs get them via the post_save
signal in apps/crm/signals.py.
"""
from django.db import migrations

_SYSTEM_TAG_COLORS = {
    'lucky_draw_lead': '#F59E0B',
    'wifi_lead': '#10B981',
    'buffet_customer': '#8B5CF6',
    'frequent_customer': '#3B82F6',
    'vip': '#EF4444',
    'inactive_customer': '#6B7280',
    'birthday_this_month': '#EC4899',
}


def seed_existing_orgs(apps, schema_editor):
    Organization = apps.get_model('accounts', 'Organization')
    CRMTag = apps.get_model('crm', 'CRMTag')
    CRMSegment = apps.get_model('crm', 'CRMSegment')

    for org in Organization.objects.all().iterator():
        for name, color in _SYSTEM_TAG_COLORS.items():
            CRMTag.objects.get_or_create(
                organization=org, name=name,
                defaults={'color': color, 'is_system': True},
            )
        CRMSegment.objects.get_or_create(
            organization=org,
            name='All consenting customers',
            defaults={
                'description': 'Customers who have given marketing consent.',
                'filter_rules': {
                    'logic': 'AND',
                    'rules': [{'field': 'marketing_consent_status',
                               'op': 'eq', 'value': 'given'}],
                },
            },
        )


def unseed(apps, schema_editor):
    # Reverse is a no-op (we don't want to delete tags that may now be in use).
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('crm', '0001_initial'),
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_existing_orgs, unseed),
    ]
