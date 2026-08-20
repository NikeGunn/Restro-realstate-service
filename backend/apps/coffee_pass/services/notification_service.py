"""
Outbox delivery — the only place Coffee Pass sends a customer a message.

Two rules that are easy to state and easy to get wrong:

1. **Transactional vs marketing are different consents.** A payment receipt or a
   redemption confirmation is transactional: the customer just handed over money
   or a code and is owed the result. A "your pass expires soon, come back" nudge
   is marketing and requires `has_marketing_consent`. Conflating them either
   spams people or hides receipts from paying customers.

2. **State is re-checked at SEND time, never at enqueue time.** Between queueing
   a reminder and sending it, a customer may withdraw consent, have a bad
   experience, or let the pass lapse. Every one of those must stop the message.

Delivery failure marks the outbox row for retry and NEVER unwinds the payment or
redemption it describes.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.crm.services import consent_service

from ..models import (
    CoffeePass, CoffeePassOutboxEvent, OutboxStatus, PassStatus,
)
from . import experience_service

logger = logging.getLogger(__name__)

#: Message classes. TRANSACTIONAL bypasses the marketing consent gate; MARKETING
#: never does.
TRANSACTIONAL = 'transactional'
MARKETING = 'marketing'

EVENT_CLASS = {
    experience_service.EVENT_PASS_ACTIVATED: TRANSACTIONAL,
    experience_service.EVENT_REDEMPTION_CREATED: TRANSACTIONAL,
    experience_service.EVENT_FEEDBACK_NEGATIVE: TRANSACTIONAL,
    experience_service.EVENT_EXPIRY_REMINDER: MARKETING,
}


def _cfg(key, default):
    return getattr(settings, 'COFFEE_PASS_SETTINGS', {}).get(key, default)


# ──────────────────────────────────────────────────────────────────────
# Copy (zh-TW default for HK; falls back by language, never crashes)
# ──────────────────────────────────────────────────────────────────────
_COPY = {
    experience_service.EVENT_PASS_ACTIVATED: {
        'zh-TW': '☕ 你嘅 {plan} 已生效！喺 {location} 享有 {pct}% 折扣，有效期至 {expiry}。開啟錢包：{url}',
        'zh-CN': '☕ 你的 {plan} 已生效！在 {location} 享有 {pct}% 折扣，有效期至 {expiry}。打开钱包：{url}',
        'en': '☕ Your {plan} is active! {pct}% off at {location} until {expiry}. Open your wallet: {url}',
    },
    experience_service.EVENT_REDEMPTION_CREATED: {
        'zh-TW': '✅ 今次幫你慳咗 HK${amount}。多謝幫襯 {location}！',
        'zh-CN': '✅ 这次帮你省了 HK${amount}。感谢光临 {location}！',
        'en': '✅ You saved HK${amount} today. Thanks for visiting {location}!',
    },
    experience_service.EVENT_FEEDBACK_NEGATIVE: {
        'zh-TW': '多謝你嘅意見。我哋好重視今次體驗，{location} 團隊會盡快跟進。',
        'zh-CN': '感谢你的反馈。我们非常重视这次体验，{location} 团队会尽快跟进。',
        'en': 'Thank you for telling us. The team at {location} takes this seriously and will follow up.',
    },
    experience_service.EVENT_EXPIRY_REMINDER: {
        'zh-TW': '你嘅 {plan} 將於 {expiry} 到期。今個月已慳 HK${amount}。（不會自動續期）',
        'zh-CN': '你的 {plan} 将于 {expiry} 到期。本月已省 HK${amount}。（不会自动续期）',
        'en': 'Your {plan} expires on {expiry}. You have saved HK${amount} so far. (No auto-renewal.)',
    },
}


def render(event_type, language, context) -> str:
    """Localized copy with a safe fallback chain: language -> zh-TW -> ''."""
    table = _COPY.get(event_type) or {}
    template = table.get(language) or table.get('zh-TW') or ''
    try:
        return template.format(**context)
    except (KeyError, IndexError):
        logger.warning('Notification copy render failed for %s', event_type)
        return ''


# ──────────────────────────────────────────────────────────────────────
# Gates
# ──────────────────────────────────────────────────────────────────────
def may_send(event_type, customer, *, location=None) -> tuple:
    """
    Decide whether this message may go out RIGHT NOW.

    Returns (allowed, reason). Reasons are stable so the outbox row records
    exactly why something was skipped — a skipped message must be explainable.
    """
    message_class = EVENT_CLASS.get(event_type, MARKETING)

    if not customer.is_active:
        return False, 'customer_inactive'
    if not (customer.whatsapp_number or customer.phone):
        return False, 'no_channel'

    if message_class == TRANSACTIONAL:
        # A receipt is owed regardless of marketing preference.
        return True, 'transactional'

    if not consent_service.has_marketing_consent(customer, 'whatsapp'):
        return False, 'no_marketing_consent'

    # Quality suppression: never nudge someone who just had a bad coffee.
    if location is not None and experience_service.has_recent_negative(customer, location):
        return False, 'recent_negative_experience'

    if not _within_cadence(customer):
        return False, 'cadence_cap'

    return True, 'ok'


def _within_cadence(customer) -> bool:
    """At most one PROMOTIONAL message per N days (default 7)."""
    days = _cfg('REMINDER_MIN_INTERVAL_DAYS', 7)
    cutoff = timezone.now() - timezone.timedelta(days=days)
    marketing_types = [k for k, v in EVENT_CLASS.items() if v == MARKETING]
    return not CoffeePassOutboxEvent.objects.filter(
        organization=customer.organization,
        event_type__in=marketing_types,
        status=OutboxStatus.SENT,
        processed_at__gte=cutoff,
        payload__customer_id=str(customer.id),
    ).exists()


# ──────────────────────────────────────────────────────────────────────
# Delivery
# ──────────────────────────────────────────────────────────────────────
def deliver(event) -> dict:
    """
    Deliver one outbox event. Always returns a dict; never raises.

    The caller (a Celery task) uses the returned status to decide retry vs stop,
    so an unexpected exception here must not poison the whole batch.
    """
    try:
        return _deliver_inner(event)
    except Exception as exc:
        logger.exception('Coffee Pass notification delivery crashed')
        _mark_failed(event, str(exc)[:500])
        return {'status': 'failed', 'reason': 'exception'}


def _deliver_inner(event) -> dict:
    from apps.crm.models import CRMCustomer

    payload = event.payload or {}
    customer = CRMCustomer.objects.filter(id=payload.get('customer_id')).first()
    if customer is None:
        _mark(event, OutboxStatus.SKIPPED, 'customer_not_found')
        return {'status': 'skipped', 'reason': 'customer_not_found'}

    coffee_pass = None
    if payload.get('pass_id'):
        coffee_pass = CoffeePass.objects.select_related(
            'location', 'plan',
        ).filter(id=payload['pass_id']).first()

    location = coffee_pass.location if coffee_pass else None
    allowed, reason = may_send(event.event_type, customer, location=location)
    if not allowed:
        _mark(event, OutboxStatus.SKIPPED, reason)
        return {'status': 'skipped', 'reason': reason}

    # For a reminder, the pass must STILL be active at send time.
    if event.event_type == experience_service.EVENT_EXPIRY_REMINDER:
        if coffee_pass is None or coffee_pass.status != PassStatus.ACTIVE:
            _mark(event, OutboxStatus.SKIPPED, 'pass_not_active')
            return {'status': 'skipped', 'reason': 'pass_not_active'}

    text = render(event.event_type, customer.preferred_language or 'zh-TW',
                  _context(event, customer, coffee_pass, payload))
    if not text:
        _mark(event, OutboxStatus.SKIPPED, 'no_copy')
        return {'status': 'skipped', 'reason': 'no_copy'}

    sent = _send_whatsapp(customer, text)
    if sent:
        _mark(event, OutboxStatus.SENT, '')
        return {'status': 'sent'}

    _mark_failed(event, 'whatsapp_send_failed')
    return {'status': 'failed', 'reason': 'whatsapp_send_failed'}


def _context(event, customer, coffee_pass, payload) -> dict:
    """Build render context. Every key is optional-safe."""
    from . import webhook_service

    snapshot = (coffee_pass.plan_snapshot if coffee_pass else {}) or {}
    location_name = coffee_pass.location.name if coffee_pass else ''
    amount = payload.get('discount_amount_hkd')
    if amount is None and coffee_pass is not None:
        amount = str(webhook_service.savings_to_date(coffee_pass))

    return {
        'plan': snapshot.get('name', 'Coffee Pass'),
        'location': location_name,
        'pct': snapshot.get('discount_percent', '30'),
        'expiry': (
            coffee_pass.expires_at.strftime('%Y-%m-%d') if coffee_pass else ''
        ),
        'amount': amount or '0.00',
        'url': _wallet_url(coffee_pass),
        'name': customer.name,
    }


def _wallet_url(coffee_pass) -> str:
    if coffee_pass is None:
        return settings.PUBLIC_BASE_URL.rstrip('/')
    token = getattr(coffee_pass.plan, 'public_token', '')
    return f'{settings.PUBLIC_BASE_URL.rstrip("/")}/public/coffee-pass/{token}/'


def _send_whatsapp(customer, text) -> bool:
    """
    Send through the org's existing WhatsApp channel.

    No active config is a SKIP, not an error: many orgs run Coffee Pass without
    WhatsApp, and the pass itself is unaffected.
    """
    from apps.channels.whatsapp_service import WhatsAppService

    service = WhatsAppService.get_for_organization(customer.organization)
    if service is None:
        logger.info('No active WhatsApp config for org %s', customer.organization_id)
        return False
    to = customer.whatsapp_number or customer.phone
    try:
        return bool(service.send_message(to, text))
    except Exception:
        logger.warning('WhatsApp send raised for customer %s', customer.id, exc_info=True)
        return False


def _mark(event, status, reason):
    event.status = status
    event.processed_at = timezone.now()
    event.last_error = reason or ''
    event.save(update_fields=['status', 'processed_at', 'last_error'])


def _mark_failed(event, error):
    """
    Exponential backoff, bounded attempts. After the ceiling the row stays FAILED
    for an operator to see — silently dropping a notification intent is worse
    than an alert.
    """
    max_attempts = _cfg('OUTBOX_MAX_ATTEMPTS', 5)
    event.attempt_count += 1
    event.last_error = error or ''
    if event.attempt_count >= max_attempts:
        event.status = OutboxStatus.FAILED
        event.processed_at = timezone.now()
    else:
        event.status = OutboxStatus.PENDING
        backoff = min(2 ** event.attempt_count, 60) * 60  # cap at 1h
        event.available_at = timezone.now() + timezone.timedelta(seconds=backoff)
    event.save(update_fields=[
        'attempt_count', 'last_error', 'status', 'available_at', 'processed_at',
    ])


@transaction.atomic
def claim_batch(limit=50):
    """
    Claim due outbox rows for this worker.

    `select_for_update(skip_locked=True)` is what lets several workers drain the
    queue in parallel without two of them grabbing the same row — the alternative
    (a plain filter) would send duplicate messages under concurrency.
    """
    ids = list(
        CoffeePassOutboxEvent.objects.select_for_update(skip_locked=True)
        .filter(status=OutboxStatus.PENDING, available_at__lte=timezone.now())
        .order_by('available_at')
        .values_list('id', flat=True)[:limit]
    )
    return list(CoffeePassOutboxEvent.objects.filter(id__in=ids))
