"""Create a UsageCreditBalance + UsageLimit (+ AccountSubscription) for every
existing org so the credit saga has a row to lock on day one. Idempotent."""
from datetime import date
from decimal import Decimal

from django.db import migrations


def backfill(apps, schema_editor):
    Organization = apps.get_model('accounts', 'Organization')
    SubscriptionPlan = apps.get_model('billing', 'SubscriptionPlan')
    UsageCreditBalance = apps.get_model('billing', 'UsageCreditBalance')
    UsageLimit = apps.get_model('billing', 'UsageLimit')
    AccountSubscription = apps.get_model('billing', 'AccountSubscription')

    today = date.today().replace(day=1)
    if today.month == 12:
        period_end = today.replace(year=today.year + 1, month=1, day=1)
    else:
        period_end = today.replace(month=today.month + 1, day=1)

    plans = {p.plan_code: p for p in SubscriptionPlan.objects.all()}

    for org in Organization.objects.all().iterator():
        plan = plans.get(org.plan) or plans.get('basic')
        free = plan.monthly_image_credits if plan else 0

        UsageCreditBalance.objects.get_or_create(
            organization=org,
            defaults={'free_credits_remaining': free, 'period_start': today},
        )
        UsageLimit.objects.get_or_create(
            organization=org,
            defaults={'monthly_ai_spend_cap_hkd': Decimal('200.00'), 'alert_at_percent': 80},
        )
        if plan is not None and not AccountSubscription.objects.filter(
            organization=org, status='active',
        ).exists():
            AccountSubscription.objects.create(
                organization=org, plan=plan, status='active',
                current_period_start=today, current_period_end=period_end,
                monthly_ai_spend_cap_hkd=Decimal('200.00'),
            )


def noop(apps, schema_editor):
    # Leave balances in place on reverse (safe — no data loss intended).
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('billing', '0002_seed_plans'),
        ('accounts', '0001_initial'),
    ]
    operations = [migrations.RunPython(backfill, noop)]
