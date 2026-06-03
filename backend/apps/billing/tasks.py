"""
Billing Celery tasks.

- reset_monthly_credits_task        — 1st of month: free credits reset, period advances.
- generate_monthly_summary_task     — 2nd of month: build prev-month rollup per org.
- check_cap_alerts_task             — every 6h: recompute cap_status, fire crossings.
- reconcile_stale_reservations_task — every 15 min: refund orphaned reservations.

All tasks are per-org loops, failure-isolated (one org failing never aborts the rest).
"""
import logging
from datetime import timedelta
from decimal import Decimal

from celery import shared_task
from django.db.models import Sum, Count, Q
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name='apps.billing.tasks.reset_monthly_credits_task')
def reset_monthly_credits_task():
    from apps.accounts.models import Organization
    from .services import credit_service
    n = 0
    for org in Organization.objects.all().iterator():
        try:
            credit_service.reset_monthly_credits(org)
            n += 1
        except Exception:
            logger.exception('monthly reset failed for org %s', org.pk)
    return {'reset': n}


@shared_task(name='apps.billing.tasks.generate_monthly_summary_task')
def generate_monthly_summary_task():
    from apps.accounts.models import Organization
    from .models import UsageEvent, MonthlyUsageSummary, UsageModule

    now = timezone.now()
    first_this_month = now.date().replace(day=1)
    last_prev = first_this_month - timedelta(days=1)
    year, month = last_prev.year, last_prev.month
    built = 0
    for org in Organization.objects.all().iterator():
        try:
            events = UsageEvent.objects.filter(
                organization=org, status='success',
                created_at__year=year, created_at__month=month,
            )
            agg = events.aggregate(
                free_used=Sum('credits_used', filter=Q(is_free_credit=True)),
                paid_used=Sum('credits_used', filter=Q(is_free_credit=False)),
                cost_usd=Sum('cost_usd'),
                cost_hkd=Sum('cost_hkd'),
                billable=Sum('billable_amount_hkd'),
                images=Count('id', filter=Q(module=UsageModule.CONTENT_STUDIO)),
                queries=Count('id', filter=Q(module=UsageModule.INVENTORY_AI)),
            )
            MonthlyUsageSummary.objects.update_or_create(
                organization=org, year=year, month=month,
                defaults={
                    'free_credits_used': agg['free_used'] or 0,
                    'paid_credits_used': agg['paid_used'] or 0,
                    'total_cost_usd': agg['cost_usd'] or Decimal('0'),
                    'total_cost_hkd': agg['cost_hkd'] or Decimal('0'),
                    'total_billable_hkd': agg['billable'] or Decimal('0'),
                    'image_generations': agg['images'] or 0,
                    'ai_queries': agg['queries'] or 0,
                },
            )
            built += 1
        except Exception:
            logger.exception('monthly summary failed for org %s', org.pk)
    return {'summaries': built, 'year': year, 'month': month}


@shared_task(name='apps.billing.tasks.check_cap_alerts_task')
def check_cap_alerts_task():
    from .models import UsageCreditBalance
    from .services import cap_monitor
    checked = 0
    for balance in UsageCreditBalance.objects.all().iterator():
        try:
            cap_monitor.recompute_cap_status(balance, persist=True)
            checked += 1
        except Exception:
            logger.exception('cap alert check failed for org %s', balance.organization_id)
    return {'checked': checked}


@shared_task(name='apps.billing.tasks.reconcile_stale_reservations_task')
def reconcile_stale_reservations_task():
    """Refund `reserved` events older than RESERVATION_TTL — a crash between
    provider-success and confirm must never leave a silent charge or a stuck hold.
    """
    from django.conf import settings
    from .models import UsageEvent, EventStatus
    from .services import credit_service

    ttl = settings.BILLING_SETTINGS.get('RESERVATION_TTL_MINUTES', 15)
    cutoff = timezone.now() - timedelta(minutes=ttl)
    stale = UsageEvent.objects.filter(status=EventStatus.RESERVED, created_at__lt=cutoff)
    refunded = 0
    for event in stale.iterator():
        try:
            credit_service.refund_credits(event)
            refunded += 1
        except Exception:
            logger.exception('reconcile refund failed for event %s', event.pk)
    return {'refunded': refunded}
