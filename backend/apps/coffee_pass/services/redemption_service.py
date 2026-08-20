"""
Manual redemption + owner-only void.

The whole feature's integrity narrows to `redeem()`. Two staff members can scan
the same customer's phone at two tills in the same second; a flaky POS makes the
barista tap Confirm twice. Exactly one redemption must exist afterwards.

How that is guaranteed, in order inside ONE transaction:
  1. `verification_service.consume()` does a conditional UPDATE on the token —
     one atomic statement, so exactly one caller gets rowcount 1.
  2. That call returns the pass under `select_for_update()`, so the entitlement
     re-check below cannot race a concurrent expiry/suspension.
  3. Entitlement is re-validated AFTER the lock, not before — checking first and
     writing later is the classic TOCTOU hole.
  4. The discount is computed server-side from the pass SNAPSHOT. The staff
     client sends a subtotal; it never sends a discount.
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..models import (
    CoffeePassAuditEvent, CoffeePassRedemption, RedemptionStatus,
)
from . import audit_service, entitlement_service, experience_service, verification_service

logger = logging.getLogger(__name__)


class RedemptionError(Exception):
    """Stable reason code -> the view maps it to a specific HTTP status."""

    def __init__(self, reason, detail=None):
        self.reason = reason
        self.detail = detail or {}
        super().__init__(reason)


def _cfg(key, default):
    return getattr(settings, 'COFFEE_PASS_SETTINGS', {}).get(key, default)


def validate_subtotal(raw) -> Decimal:
    """
    Parse and bound the staff-entered eligible subtotal.

    The cap exists because a mistyped extra zero would otherwise record a
    HK$20,000 "discount" and poison every retention metric the owner reads.
    """
    try:
        subtotal = Decimal(str(raw)).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError, ValueError):
        raise RedemptionError('invalid_subtotal')

    if subtotal < 0:
        raise RedemptionError('invalid_subtotal')

    cap = Decimal(str(_cfg('MAX_ELIGIBLE_SUBTOTAL_HKD', 2000)))
    if subtotal > cap:
        raise RedemptionError('subtotal_exceeds_cap', {'cap_hkd': str(cap)})
    return subtotal


@transaction.atomic
def redeem(*, verification_token_id, eligible_subtotal, user, location=None,
           pos_receipt_reference='', correlation_id='', ip=None):
    """
    Consume a verification token and record one redemption.

    Returns the CoffeePassRedemption. Raises RedemptionError with a stable reason
    on every refusal path so the staff UI can show precise, safe copy.
    """
    subtotal = validate_subtotal(eligible_subtotal)

    # (1)+(2): atomic burn; returns the row-locked pass, or None if we lost the race.
    coffee_pass = verification_service.consume(verification_token_id, user=user)
    if coffee_pass is None:
        raise RedemptionError('code_already_used_or_expired')

    # (3) Re-validate under the lock. A pass that expired or was suspended
    # between mint and commit must be refused even though the token was live.
    check = entitlement_service.check(coffee_pass, location=location)
    if not check.valid:
        raise RedemptionError(check.reason_code)

    # Staff must belong to the pass's organization. Guards against a token
    # somehow resolved outside the scoped queryset.
    if not _user_in_org(user, coffee_pass.organization_id):
        raise RedemptionError('wrong_organization')

    # (4) Server-side money. The snapshot percent, never the live plan.
    discount = entitlement_service.calculate_discount(coffee_pass, subtotal)

    redemption = CoffeePassRedemption.objects.create(
        organization=coffee_pass.organization,
        location=coffee_pass.location,
        coffee_pass=coffee_pass,
        customer=coffee_pass.customer,
        redeemed_by=user if getattr(user, 'is_authenticated', False) else None,
        eligible_subtotal_hkd=subtotal,
        discount_amount_hkd=discount,
        discount_percent_applied=coffee_pass.discount_percent,
        pos_receipt_reference=(pos_receipt_reference or '').strip()[:100],
        status=RedemptionStatus.REDEEMED,
        redeemed_at=timezone.now(),
    )

    audit_service.record(
        organization=coffee_pass.organization, location=coffee_pass.location,
        action=CoffeePassAuditEvent.Action.REDEMPTION_CREATED,
        entity=redemption, actor=user,
        correlation_id=correlation_id, ip=ip,
        metadata={
            'pass_id': str(coffee_pass.id),
            'eligible_subtotal_hkd': str(subtotal),
            'discount_amount_hkd': str(discount),
            'has_receipt_reference': bool(pos_receipt_reference),
        },
    )
    audit_service.enqueue(
        organization=coffee_pass.organization,
        event_type=experience_service.EVENT_REDEMPTION_CREATED,
        aggregate=redemption,
        payload={
            'redemption_id': str(redemption.id),
            'pass_id': str(coffee_pass.id),
            'customer_id': str(coffee_pass.customer_id),
            'discount_amount_hkd': str(discount),
        },
    )

    logger.info('Coffee Pass redeemed', extra={
        'redemption_id': str(redemption.id), 'pass_id': str(coffee_pass.id),
    })
    return redemption


@transaction.atomic
def void(*, redemption, user, reason, correlation_id='', ip=None):
    """
    Owner-only correction. Flips status; NEVER deletes.

    Deleting would erase the fact that a discount was given, which is exactly
    what an abusive staff member would want. A void is itself an audited event.
    """
    reason = (reason or '').strip()
    if len(reason) < 5:
        raise RedemptionError('void_reason_required')

    locked = CoffeePassRedemption.objects.select_for_update().get(pk=redemption.pk)
    if locked.status == RedemptionStatus.VOIDED:
        raise RedemptionError('already_voided')

    locked.status = RedemptionStatus.VOIDED
    locked.voided_at = timezone.now()
    locked.voided_by = user if getattr(user, 'is_authenticated', False) else None
    locked.void_reason = reason[:255]
    locked.save(update_fields=['status', 'voided_at', 'voided_by', 'void_reason'])

    audit_service.record(
        organization=locked.organization, location=locked.location,
        action=CoffeePassAuditEvent.Action.REDEMPTION_VOIDED,
        entity=locked, actor=user, correlation_id=correlation_id, ip=ip,
        metadata={
            'pass_id': str(locked.coffee_pass_id),
            'discount_amount_hkd': str(locked.discount_amount_hkd),
            'reason': reason[:255],
        },
    )
    return locked


def _user_in_org(user, organization_id) -> bool:
    from apps.accounts.models import OrganizationMembership
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    return OrganizationMembership.objects.filter(
        user=user, organization_id=organization_id,
    ).exists()
