"""
Stripe payment services — AI credit-pack purchases.

Card data never touches our servers (Stripe Checkout, PCI-compliant). The
purchase saga:

  create_checkout_session  → CreditPurchase(pending) + Stripe Checkout URL
  checkout.session.completed (webhook) → atomically grant paid credits to the
      Phase 6 wallet, latch the purchase as credited (one-way), idempotent.
  checkout.session.expired (webhook) → mark the pending order expired.
  charge.refunded (webhook) → record refund + claw paid credits (floored at 0).

Idempotency is layered:
  1. Webhook event-id claim (atomic cache.add) at the view — dedupes deliveries.
  2. CreditPurchase.stripe_payment_intent_id / stripe_session_id UNIQUE — dedupes
     across event types and restarts.
  3. CreditPurchase.credited one-way latch inside the locked grant txn — even a
     logic bug can't double-credit.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Organization
from apps.billing.services import credit_service

from .models import CreditPack, CreditPurchase
from .stripe_client import get_stripe

logger = logging.getLogger(__name__)

WEBHOOK_IDEMPOTENCY_TTL = 60 * 60 * 24  # 24h — covers Stripe's retry window


class CreditCheckoutService:
    """Creates Stripe Checkout Sessions for credit-pack purchases."""

    @staticmethod
    def create_checkout_session(*, organization: Organization, pack: CreditPack,
                                user=None, success_url: str | None = None,
                                cancel_url: str | None = None) -> dict:
        if not pack.is_active:
            raise ValueError('This credit pack is not available.')

        stripe = get_stripe()
        public_url = settings.PUBLIC_BASE_URL.rstrip('/')

        # Create the pending order FIRST so we have a stable reference id to put
        # in Stripe metadata; the webhook resolves back to it.
        purchase = CreditPurchase.objects.create(
            organization=organization,
            pack=pack,
            initiated_by=user,
            status=CreditPurchase.Status.PENDING,
            credits=pack.credits,
            amount_hkd=pack.price_hkd,
            currency=pack.currency,
        )

        if not success_url:
            success_url = (
                f'{public_url}/billing?purchase={purchase.id}'
                f'&session_id={{CHECKOUT_SESSION_ID}}'
            )
        if not cancel_url:
            cancel_url = f'{public_url}/billing?purchase={purchase.id}&cancelled=1'

        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            mode='payment',
            line_items=[{
                'price_data': {
                    'currency': pack.currency,
                    'unit_amount': pack.amount_cents,
                    'product_data': {
                        'name': f'{pack.name} — {pack.credits} AI credits',
                        'description': pack.description or f'{pack.credits} paid AI credits for Kribaat.',
                    },
                },
                'quantity': 1,
            }],
            client_reference_id=str(purchase.id),
            metadata={
                'purchase_id': str(purchase.id),
                'organization_id': str(organization.id),
                'pack_slug': pack.slug,
                'credits': str(pack.credits),
            },
            # Idempotency on the create call itself — a retried POST returns the
            # same session instead of opening a second one for this purchase.
            idempotency_key=f'checkout_create_{purchase.id}',
            success_url=success_url,
            cancel_url=cancel_url,
        )

        purchase.stripe_session_id = session['id']
        purchase.save(update_fields=['stripe_session_id', 'updated_at'])

        logger.info('Stripe credit checkout created', extra={
            'purchase_id': str(purchase.id), 'session_id': session['id'],
            'org': str(organization.id), 'credits': pack.credits,
        })

        return {
            'purchase_id': str(purchase.id),
            'checkout_url': session['url'],
            'session_id': session['id'],
            'credits': pack.credits,
            'amount_hkd': str(pack.price_hkd),
            'currency': pack.currency,
        }


class StripeWebhookService:
    """Verifies + processes Stripe webhook events with layered idempotency."""

    @staticmethod
    def verify_and_construct_event(payload: bytes, sig_header: str):
        stripe = get_stripe()
        secret = settings.STRIPE_WEBHOOK_SECRET
        if not secret:
            raise ValueError('STRIPE_WEBHOOK_SECRET is not configured.')
        # construct_event raises SignatureVerificationError on a forged payload.
        return stripe.Webhook.construct_event(payload, sig_header, secret)

    # ── event-id idempotency (atomic claim, release-on-failure) ───────────
    @staticmethod
    def _event_key(event_id: str) -> str:
        return f'stripe_pay_event:{event_id}'

    @classmethod
    def is_duplicate_event(cls, event_id: str) -> bool:
        # cache.add is atomic SET-NX: True if we won the claim, False if it
        # already existed (someone else is handling / handled it).
        claimed = cache.add(cls._event_key(event_id), 'processing', WEBHOOK_IDEMPOTENCY_TTL)
        return not claimed

    @classmethod
    def mark_event_processed(cls, event_id: str) -> None:
        cache.set(cls._event_key(event_id), 'done', WEBHOOK_IDEMPOTENCY_TTL)

    @classmethod
    def release_event(cls, event_id: str) -> None:
        # Drop a provisional claim so a Stripe retry isn't silently masked.
        cache.delete(cls._event_key(event_id))

    @classmethod
    def handle_event(cls, event) -> dict:
        handlers = {
            'checkout.session.completed': cls._handle_completed,
            'checkout.session.expired': cls._handle_expired,
            'charge.refunded': cls._handle_refunded,
            'payment_intent.payment_failed': cls._handle_failed,
        }
        handler = handlers.get(event['type'])
        if handler:
            return handler(event['data']['object'])
        logger.info('Unhandled Stripe event: %s', event['type'])
        return {'status': 'ignored', 'event_type': event['type']}

    # ── handlers ─────────────────────────────────────────────────────────
    @classmethod
    @transaction.atomic
    def _handle_completed(cls, session) -> dict:
        purchase_id = session.get('client_reference_id') \
            or (session.get('metadata') or {}).get('purchase_id')
        if not purchase_id:
            logger.error('Checkout completed without purchase ref', extra={'session': session.get('id')})
            return {'status': 'error', 'reason': 'missing_purchase_ref'}

        try:
            # ROW LOCK: serialize concurrent deliveries of the same purchase.
            purchase = CreditPurchase.objects.select_for_update().get(id=purchase_id)
        except CreditPurchase.DoesNotExist:
            logger.error('Purchase not found for session', extra={'purchase_id': purchase_id})
            return {'status': 'error', 'reason': 'purchase_not_found'}

        # One-way latch: if already credited, this is a replay → no-op.
        if purchase.credited:
            return {'status': 'duplicate', 'purchase_id': str(purchase.id)}

        payment_intent = session.get('payment_intent', '') or ''

        # Defense-in-depth: a *different* purchase already credited from this PI
        # means a replay/forgery — refuse to double-grant.
        if payment_intent and CreditPurchase.objects.filter(
            stripe_payment_intent_id=payment_intent, credited=True,
        ).exclude(pk=purchase.pk).exists():
            logger.warning('Payment intent already credited elsewhere', extra={'pi': payment_intent})
            return {'status': 'duplicate', 'reason': 'intent_already_credited'}

        # Grant the paid credits into the Phase 6 wallet (row-locked there too).
        event = credit_service.add_paid_credits(
            purchase.organization, purchase.credits,
            reference_id=purchase.id,
            user=purchase.initiated_by,
            metadata={'purchase_id': str(purchase.id), 'session_id': session.get('id', '')},
        )

        receipt_url = ''
        try:
            receipt_url = cls._fetch_receipt_url(payment_intent)
        except Exception:  # observability only — never block the grant
            logger.warning('Could not fetch Stripe receipt URL', exc_info=True)

        purchase.status = CreditPurchase.Status.PAID
        purchase.credited = True  # the latch
        purchase.stripe_payment_intent_id = payment_intent
        purchase.stripe_receipt_url = receipt_url
        purchase.usage_event_id = event.id
        purchase.paid_at = timezone.now()
        purchase.save(update_fields=[
            'status', 'credited', 'stripe_payment_intent_id', 'stripe_receipt_url',
            'usage_event_id', 'paid_at', 'updated_at',
        ])

        logger.info('Credit purchase fulfilled', extra={
            'purchase_id': str(purchase.id), 'org': str(purchase.organization_id),
            'credits': purchase.credits,
        })
        return {'status': 'success', 'purchase_id': str(purchase.id), 'credits': purchase.credits}

    @classmethod
    @transaction.atomic
    def _handle_expired(cls, session) -> dict:
        purchase_id = session.get('client_reference_id') \
            or (session.get('metadata') or {}).get('purchase_id')
        if not purchase_id:
            return {'status': 'skipped', 'reason': 'no_ref'}
        try:
            purchase = CreditPurchase.objects.select_for_update().get(id=purchase_id)
        except CreditPurchase.DoesNotExist:
            return {'status': 'skipped', 'reason': 'not_found'}
        # Never touch a paid/credited order.
        if purchase.status == CreditPurchase.Status.PENDING and not purchase.credited:
            purchase.status = CreditPurchase.Status.EXPIRED
            purchase.save(update_fields=['status', 'updated_at'])
            return {'status': 'expired', 'purchase_id': str(purchase.id)}
        return {'status': 'skipped', 'reason': 'not_pending'}

    @classmethod
    @transaction.atomic
    def _handle_refunded(cls, charge) -> dict:
        payment_intent = charge.get('payment_intent', '') or ''
        if not payment_intent:
            return {'status': 'ignored', 'reason': 'no_payment_intent'}
        purchase = CreditPurchase.objects.select_for_update().filter(
            stripe_payment_intent_id=payment_intent, credited=True,
        ).first()
        if not purchase:
            return {'status': 'skipped', 'reason': 'purchase_not_found'}

        refunded_total = Decimal(str(charge.get('amount_refunded', 0))) / Decimal('100')
        # Idempotent: only act on the *new* refunded delta beyond what we recorded.
        new_delta = refunded_total - purchase.refunded_amount_hkd
        if new_delta <= Decimal('0'):
            return {'status': 'duplicate', 'reason': 'already_recorded'}

        # Proportionally claw back credits for the newly-refunded amount.
        if purchase.amount_hkd > 0:
            credits_to_remove = int(
                (new_delta / purchase.amount_hkd) * purchase.credits
            )
        else:
            credits_to_remove = 0
        if credits_to_remove > 0:
            credit_service.deduct_paid_credits(
                purchase.organization, credits_to_remove,
                reference_id=purchase.id,
                metadata={'purchase_id': str(purchase.id), 'charge': charge.get('id', '')},
            )

        purchase.refunded_amount_hkd = refunded_total
        purchase.stripe_charge_id = charge.get('id', '') or purchase.stripe_charge_id
        if refunded_total >= purchase.amount_hkd:
            purchase.status = CreditPurchase.Status.REFUNDED
        purchase.save(update_fields=[
            'refunded_amount_hkd', 'stripe_charge_id', 'status', 'updated_at',
        ])
        logger.info('Credit purchase refunded', extra={
            'purchase_id': str(purchase.id), 'refunded': str(refunded_total),
            'credits_removed': credits_to_remove,
        })
        return {'status': 'refunded', 'purchase_id': str(purchase.id),
                'credits_removed': credits_to_remove}

    @classmethod
    def _handle_failed(cls, payment_intent) -> dict:
        pi_id = payment_intent.get('id', '')
        msg = (payment_intent.get('last_payment_error') or {}).get('message', 'unknown')
        logger.warning('Stripe payment failed', extra={'pi': pi_id, 'msg': msg})
        # We do NOT cancel the pending order — the customer may retry within the
        # session window. Expiry is the authoritative abandonment signal.
        return {'status': 'payment_failed', 'payment_intent': pi_id}

    @staticmethod
    def _fetch_receipt_url(payment_intent_id: str) -> str:
        if not payment_intent_id:
            return ''
        stripe = get_stripe()
        intent = stripe.PaymentIntent.retrieve(payment_intent_id, expand=['latest_charge'])
        charge = getattr(intent, 'latest_charge', None)
        if isinstance(charge, str) or charge is None:
            return ''
        return getattr(charge, 'receipt_url', '') or ''


class StripeRefundService:
    """Issue a Stripe refund for a credit purchase (owner/admin action)."""

    @staticmethod
    @transaction.atomic
    def create_refund(*, purchase: CreditPurchase, amount_hkd: Decimal | None = None,
                      reason: str = 'requested_by_customer') -> dict:
        stripe = get_stripe()
        # Lock the order so two concurrent refund requests can't over-refund.
        purchase = CreditPurchase.objects.select_for_update().get(pk=purchase.pk)

        if not purchase.credited or not purchase.stripe_payment_intent_id:
            raise ValueError('This purchase has no captured payment to refund.')

        max_refundable = purchase.amount_hkd - purchase.refunded_amount_hkd
        if amount_hkd is None:
            amount_hkd = max_refundable
        if amount_hkd <= Decimal('0'):
            raise ValueError('Nothing left to refund.')
        if amount_hkd > max_refundable:
            raise ValueError(f'Refund {amount_hkd} exceeds refundable {max_refundable}.')

        refund = stripe.Refund.create(
            payment_intent=purchase.stripe_payment_intent_id,
            amount=int(amount_hkd * 100),
            reason=reason,
            idempotency_key=f'refund_{purchase.id}_{int(amount_hkd * 100)}',
        )
        # The charge.refunded webhook does the credit claw-back + status update
        # (single source of truth). We only return the Stripe result here.
        logger.info('Stripe refund requested', extra={
            'purchase_id': str(purchase.id), 'refund_id': refund.id, 'amount': str(amount_hkd),
        })
        return {'refund_id': refund.id, 'amount_hkd': str(amount_hkd), 'status': refund.status}
