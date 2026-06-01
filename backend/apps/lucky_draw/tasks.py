"""
Lucky Draw Celery tasks (Phase 2).

- send_coupon_whatsapp_task  : queued on_commit by the public POST (loop 1).
- reset_prize_daily_counters_task : zero wins_today_count nightly.
- send_expiry_reminders_task : hourly nudge for coupons expiring <24h (loop 1).
- expire_entries_task        : daily, flip past-expiry drawn entries to expired.

Beat entries are appended in config/settings.CELERY_BEAT_SCHEDULE.
All tasks are defensive: a single bad row never aborts the sweep.
"""
import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def send_coupon_whatsapp_task(entry_id):
    """Deliver the coupon for one entry over WhatsApp (consent-gated)."""
    from .models import LuckyDrawEntry
    from .services import delivery_service
    entry = (
        LuckyDrawEntry.objects.select_related('campaign__organization', 'prize', 'crm_customer')
        .filter(pk=entry_id)
        .first()
    )
    if entry is None:
        return
    delivery_service.deliver_coupon_whatsapp(entry)


@shared_task
def reset_prize_daily_counters_task():
    """Zero every prize's wins_today_count (daily 00:01)."""
    from .models import LuckyDrawPrize
    LuckyDrawPrize.objects.filter(wins_today_count__gt=0).update(wins_today_count=0)


@shared_task
def send_expiry_reminders_task():
    """
    Send a reminder for drawn entries expiring within 24h that haven't been
    reminded yet and whose customer still has whatsapp consent (hourly).
    """
    from .models import LuckyDrawEntry, EntryStatus
    from .services import delivery_service
    now = timezone.now()
    window_end = now + timezone.timedelta(hours=24)
    qs = (
        LuckyDrawEntry.objects.select_related('campaign__organization', 'prize', 'crm_customer')
        .filter(
            status=EntryStatus.DRAWN,
            reminder_sent_at__isnull=True,
            expires_at__isnull=False,
            expires_at__gt=now,
            expires_at__lte=window_end,
        )
        .iterator()
    )
    sent = 0
    for entry in qs:
        try:
            if delivery_service.send_expiry_reminder(entry):
                sent += 1
        except Exception:
            logger.exception("Expiry reminder failed for entry %s", entry.id)
    logger.info("Lucky-draw expiry reminders sent: %s", sent)


@shared_task
def expire_entries_task():
    """Flip drawn entries past their expires_at to expired (daily)."""
    from .models import LuckyDrawEntry, EntryStatus
    now = timezone.now()
    qs = LuckyDrawEntry.objects.filter(
        status=EntryStatus.DRAWN, expires_at__isnull=False, expires_at__lt=now,
    ).iterator()
    count = 0
    for entry in qs:
        try:
            entry.status = EntryStatus.EXPIRED
            entry.save(update_fields=['status'])
            count += 1
        except Exception:
            logger.exception("Expire failed for entry %s", entry.id)
    logger.info("Lucky-draw entries expired: %s", count)
