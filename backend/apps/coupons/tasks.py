"""Coupon-related Celery tasks."""
import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Organization

logger = logging.getLogger(__name__)


@shared_task(name='coupons.downgrade_expired_plans')
def downgrade_expired_plans():
    """Sync `Organization.plan` → BASIC for orgs whose `plan_expires_at` has passed.

    Plan gating already respects expiry via `Organization.effective_plan`, so this
    task is a *materialization* step — it makes the stored column match the
    computed truth so admin views, exports, and analytics show the right value.

    Idempotent: running it twice is a no-op.
    """
    now = timezone.now()
    expired = Organization.objects.filter(
        plan_expires_at__lt=now,
    ).exclude(plan=Organization.Plan.BASIC)

    count = 0
    for org in expired.iterator():
        with transaction.atomic():
            org.plan = Organization.Plan.BASIC
            org.plan_expires_at = None
            org.save(update_fields=['plan', 'plan_expires_at', 'updated_at'])
            count += 1
            logger.info('Downgraded org %s (%s) to BASIC after plan expiry.', org.id, org.name)

    logger.info('downgrade_expired_plans: processed %d expired organizations.', count)
    return count
