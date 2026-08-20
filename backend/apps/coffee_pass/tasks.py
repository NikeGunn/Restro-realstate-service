"""
Celery tasks — expiry, outbox delivery, Stripe reconciliation, reminders.

Every task is idempotent and failure-isolated per organization/row: one bad
tenant must never stop the sweep for everyone else. None of them is the
authority on anything — query-time checks are (a pass past `expires_at` is
already invalid whether or not this ran). These tasks exist to make state tidy
and notifications timely, not to be load-bearing for correctness.
"""
from __future__ import annotations

import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name='apps.coffee_pass.tasks.expire_passes_task')
def expire_passes_task():
    """
    Flip ACTIVE passes past their window to EXPIRED and tag the customer.

    Housekeeping only — `entitlement_service.check()` already refuses an
    out-of-window pass, so a delayed run can never let someone redeem late.
    """
    from .models import CoffeePass, CoffeePassAuditEvent, PassStatus
    from .services import audit_service, experience_service

    now = timezone.now()
    due = CoffeePass.objects.select_related('customer', 'organization', 'location').filter(
        status=PassStatus.ACTIVE, expires_at__lte=now,
    )[:500]

    expired = 0
    for coffee_pass in due:
        try:
            with transaction.atomic():
                # Re-check under lock: a support restore may have raced us.
                locked = CoffeePass.objects.select_for_update().get(pk=coffee_pass.pk)
                if locked.status != PassStatus.ACTIVE or locked.expires_at > now:
                    continue
                locked.status = PassStatus.EXPIRED
                locked.save(update_fields=['status', 'updated_at'])

                experience_service.remove_tag(
                    coffee_pass.customer, experience_service.TAG_MEMBER,
                )
                experience_service.apply_tag(
                    coffee_pass.customer, experience_service.TAG_EXPIRED, '#94A3B8',
                )
                audit_service.record(
                    organization=coffee_pass.organization,
                    location=coffee_pass.location,
                    action=CoffeePassAuditEvent.Action.PASS_EXPIRED,
                    entity=locked,
                    metadata={'expired_at': now.isoformat()},
                )
            expired += 1
        except Exception:
            logger.exception('Failed to expire Coffee Pass %s', coffee_pass.id)

    return {'expired': expired}


@shared_task(name='apps.coffee_pass.tasks.process_outbox_task')
def process_outbox_task(limit=50):
    """
    Deliver due outbox events.

    Claims rows with `skip_locked` so several workers can drain concurrently
    without double-sending. Each event is delivered independently — one failure
    never blocks the queue behind it.
    """
    from .services import notification_service

    events = notification_service.claim_batch(limit=limit)
    counts = {'sent': 0, 'skipped': 0, 'failed': 0}
    for event in events:
        outcome = notification_service.deliver(event).get('status', 'failed')
        counts[outcome] = counts.get(outcome, 0) + 1
    return counts


@shared_task(name='apps.coffee_pass.tasks.reconcile_purchases_task')
def reconcile_purchases_task():
    """
    Recover payments whose webhook never arrived (deploy window, network blip).

    Without this a customer could pay and receive nothing. Reuses the SAME
    activation handler as the webhook, so recovery and the happy path cannot
    diverge.
    """
    from .services import checkout_service, webhook_service

    try:
        result = webhook_service.reconcile_pending_purchases()
    except Exception:
        logger.exception('Coffee Pass reconciliation failed')
        result = {'checked': 0, 'recovered': 0}

    # Release abandoned checkouts so they stop blocking new offers.
    try:
        result['expired_pending'] = checkout_service.expire_stale_pending()
    except Exception:
        logger.exception('Coffee Pass pending-checkout sweep failed')
    return result


@shared_task(name='apps.coffee_pass.tasks.send_expiry_reminders_task')
def send_expiry_reminders_task():
    """
    Queue a 3-day expiry reminder for active passes.

    Only ENQUEUES — the notification service re-checks consent, cadence, and
    quality suppression at SEND time, which is the check that actually matters.
    The unique outbox key makes a re-run a no-op.
    """
    from django.conf import settings

    from .models import CoffeePass, PassStatus
    from .services import audit_service, experience_service

    days = getattr(settings, 'COFFEE_PASS_SETTINGS', {}).get('EXPIRY_REMINDER_DAYS', 3)
    now = timezone.now()
    window_end = now + timezone.timedelta(days=days)

    due = CoffeePass.objects.select_related('customer', 'organization').filter(
        status=PassStatus.ACTIVE, expires_at__gt=now, expires_at__lte=window_end,
    )[:500]

    queued = 0
    for coffee_pass in due:
        try:
            event = audit_service.enqueue(
                organization=coffee_pass.organization,
                event_type=experience_service.EVENT_EXPIRY_REMINDER,
                aggregate=coffee_pass,
                payload={
                    'pass_id': str(coffee_pass.id),
                    'customer_id': str(coffee_pass.customer_id),
                },
                # One reminder per pass, ever — the unique key enforces it.
                idempotency_key=f'expiry_reminder:{coffee_pass.id}',
            )
            if event is not None:
                queued += 1
        except Exception:
            logger.exception('Failed to queue expiry reminder for %s', coffee_pass.id)

    return {'queued': queued}


@shared_task(name='apps.coffee_pass.tasks.purge_expired_tokens_task')
def purge_expired_tokens_task():
    """Drop long-dead verification tokens. Live and recent rows are untouched."""
    from .services import verification_service

    try:
        return {'deleted': verification_service.purge_expired()}
    except Exception:
        logger.exception('Coffee Pass token purge failed')
        return {'deleted': 0}


@shared_task(name='apps.coffee_pass.tasks.detect_anomalies_task')
def detect_anomalies_task():
    """
    Compute explainable anomaly flags per org for the owner dashboard.

    Read-only and per-org isolated: it reports, it never suspends or blocks.
    """
    from apps.accounts.models import Organization

    from .models import CoffeePassPlan
    from .services import analytics_service

    org_ids = CoffeePassPlan.objects.values_list('organization_id', flat=True).distinct()
    flagged = 0
    for organization in Organization.objects.filter(id__in=list(org_ids)):
        try:
            found = analytics_service.anomalies(organization=organization)
            if found:
                flagged += 1
                logger.info(
                    'Coffee Pass anomalies for org %s: %s',
                    organization.id, [f['code'] for f in found],
                )
        except Exception:
            logger.exception('Anomaly detection failed for org %s', organization.id)
    return {'organizations_flagged': flagged}
