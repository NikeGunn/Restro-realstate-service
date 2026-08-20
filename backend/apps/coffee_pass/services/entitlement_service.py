"""
Entitlement service — THE single authority on whether a pass may redeem.

Manual staff redemption uses it today; the future POS adapter (Appendix A.8)
will call the same functions. That is the whole point: there must never be two
implementations of "is this pass valid", because they will drift and one of them
will be wrong at the till.

Nothing here mutates. Consumption happens in redemption_service, inside the
final transaction, so a preview can never burn a customer's code.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone

from ..models import PassStatus

# Stable reason codes for a refusal. The staff UI maps these to safe copy.
REASON_VALID = 'valid'
REASON_NOT_FOUND = 'not_found'
REASON_EXPIRED = 'expired'
REASON_SUSPENDED = 'suspended'
REASON_CANCELLED = 'cancelled'
REASON_PENDING_PAYMENT = 'pending_payment'
REASON_WRONG_LOCATION = 'wrong_location'
REASON_NOT_STARTED = 'not_started'

#: Tolerance on the start boundary. `starts_at` is stamped at activation time,
#: so a customer minting a code in the same instant can otherwise be refused
#: `not_started` by a few microseconds of clock skew between the web process and
#: the database. Seconds of grace at the START of a 30-day window is harmless;
#: the EXPIRY boundary gets no such tolerance.
_START_GRACE_SECONDS = 5

_STATUS_REASONS = {
    PassStatus.EXPIRED: REASON_EXPIRED,
    PassStatus.SUSPENDED: REASON_SUSPENDED,
    PassStatus.CANCELLED: REASON_CANCELLED,
    PassStatus.PENDING_PAYMENT: REASON_PENDING_PAYMENT,
}


@dataclass(frozen=True)
class EntitlementCheck:
    """Result of asking "can this pass redeem, here, now?"."""
    valid: bool
    reason_code: str
    coffee_pass: object | None = None

    def as_dict(self) -> dict:
        return {'valid': self.valid, 'reason_code': self.reason_code}


def check(coffee_pass, *, location=None, at=None) -> EntitlementCheck:
    """
    Validate a pass for use at `location` at time `at`.

    Order matters: existence -> status -> window -> location. Location is checked
    LAST so that a customer presenting a valid pass at the wrong cafe gets the
    specific `wrong_location` message rather than a generic refusal.
    """
    if coffee_pass is None:
        return EntitlementCheck(False, REASON_NOT_FOUND)

    at = at or timezone.now()

    if coffee_pass.status != PassStatus.ACTIVE:
        return EntitlementCheck(
            False, _STATUS_REASONS.get(coffee_pass.status, REASON_NOT_FOUND), coffee_pass,
        )

    # Query-time expiry is the FINAL guard — the Celery sweeper is housekeeping,
    # not the authority. A pass past its window is invalid even if the sweeper
    # has not run yet.
    if coffee_pass.expires_at <= at:
        return EntitlementCheck(False, REASON_EXPIRED, coffee_pass)
    # Grace only on the START edge (see _START_GRACE_SECONDS); expiry is exact.
    if coffee_pass.starts_at > at + timedelta(seconds=_START_GRACE_SECONDS):
        return EntitlementCheck(False, REASON_NOT_STARTED, coffee_pass)

    if location is not None:
        location_id = getattr(location, 'pk', location)
        if str(coffee_pass.location_id) != str(location_id):
            return EntitlementCheck(False, REASON_WRONG_LOCATION, coffee_pass)

    return EntitlementCheck(True, REASON_VALID, coffee_pass)


def calculate_discount(coffee_pass, eligible_subtotal) -> Decimal:
    """
    discount = round(eligible_subtotal * snapshot_discount% / 100, 2)

    Reads the pass SNAPSHOT, never the live plan — a plan repriced after the sale
    must not change what an existing member is owed. Banker's rounding is wrong
    for money the customer sees, so we force ROUND_HALF_UP.
    """
    subtotal = Decimal(str(eligible_subtotal))
    if subtotal <= 0:
        return Decimal('0.00')
    percent = coffee_pass.discount_percent
    raw = subtotal * percent / Decimal('100')
    return raw.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def preview(coffee_pass, *, location=None, at=None) -> dict:
    """
    Operational detail for the staff redemption screen.

    PRIVACY (A.9): deliberately excludes the customer's feedback comment, CRM
    history, and internal notes. Staff get exactly what they need to apply a
    discount correctly and nothing more.
    """
    result = check(coffee_pass, location=location, at=at)
    if not result.valid:
        return {'valid': False, 'reason_code': result.reason_code}

    snapshot = coffee_pass.plan_snapshot or {}
    return {
        'valid': True,
        'reason_code': REASON_VALID,
        'pass_id': str(coffee_pass.id),
        'customer_name': coffee_pass.customer.name,
        'plan_name': snapshot.get('name', ''),
        'discount_percent': str(coffee_pass.discount_percent),
        'expires_at': coffee_pass.expires_at.isoformat(),
        'location_id': str(coffee_pass.location_id),
        'eligible_items': snapshot.get('eligible_items', []),
        'redemption_count': coffee_pass.redemptions.filter(status='redeemed').count(),
    }
