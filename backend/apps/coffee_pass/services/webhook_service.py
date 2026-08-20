"""
Stripe webhook → Coffee Pass activation. The ONLY place a payment becomes a pass.

Stripe retries. Browsers retry. Load balancers duplicate. So activation is
idempotent at four independent layers, each of which alone would be insufficient:

  1. Signature verification — rejects forged payloads outright.
  2. Event-id cache claim (atomic SET-NX) — dedupes concurrent deliveries. Released
     on handler failure so a genuine Stripe retry is not silently swallowed.
  3. Partial-unique Stripe session/payment-intent columns — dedupes across cache
     flushes and process restarts. This is the AUTHORITATIVE layer: if Redis is
     down entirely, correctness still holds.
  4. `purchase.activated` one-way latch inside a `select_for_update` transaction —
     blocks a double-grant even from a logic bug in this file.

The customer's success redirect is informational ONLY. This handler is the sole
authority on whether money was actually taken.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.payments.stripe_client import get_stripe

from ..models import (
    CoffeePass, CoffeePassAuditEvent, CoffeePassPurchase, PassStatus, PurchaseStatus,
    RedemptionStatus,
)
from . import audit_service, experience_service

logger = logging.getLogger(__name__)

WEBHOOK_IDEMPOTENCY_TTL = 60 * 60 * 24  # covers Stripe's ~3-day retry window head

#: Only events carrying this marker belong to us. The AI-credit webhook lives at
#: a different URL, but metadata routing means a misconfigured endpoint can never
#: cross-activate the wrong product.
METADATA_KIND = 'coffee_pass'


def verify_and_construct_event(payload: bytes, sig_header: str):
    """Signature verification REPLACES CSRF on this endpoint. Never skip it."""
    stripe = get_stripe()
    secret = getattr(settings, 'COFFEE_PASS_WEBHOOK_SECRET', '') or settings.STRIPE_WEBHOOK_SECRET
    if not secret:
        raise ValueError('Stripe webhook secret is not configured.')
    return stripe.Webhook.construct_event(payload, sig_header, secret)


# ── event-id claim ───────────────────────────────────────────────────
def _event_key(event_id: str) -> str:
    return f'cp_stripe_event:{event_id}'


def is_duplicate_event(event_id: str) -> bool:
    """True when another delivery already claimed this event id."""
    if not event_id:
        return False
    try:
        return not cache.add(_event_key(event_id), 'processing', WEBHOOK_IDEMPOTENCY_TTL)
    except Exception:
        # Fail OPEN: the DB constraints below are the real backstop, and dropping
        # a real payment event would be far worse than processing it twice.
        logger.warning('Webhook idempotency cache unavailable; relying on DB constraints')
        return False


def mark_event_processed(event_id: str) -> None:
    if event_id:
        try:
            cache.set(_event_key(event_id), 'done', WEBHOOK_IDEMPOTENCY_TTL)
        except Exception:
            logger.warning('Could not mark webhook event processed')


def release_event(event_id: str) -> None:
    """Drop a provisional claim so Stripe's retry is not masked by our own cache."""
    if event_id:
        try:
            cache.delete(_event_key(event_id))
        except Exception:
            logger.warning('Could not release webhook event claim')


def is_coffee_pass_event(event) -> bool:
    """Route by metadata so a shared endpoint can host multiple products safely."""
    obj = (event.get('data') or {}).get('object') or {}
    meta = obj.get('metadata') or {}
    if meta.get('kind') == METADATA_KIND:
        return True
    # charge.refunded has no metadata of ours — resolve via the payment intent.
    if event.get('type') == 'charge.refunded':
        pi = obj.get('payment_intent') or ''
        return bool(pi) and CoffeePassPurchase.objects.filter(
            stripe_payment_intent_id=pi,
        ).exists()
    return False


def handle_event(event) -> dict:
    handlers = {
        'checkout.session.completed': _handle_completed,
        'checkout.session.expired': _handle_expired,
        'charge.refunded': _handle_refunded,
        'payment_intent.payment_failed': _handle_failed,
    }
    handler = handlers.get(event['type'])
    if handler is None:
        return {'status': 'ignored', 'event_type': event['type']}
    return handler(event['data']['object'])


# ── handlers ─────────────────────────────────────────────────────────
@transaction.atomic
def _handle_completed(session) -> dict:
    """
    Payment succeeded → create EXACTLY ONE active pass.

    Everything mutating happens under a row lock on the purchase, and the
    notification is an outbox row written in this same transaction — so a
    WhatsApp outage can never roll back a paid pass, and a crash after commit
    can never lose the promise to notify.
    """
    purchase_id = (
        session.get('client_reference_id')
        or (session.get('metadata') or {}).get('purchase_id')
    )
    if not purchase_id:
        logger.error('Coffee Pass checkout completed without purchase ref')
        return {'status': 'error', 'reason': 'missing_purchase_ref'}

    try:
        purchase = CoffeePassPurchase.objects.select_for_update().select_related(
            'plan', 'customer', 'organization', 'location',
        ).get(id=purchase_id)
    except CoffeePassPurchase.DoesNotExist:
        logger.error('Coffee Pass purchase not found: %s', purchase_id)
        return {'status': 'error', 'reason': 'purchase_not_found'}

    # Latch: a replayed delivery for an already-activated order is a no-op.
    if purchase.activated:
        existing = CoffeePass.objects.filter(purchase=purchase).first()
        return {
            'status': 'duplicate',
            'purchase_id': str(purchase.id),
            'pass_id': str(existing.id) if existing else None,
        }

    payment_intent = session.get('payment_intent', '') or ''

    # Defense in depth: this payment intent already activated a DIFFERENT
    # purchase => replay or forgery. Refuse rather than grant a second pass.
    if payment_intent and CoffeePassPurchase.objects.filter(
        stripe_payment_intent_id=payment_intent, activated=True,
    ).exclude(pk=purchase.pk).exists():
        logger.warning('Coffee Pass intent already activated elsewhere: %s', payment_intent)
        return {'status': 'duplicate', 'reason': 'intent_already_activated'}

    now = timezone.now()
    snapshot = purchase.plan_snapshot or {}
    duration_days = int(snapshot.get('duration_days') or purchase.plan.duration_days)

    # A customer who somehow already holds an active pass here must not get a
    # second one — refund is a support action, but the entitlement stays single.
    conflicting = CoffeePass.objects.select_for_update().filter(
        customer=purchase.customer, location=purchase.location,
        plan=purchase.plan, status=PassStatus.ACTIVE,
    ).first()
    if conflicting is not None:
        purchase.status = PurchaseStatus.PAID
        purchase.stripe_payment_intent_id = payment_intent
        purchase.paid_at = now
        purchase.save(update_fields=[
            'status', 'stripe_payment_intent_id', 'paid_at', 'updated_at',
        ])
        audit_service.record(
            organization=purchase.organization, location=purchase.location,
            action=CoffeePassAuditEvent.Action.PASS_ACTIVATED,
            entity=conflicting, actor_customer=purchase.customer,
            metadata={
                'note': 'payment captured while an active pass already existed',
                'purchase_id': str(purchase.id), 'requires_support_review': True,
            },
        )
        return {
            'status': 'conflict', 'reason': 'active_pass_exists',
            'purchase_id': str(purchase.id), 'pass_id': str(conflicting.id),
        }

    coffee_pass = CoffeePass.objects.create(
        organization=purchase.organization,
        location=purchase.location,
        customer=purchase.customer,
        plan=purchase.plan,
        purchase=purchase,
        status=PassStatus.ACTIVE,
        # Snapshot copied from the PURCHASE, not re-read from the plan: the terms
        # the customer agreed to at checkout are the terms they get.
        plan_snapshot=snapshot,
        starts_at=now,
        expires_at=now + timezone.timedelta(days=duration_days),
    )

    purchase.status = PurchaseStatus.PAID
    purchase.activated = True  # the latch
    purchase.stripe_payment_intent_id = payment_intent
    purchase.stripe_receipt_url = _safe_receipt_url(payment_intent)
    purchase.paid_at = now
    purchase.save(update_fields=[
        'status', 'activated', 'stripe_payment_intent_id',
        'stripe_receipt_url', 'paid_at', 'updated_at',
    ])

    experience_service.apply_tag(purchase.customer, experience_service.TAG_MEMBER, '#10B981')
    experience_service.remove_tag(purchase.customer, experience_service.TAG_EXPIRED)

    audit_service.record(
        organization=purchase.organization, location=purchase.location,
        action=CoffeePassAuditEvent.Action.PASS_ACTIVATED,
        entity=coffee_pass, actor_customer=purchase.customer,
        metadata={
            'purchase_id': str(purchase.id),
            'amount_hkd': str(purchase.amount_hkd),
            'expires_at': coffee_pass.expires_at.isoformat(),
        },
    )
    audit_service.enqueue(
        organization=purchase.organization,
        event_type=experience_service.EVENT_PASS_ACTIVATED,
        aggregate=coffee_pass,
        payload={
            'pass_id': str(coffee_pass.id),
            'customer_id': str(purchase.customer_id),
            'location_id': str(purchase.location_id),
            'expires_at': coffee_pass.expires_at.isoformat(),
        },
    )

    logger.info('Coffee Pass activated', extra={
        'pass_id': str(coffee_pass.id), 'purchase_id': str(purchase.id),
    })
    return {
        'status': 'success',
        'purchase_id': str(purchase.id),
        'pass_id': str(coffee_pass.id),
    }


@transaction.atomic
def _handle_expired(session) -> dict:
    """An abandoned Checkout marks the order expired. It NEVER creates a pass."""
    purchase_id = (
        session.get('client_reference_id')
        or (session.get('metadata') or {}).get('purchase_id')
    )
    if not purchase_id:
        return {'status': 'skipped', 'reason': 'no_ref'}
    try:
        purchase = CoffeePassPurchase.objects.select_for_update().get(id=purchase_id)
    except CoffeePassPurchase.DoesNotExist:
        return {'status': 'skipped', 'reason': 'not_found'}

    # Never downgrade a paid/activated order on a late expiry event.
    if purchase.status == PurchaseStatus.PENDING and not purchase.activated:
        purchase.status = PurchaseStatus.EXPIRED
        purchase.save(update_fields=['status', 'updated_at'])
        return {'status': 'expired', 'purchase_id': str(purchase.id)}
    return {'status': 'skipped', 'reason': 'not_pending'}


@transaction.atomic
def _handle_refunded(charge) -> dict:
    """
    Refund handling. v1 policy (PRD §Phase E): only a FULL refund cancels the
    pass. A partial refund is recorded for finance but does NOT strip a
    customer's entitlement — clawing back a membership someone partly paid for
    is worse than absorbing the difference, and support can cancel explicitly.
    """
    payment_intent = charge.get('payment_intent', '') or ''
    if not payment_intent:
        return {'status': 'ignored', 'reason': 'no_payment_intent'}

    purchase = CoffeePassPurchase.objects.select_for_update().filter(
        stripe_payment_intent_id=payment_intent, activated=True,
    ).first()
    if purchase is None:
        return {'status': 'skipped', 'reason': 'purchase_not_found'}

    refunded_total = Decimal(str(charge.get('amount_refunded', 0))) / Decimal('100')
    # Act only on the NEW delta — Stripe resends the cumulative total.
    if refunded_total - purchase.refunded_amount_hkd <= Decimal('0'):
        return {'status': 'duplicate', 'reason': 'already_recorded'}

    purchase.refunded_amount_hkd = refunded_total
    purchase.stripe_charge_id = charge.get('id', '') or purchase.stripe_charge_id
    fields = ['refunded_amount_hkd', 'stripe_charge_id', 'updated_at']

    cancelled = False
    if refunded_total >= purchase.amount_hkd:
        purchase.status = PurchaseStatus.REFUNDED
        fields.append('status')
        coffee_pass = CoffeePass.objects.select_for_update().filter(
            purchase=purchase,
        ).first()
        if coffee_pass and coffee_pass.status not in (
            PassStatus.CANCELLED, PassStatus.EXPIRED,
        ):
            coffee_pass.status = PassStatus.CANCELLED
            coffee_pass.cancelled_at = timezone.now()
            coffee_pass.cancel_reason = 'full_refund'
            coffee_pass.save(update_fields=[
                'status', 'cancelled_at', 'cancel_reason', 'updated_at',
            ])
            experience_service.remove_tag(
                purchase.customer, experience_service.TAG_MEMBER,
            )
            cancelled = True

    purchase.save(update_fields=fields)

    audit_service.record(
        organization=purchase.organization, location=purchase.location,
        action=CoffeePassAuditEvent.Action.REFUND_PROCESSED,
        entity=purchase, actor_customer=purchase.customer,
        metadata={
            'refunded_total_hkd': str(refunded_total),
            'pass_cancelled': cancelled,
            'charge_id': charge.get('id', ''),
        },
    )
    return {
        'status': 'refunded', 'purchase_id': str(purchase.id),
        'pass_cancelled': cancelled,
    }


def _handle_failed(payment_intent) -> dict:
    """
    A failed attempt is logged, not fatal: the customer may retry inside the same
    Checkout session. Expiry is the authoritative abandonment signal.
    """
    # NOTE: `msg`/`args`/`message` are reserved LogRecord attributes — putting
    # any of them in `extra` raises KeyError and would 500 this webhook on every
    # declined card. Use distinct key names.
    logger.warning('Coffee Pass payment failed', extra={
        'payment_intent_id': payment_intent.get('id', ''),
        'failure_reason': (
            payment_intent.get('last_payment_error') or {}
        ).get('message', 'unknown'),
    })
    return {'status': 'payment_failed', 'payment_intent': payment_intent.get('id', '')}


def _safe_receipt_url(payment_intent_id: str) -> str:
    """Best-effort receipt lookup — observability only, never blocks activation."""
    if not payment_intent_id:
        return ''
    try:
        stripe = get_stripe()
        intent = stripe.PaymentIntent.retrieve(payment_intent_id, expand=['latest_charge'])
        charge = getattr(intent, 'latest_charge', None)
        if isinstance(charge, str) or charge is None:
            return ''
        return getattr(charge, 'receipt_url', '') or ''
    except Exception:
        logger.warning('Could not fetch Coffee Pass receipt URL', exc_info=True)
        return ''


# ── reconciliation (missed/delayed webhooks) ─────────────────────────
def reconcile_pending_purchases(*, limit=100) -> dict:
    """
    Ask Stripe about pending purchases whose webhook never arrived.

    Without this, a webhook lost to a deploy window means a customer paid and got
    nothing. Reuses the SAME `_handle_completed` path, so recovery and the happy
    path can never diverge.
    """
    from django.utils import timezone as tz

    stripe = get_stripe()
    cutoff = tz.now() - tz.timedelta(minutes=5)  # give the webhook a fair chance first
    pending = CoffeePassPurchase.objects.filter(
        status=PurchaseStatus.PENDING, activated=False,
        created_at__lt=cutoff,
    ).exclude(stripe_session_id='')[:limit]

    recovered, checked = 0, 0
    for purchase in pending:
        checked += 1
        try:
            session = stripe.checkout.Session.retrieve(purchase.stripe_session_id)
        except Exception:
            logger.warning('Reconcile: could not retrieve session for %s', purchase.id)
            continue

        if session.get('payment_status') == 'paid':
            result = _handle_completed(dict(session))
            if result.get('status') == 'success':
                recovered += 1
        elif session.get('status') == 'expired':
            _handle_expired(dict(session))

    return {'checked': checked, 'recovered': recovered}


def savings_to_date(coffee_pass) -> Decimal:
    """Total the customer has actually saved. Voided redemptions don't count."""
    from django.db.models import Sum
    total = coffee_pass.redemptions.filter(
        status=RedemptionStatus.REDEEMED,
    ).aggregate(total=Sum('discount_amount_hkd'))['total']
    return total or Decimal('0.00')
