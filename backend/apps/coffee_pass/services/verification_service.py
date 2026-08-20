"""
Rotating verification codes — mint in the wallet, consume at the till.

Threat model (PRD §13 / A.6): a screenshot of a pass must be worthless. So:
- the wallet mints a token that lives ~90 seconds;
- only the HASH is stored, so a DB leak cannot mint redemptions;
- consumption is a CONDITIONAL UPDATE, which is what actually makes two
  simultaneous scans resolve to exactly one redemption;
- the QR payload is an opaque random string — no pass id, no phone, no name,
  no discount percentage.

`resolve()` (staff preview) deliberately does NOT consume. Burning the code on
preview would strand a customer whenever a staff member opened the screen and
walked away. Consumption happens only in the final redemption transaction.
"""
from __future__ import annotations

import hashlib
import logging
import secrets

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..models import CoffeePass, CoffeePassVerificationToken, PassStatus

logger = logging.getLogger(__name__)

#: Fallback-code alphabet: digits only, easy to read aloud and type on a POS
#: keypad under time pressure.
_FALLBACK_DIGITS = 6


def _cfg(key, default):
    return getattr(settings, 'COFFEE_PASS_SETTINGS', {}).get(key, default)


def hash_token(raw: str) -> str:
    """Peppered SHA-256 — a leaked hash column can't be reversed to a code."""
    return hashlib.sha256(f'{settings.SECRET_KEY}:cp:{raw}'.encode('utf-8')).hexdigest()


def mint(coffee_pass, *, at=None):
    """
    Issue a fresh short-lived code for an ACTIVE pass. Returns (token, raw, fallback).

    Refuses to mint for a non-redeemable pass so an expired wallet can't produce
    a code that merely fails later at the counter.
    """
    from . import entitlement_service

    at = at or timezone.now()
    result = entitlement_service.check(coffee_pass, at=at)
    if not result.valid:
        raise ValueError(result.reason_code)

    ttl = _cfg('VERIFICATION_TOKEN_TTL_SECONDS', 90)
    raw = secrets.token_urlsafe(32)
    fallback = f'{secrets.randbelow(10 ** _FALLBACK_DIGITS):0{_FALLBACK_DIGITS}d}'

    # Retire this pass's outstanding codes: only the newest one is live, so an
    # old screenshot stops working the moment the wallet refreshes.
    CoffeePassVerificationToken.objects.filter(
        coffee_pass=coffee_pass, consumed_at__isnull=True,
    ).update(consumed_at=at)

    token = CoffeePassVerificationToken.objects.create(
        coffee_pass=coffee_pass,
        token_hash=hash_token(raw),
        fallback_hash=hash_token(fallback),
        expires_at=at + timezone.timedelta(seconds=ttl),
    )
    return token, raw, fallback


def _lookup(raw_value: str, *, organization=None):
    """
    Find a LIVE token by raw QR value or fallback code.

    Scoping by organization is what stops a code minted at one tenant from
    resolving at another. Expiry is evaluated at query time.
    """
    if not raw_value:
        return None
    hashed = hash_token(str(raw_value).strip())
    qs = CoffeePassVerificationToken.objects.select_related(
        'coffee_pass__customer', 'coffee_pass__plan',
    ).filter(consumed_at__isnull=True, expires_at__gt=timezone.now())
    if organization is not None:
        qs = qs.filter(coffee_pass__organization=organization)
    # A raw QR value and a typed fallback are both accepted at the same door.
    from django.db.models import Q
    return qs.filter(Q(token_hash=hashed) | Q(fallback_hash=hashed)).first()


def resolve(raw_value: str, *, organization, location=None):
    """
    Staff preview: validate a scanned/typed code WITHOUT consuming it.

    Returns a dict carrying the token id the staff client must echo back on
    commit, plus the privacy-filtered pass preview.
    """
    from . import entitlement_service

    token = _lookup(raw_value, organization=organization)
    if token is None:
        return {'valid': False, 'reason_code': 'invalid_or_expired_code'}

    preview = entitlement_service.preview(token.coffee_pass, location=location)
    if not preview.get('valid'):
        return preview

    preview['verification_token_id'] = str(token.id)
    preview['token_expires_at'] = token.expires_at.isoformat()
    return preview


@transaction.atomic
def consume(token_id, *, user=None, at=None):
    """
    Atomically burn a token. Returns the locked CoffeePass, or None if the token
    was already used / expired / missing.

    This is the concurrency-critical line in the whole feature. The conditional
    UPDATE (`filter(consumed_at__isnull=True).update(...)`) is a single atomic
    statement: of two racing staff commits exactly one gets rowcount 1, and the
    loser gets 0 and is refused. A read-then-write would leave a race window.
    """
    at = at or timezone.now()
    updated = CoffeePassVerificationToken.objects.filter(
        id=token_id, consumed_at__isnull=True, expires_at__gt=at,
    ).update(consumed_at=at, consumed_by=user)

    if not updated:
        return None

    token = CoffeePassVerificationToken.objects.select_related('coffee_pass').get(id=token_id)
    # Re-read the pass under a row lock: status/expiry are re-validated by the
    # caller inside this same transaction, so nothing can change underneath.
    return CoffeePass.objects.select_for_update().get(pk=token.coffee_pass_id)


def purge_expired(*, before=None) -> int:
    """Housekeeping: drop long-dead tokens. Never touches live or recent ones."""
    cutoff = before or (timezone.now() - timezone.timedelta(days=7))
    deleted, _ = CoffeePassVerificationToken.objects.filter(expires_at__lt=cutoff).delete()
    return deleted


def active_pass_for(customer, *, location=None):
    """The customer's currently-usable pass at a location, if any."""
    qs = CoffeePass.objects.filter(
        customer=customer, status=PassStatus.ACTIVE, expires_at__gt=timezone.now(),
    )
    if location is not None:
        qs = qs.filter(location=location)
    return qs.order_by('-expires_at').first()
