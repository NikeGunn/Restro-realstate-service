"""
Coffee Pass checkout — create a Stripe-hosted Checkout Session.

Modeled on `apps.payments.CreditCheckoutService` but with SEPARATE models,
routes, and webhook handling. Deliberately not shared: that saga tops up an
ORG's AI credit wallet, this one sells a CUSTOMER an entitlement. Merging them
would mean one function branching on "is this org money or customer money",
which is exactly the class of bug that ends with credits granted for a coffee.

Card data never reaches our servers (Stripe-hosted), so this stays PCI-light.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.conf import settings
from django.db import transaction

from apps.payments.stripe_client import get_stripe

from ..models import (
    CoffeePassAuditEvent, CoffeePassPurchase, PurchaseStatus,
)
from . import audit_service, offer_decision_service

logger = logging.getLogger(__name__)


class CheckoutError(Exception):
    """Raised with a stable reason code the public API maps to a 4xx."""

    def __init__(self, reason, detail=None):
        self.reason = reason
        self.detail = detail or {}
        super().__init__(reason)


def _public_base_url() -> str:
    return settings.PUBLIC_BASE_URL.rstrip('/')


def create_checkout(*, plan, customer, experience=None, correlation_id='', ip=None):
    """
    Re-validate eligibility server-side, then open a Checkout Session.

    Eligibility is re-checked HERE even though the client just saw an offer: the
    offer response is advisory and a client can post straight to this endpoint.
    The engine is the only authority, and it runs again on the server's facts.

    NOT wrapped in a single `atomic()`. The pending purchase must COMMIT before
    we call Stripe, because if Stripe then fails we need to mark that row FAILED
    — a rollback would leave it PENDING forever, and a stale PENDING purchase is
    a hard gate that would block the customer's next offer.

    Returns {purchase_id, checkout_url, session_id, amount_hkd, currency}.
    """
    decision = offer_decision_service.decide(
        plan=plan, customer=customer, experience=experience, session_verified=True,
    )
    # `soft_offer` customers may still buy — we just never pushed them. Only a
    # genuinely ineligible decision blocks checkout.
    if not decision.eligible:
        raise CheckoutError(decision.reason_code, decision.as_dict())

    snapshot = plan.build_snapshot()
    with transaction.atomic():
        purchase = CoffeePassPurchase.objects.create(
            organization=plan.organization,
            location=plan.location,
            customer=customer,
            plan=plan,
            experience=experience,
            status=PurchaseStatus.PENDING,
            plan_snapshot=snapshot,
            amount_hkd=plan.price_hkd,
            currency=plan.currency,
        )

    stripe = get_stripe()
    base = _public_base_url()
    return_path = f'{base}/public/coffee-pass/{plan.public_token}/'

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            mode='payment',
            line_items=[{
                'price_data': {
                    'currency': plan.currency,
                    'unit_amount': plan.amount_cents,
                    'product_data': {
                        'name': plan.name,
                        'description': (
                            f'{plan.discount_percent}% off eligible coffee for '
                            f'{plan.duration_days} days at {plan.location.name}.'
                        ),
                    },
                },
                'quantity': 1,
            }],
            client_reference_id=str(purchase.id),
            metadata={
                'kind': 'coffee_pass',  # lets the webhook route without guessing
                'purchase_id': str(purchase.id),
                'organization_id': str(plan.organization_id),
                'location_id': str(plan.location_id),
                'customer_id': str(customer.id),
                'plan_id': str(plan.id),
            },
            # Same purchase -> same session, even if the POST is retried.
            idempotency_key=f'coffee_pass_checkout_{purchase.id}',
            success_url=f'{return_path}?checkout=success&session_id={{CHECKOUT_SESSION_ID}}',
            cancel_url=f'{return_path}?checkout=cancelled',
        )
    except Exception as exc:
        logger.exception('Stripe checkout creation failed for purchase %s', purchase.id)
        # Mark the orphan so reconciliation doesn't keep probing Stripe for a
        # session that was never created.
        purchase.status = PurchaseStatus.FAILED
        purchase.save(update_fields=['status', 'updated_at'])
        raise CheckoutError('stripe_unavailable') from exc

    purchase.stripe_session_id = session['id']
    purchase.save(update_fields=['stripe_session_id', 'updated_at'])

    audit_service.record(
        organization=plan.organization, location=plan.location,
        action=CoffeePassAuditEvent.Action.CHECKOUT_STARTED,
        entity=purchase, actor_customer=customer,
        correlation_id=correlation_id, ip=ip,
        metadata={'session_id': session['id'], 'amount_hkd': str(plan.price_hkd)},
    )

    return {
        'purchase_id': str(purchase.id),
        'checkout_url': session['url'],
        'session_id': session['id'],
        'amount_hkd': str(plan.price_hkd),
        'currency': plan.currency,
        'break_even_visits': decision.break_even.break_even_visits,
    }


def expire_stale_pending(*, older_than_minutes=None) -> int:
    """
    Mark abandoned pending purchases expired.

    Matters because a lingering PENDING purchase is a hard gate on a new offer
    (`checkout_pending`) — without this sweep, one abandoned tab would lock a
    customer out of buying until the Stripe session expired on its own.
    """
    from django.utils import timezone

    minutes = older_than_minutes or getattr(
        settings, 'COFFEE_PASS_SETTINGS', {},
    ).get('PENDING_CHECKOUT_TTL_MINUTES', 60)
    cutoff = timezone.now() - timezone.timedelta(minutes=minutes)

    return CoffeePassPurchase.objects.filter(
        status=PurchaseStatus.PENDING, activated=False, created_at__lt=cutoff,
    ).update(status=PurchaseStatus.EXPIRED, updated_at=timezone.now())


def amount_from_session(session) -> Decimal:
    """Stripe reports the smallest currency unit; HKD has 2 decimals."""
    total = session.get('amount_total')
    if total is None:
        return Decimal('0')
    return (Decimal(str(total)) / Decimal('100')).quantize(Decimal('0.01'))
