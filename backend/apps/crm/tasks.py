"""
CRM Celery tasks (Phase 1).

All are light, cron-spaced jobs that run on the existing celery-beat pod.
Beat schedule entries are appended in config/settings.CELERY_BEAT_SCHEDULE.
"""
import logging

from celery import shared_task
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def refresh_segment_counts_task():
    """Recompute cached customer_count for every segment (daily 02:00 UTC)."""
    from .services import segment_service
    segment_service.refresh_counts()


@shared_task
def refresh_birthday_tag_task():
    """
    Sync the `birthday_this_month` system tag (daily 00:30 UTC). Adds this
    month's birthdays, removes everyone else — powers the birthday loop cheaply
    off the indexed birthday_month column.
    """
    from .models import CRMTag, CRMCustomer, CRMCustomerTag
    month = timezone.now().month
    for tag in CRMTag.objects.filter(name='birthday_this_month').iterator():
        org = tag.organization
        # Desired membership: active customers with birthday this month.
        desired_ids = set(
            CRMCustomer.objects.filter(
                organization=org, is_active=True, birthday_month=month
            ).values_list('id', flat=True)
        )
        current_ids = set(
            CRMCustomerTag.objects.filter(tag=tag).values_list('customer_id', flat=True)
        )
        to_add = desired_ids - current_ids
        to_remove = current_ids - desired_ids
        CRMCustomerTag.objects.bulk_create(
            [CRMCustomerTag(customer_id=cid, tag=tag) for cid in to_add],
            ignore_conflicts=True,
        )
        if to_remove:
            CRMCustomerTag.objects.filter(tag=tag, customer_id__in=to_remove).delete()


@shared_task
def refresh_inactive_tag_task():
    """
    Tag/untag `inactive_customer` (daily 01:00 UTC). Inactive = last_visit_date
    older than CRM_INACTIVE_DAYS (default 90) or never visited.
    """
    from .models import CRMTag, CRMCustomer, CRMCustomerTag
    inactive_days = getattr(settings, 'CRM_INACTIVE_DAYS', 90)
    cutoff = (timezone.now() - timezone.timedelta(days=inactive_days)).date()
    for tag in CRMTag.objects.filter(name='inactive_customer').iterator():
        org = tag.organization
        desired_ids = set(
            CRMCustomer.objects.filter(organization=org, is_active=True)
            .filter(Q(last_visit_date__lt=cutoff) | Q(last_visit_date__isnull=True))
            .values_list('id', flat=True)
        )
        current_ids = set(
            CRMCustomerTag.objects.filter(tag=tag).values_list('customer_id', flat=True)
        )
        to_add = desired_ids - current_ids
        to_remove = current_ids - desired_ids
        CRMCustomerTag.objects.bulk_create(
            [CRMCustomerTag(customer_id=cid, tag=tag) for cid in to_add],
            ignore_conflicts=True,
        )
        if to_remove:
            CRMCustomerTag.objects.filter(tag=tag, customer_id__in=to_remove).delete()
