"""
Credit Engine — Reserve / Confirm / Refund saga (REQUIREMENTS § 0 #9 + § Phase 6).

THE single highest-risk code in the platform. Every balance mutation takes a
`select_for_update` row lock on the org's `UsageCreditBalance`, so concurrent
generations cannot double-spend. Deduction order is ALWAYS free → paid.

Saga:
  reserve_credits  → lock, idempotency check, cap/credit check, bump reserved,
                     append a `reserved` UsageEvent.
  confirm_credits  → lock, move reserved → used (free first), set actual cost,
                     event → success, recompute cap.
  refund_credits   → lock, release reservation, restore any used credits,
                     append a NEW `refunded` event, original → failed.
  reset_monthly_credits → period rollover: free reset to plan grant, paid kept.

Contract is exactly what `content_studio.services.credits` expects, so Phase 5
delegates to this with zero code change.
"""
import logging
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..models import (
    UsageCreditBalance, UsageEvent, UsageLimit,
    EventStatus, UsageModule,
)
from . import cap_monitor

logger = logging.getLogger(__name__)


class InsufficientCreditsError(Exception):
    """Raised when the spend cap / credit balance blocks a reservation."""


# ── helpers ──────────────────────────────────────────────────────────────

def _usd_to_hkd(cost_usd: Decimal) -> Decimal:
    rate = Decimal(str(settings.BILLING_SETTINGS.get('USD_TO_HKD', 7.8)))
    return (Decimal(cost_usd) * rate).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)


def _module_for_event_type(event_type: str) -> str:
    if event_type.startswith('content_studio'):
        return UsageModule.CONTENT_STUDIO
    if event_type.startswith('inventory'):
        return UsageModule.INVENTORY_AI
    if event_type.startswith('chatbot') or event_type.startswith('ai'):
        return UsageModule.CHATBOT_AI
    return UsageModule.CHATBOT_AI


def _ensure_balance(org):
    """Get-or-provision the locked-row balance. Provisioning is idempotent."""
    from .provisioning import ensure_billing_for_org
    bal = UsageCreditBalance.objects.filter(organization=org).first()
    if bal is None:
        ensure_billing_for_org(org)
    return UsageCreditBalance.objects.get(organization=org)


def _check_cap_and_credits(balance, limit, credits):
    """(allowed, reason). Blocks if no credits available OR spend cap reached."""
    if balance.cap_status == 'blocked':
        return False, 'Monthly AI spend cap reached. Raise the limit to continue.'
    cap = limit.monthly_ai_spend_cap_hkd if limit else Decimal('200')
    if cap and balance.current_estimated_spend_hkd >= cap:
        return False, 'Monthly AI spend cap reached. Raise the limit to continue.'
    if balance.total_available < credits:
        return False, 'Not enough credits remaining for this generation.'
    return True, ''


def get_event(event_id):
    """Fetch a UsageEvent by id (used by the Content Studio adapter)."""
    return UsageEvent.objects.get(id=event_id)


# ── saga ────────────────────────────────────────────────────────────────

def reserve_credits(org, credits, *, event_type, provider, model,
                    cost_usd_estimate, reference_id, idempotency_key, user=None):
    """Atomic reservation. Idempotent on idempotency_key.

    Raises InsufficientCreditsError when the cap/credits block it (caller maps
    that to blocked_by_cap with NO charge).
    """
    credits = int(credits)
    with transaction.atomic():
        # Idempotency: a retry with the same key returns the existing event and
        # does NOT reserve again. Checked inside the txn for safety.
        if idempotency_key:
            existing = UsageEvent.objects.filter(idempotency_key=idempotency_key).first()
            if existing is not None:
                return existing

        balance = UsageCreditBalance.objects.select_for_update().get(organization=org)  # ROW LOCK
        limit = UsageLimit.objects.filter(organization=org).first()

        allowed, reason = _check_cap_and_credits(balance, limit, credits)
        if not allowed:
            raise InsufficientCreditsError(reason)

        # Decide free/paid split for THIS reservation (free first).
        free_avail = max(0, balance.free_credits_remaining - balance.reserved_credits)
        reserved_free = min(credits, free_avail)
        reserved_paid = credits - reserved_free

        balance.reserved_credits += credits
        balance.save(update_fields=['reserved_credits', 'updated_at'])

        event = UsageEvent.objects.create(
            organization=org,
            user=user,
            module=_module_for_event_type(event_type),
            event_type=event_type,
            provider=provider or '',
            model=model or '',
            credits_used=credits,
            is_free_credit=(reserved_paid == 0),
            cost_usd=Decimal(cost_usd_estimate or 0),
            cost_hkd=_usd_to_hkd(cost_usd_estimate or 0),
            billable_amount_hkd=Decimal('0'),  # set on confirm (paid credits only)
            status=EventStatus.RESERVED,
            reference_id=reference_id,
            idempotency_key=idempotency_key,
            reserved_free=reserved_free,
            reserved_paid=reserved_paid,
        )
        return event


def confirm_credits(event, *, credits_actual, cost_usd_actual):
    """On provider success: reserved → used (free first), set actual cost."""
    credits_actual = int(credits_actual)
    with transaction.atomic():
        balance = UsageCreditBalance.objects.select_for_update().get(
            organization=event.organization_id,
        )
        reserved_total = event.reserved_free + event.reserved_paid

        # Release the originally-reserved amount.
        balance.reserved_credits = max(0, balance.reserved_credits - reserved_total)

        # Consume the actual credits, free first, capped by what was reserved.
        spend_free = min(event.reserved_free, credits_actual)
        spend_paid = min(event.reserved_paid, credits_actual - spend_free)

        balance.free_credits_remaining = max(0, balance.free_credits_remaining - spend_free)
        balance.paid_credits_remaining = max(0, balance.paid_credits_remaining - spend_paid)
        balance.free_credits_used_this_month += spend_free
        balance.paid_credits_used_this_month += spend_paid

        cost_hkd = _usd_to_hkd(cost_usd_actual or 0)
        # Only paid credits are billable; free credits cost the customer nothing.
        billable = cost_hkd if spend_paid > 0 else Decimal('0')
        balance.current_estimated_spend_hkd = (
            balance.current_estimated_spend_hkd + billable
        ).quantize(Decimal('0.01'))
        balance.save(update_fields=[
            'reserved_credits', 'free_credits_remaining', 'paid_credits_remaining',
            'free_credits_used_this_month', 'paid_credits_used_this_month',
            'current_estimated_spend_hkd', 'updated_at',
        ])

        # Append-only: we set terminal fields exactly once on the reserved row.
        UsageEvent.objects.filter(pk=event.pk).update(
            status=EventStatus.SUCCESS,
            credits_used=credits_actual,
            is_free_credit=(spend_paid == 0),
            cost_usd=Decimal(cost_usd_actual or 0),
            cost_hkd=cost_hkd,
            billable_amount_hkd=billable,
        )
        cap_monitor.recompute_cap_status(balance, persist=True)


def refund_credits(event):
    """On provider failure/cancel: release reservation, restore used credits,
    append a NEW refunded event. Original → failed. Technical failures never charge.
    """
    with transaction.atomic():
        balance = UsageCreditBalance.objects.select_for_update().get(
            organization=event.organization_id,
        )
        fresh = UsageEvent.objects.select_for_update().get(pk=event.pk)

        if fresh.status == EventStatus.RESERVED:
            # Reserved but never confirmed → just release the reservation.
            reserved_total = fresh.reserved_free + fresh.reserved_paid
            balance.reserved_credits = max(0, balance.reserved_credits - reserved_total)
        elif fresh.status == EventStatus.SUCCESS:
            # Already consumed → give the credits back to the right buckets and
            # back out the billable spend.
            balance.free_credits_remaining += fresh.reserved_free
            balance.paid_credits_remaining += fresh.reserved_paid
            balance.free_credits_used_this_month = max(
                0, balance.free_credits_used_this_month - fresh.reserved_free)
            balance.paid_credits_used_this_month = max(
                0, balance.paid_credits_used_this_month - fresh.reserved_paid)
            balance.current_estimated_spend_hkd = max(
                Decimal('0'),
                balance.current_estimated_spend_hkd - fresh.billable_amount_hkd,
            )
        else:
            # Already failed/refunded → nothing to do (idempotent).
            return

        balance.save()

        UsageEvent.objects.filter(pk=fresh.pk).update(status=EventStatus.FAILED)
        UsageEvent.objects.create(
            organization_id=fresh.organization_id,
            user_id=fresh.user_id,
            module=fresh.module,
            event_type=fresh.event_type,
            provider=fresh.provider,
            model=fresh.model,
            credits_used=fresh.credits_used,
            is_free_credit=fresh.is_free_credit,
            cost_usd=Decimal('0'),
            cost_hkd=Decimal('0'),
            billable_amount_hkd=Decimal('0'),
            status=EventStatus.REFUNDED,
            reference_id=fresh.reference_id,
            idempotency_key=None,  # the refund row never collides on the unique key
            metadata={'refund_of': str(fresh.pk)},
        )
        cap_monitor.recompute_cap_status(balance, persist=True)


def add_paid_credits(org, credits, *, reference_id=None, user=None,
                     event_type='credit_purchase', provider='stripe',
                     metadata=None):
    """Top up paid credits (e.g. a Stripe credit-pack purchase).

    Row-locked. Appends a `success` UsageEvent recording the grant (credits as
    a negative-spend top-up is not modeled; we record credits_used=credits with
    is_free_credit=False and zero cost — the *purchase* cost lives on the
    payments.CreditPurchase row, not here, to keep this ledger about AI usage).
    Returns the created UsageEvent. The caller is responsible for its own
    idempotency latch (payments.CreditPurchase.credited) — this function does
    NOT dedupe, so only call it once per paid purchase.
    """
    credits = int(credits)
    with transaction.atomic():
        balance = UsageCreditBalance.objects.select_for_update().get(organization=org)
        balance.paid_credits_remaining += credits
        balance.save(update_fields=['paid_credits_remaining', 'updated_at'])
        event = UsageEvent.objects.create(
            organization=org,
            user=user,
            module=UsageModule.CONTENT_STUDIO,
            event_type=event_type,
            provider=provider,
            credits_used=credits,
            is_free_credit=False,
            cost_usd=Decimal('0'),
            cost_hkd=Decimal('0'),
            billable_amount_hkd=Decimal('0'),
            status=EventStatus.SUCCESS,
            reference_id=reference_id,
            metadata={**(metadata or {}), 'kind': 'credit_topup'},
        )
        return event


def deduct_paid_credits(org, credits, *, reference_id=None, metadata=None):
    """Remove paid credits (e.g. a refunded credit-pack purchase). Row-locked.

    Floors at zero — if the org already spent the purchased credits we don't
    drive the balance negative (the money refund still goes back via Stripe;
    the wallet simply can't be clawed below zero).
    """
    credits = int(credits)
    with transaction.atomic():
        balance = UsageCreditBalance.objects.select_for_update().get(organization=org)
        balance.paid_credits_remaining = max(0, balance.paid_credits_remaining - credits)
        balance.save(update_fields=['paid_credits_remaining', 'updated_at'])
        UsageEvent.objects.create(
            organization=org,
            module=UsageModule.CONTENT_STUDIO,
            event_type='credit_purchase_refund',
            provider='stripe',
            credits_used=credits,
            is_free_credit=False,
            status=EventStatus.REFUNDED,
            reference_id=reference_id,
            metadata={**(metadata or {}), 'kind': 'credit_topup_refund'},
        )
        return balance


def reset_monthly_credits(org):
    """Period rollover: free credits reset to the plan grant; paid untouched."""
    from .provisioning import _plan_for_org
    with transaction.atomic():
        balance = UsageCreditBalance.objects.select_for_update().get(organization=org)
        plan = _plan_for_org(org)
        grant = plan.monthly_image_credits if plan else 0
        balance.free_credits_remaining = grant
        balance.free_credits_used_this_month = 0
        balance.paid_credits_used_this_month = 0
        balance.current_estimated_spend_hkd = Decimal('0')
        balance.period_start = timezone.now().date().replace(day=1)
        # reserved_credits intentionally left as-is (in-flight reservations survive)
        balance.save()
        cap_monitor.recompute_cap_status(balance, persist=True)
        return balance
