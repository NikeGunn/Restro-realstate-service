"""
Public customer identity — phone OTP + signed short-lived sessions.

Security contract (PRD §13):
- OTP codes are HASHED at rest, expire fast, and are attempt-limited.
- Responses are GENERIC: request-code returns the same shape whether or not the
  phone belongs to a known customer, so the endpoint cannot enumerate accounts.
- The session token is a signed, expiring token scoped to exactly ONE
  (organization, customer). It is NOT a dashboard JWT and grants no admin access.
- Rate limits are enforced per-phone and per-IP in Redis, on top of the DRF
  public throttles (which are per-IP only and therefore not sufficient alone).

The customer record is created ONLY on successful verification, so an attacker
spraying phone numbers cannot pollute the CRM.
"""
from __future__ import annotations

import hashlib
import logging
import secrets

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.utils import timezone

from apps.crm.services.customer_service import normalize_phone

from ..models import CoffeePassOTP

logger = logging.getLogger(__name__)

#: Namespace for the signed session token — a token minted for another purpose
#: can never be replayed as a Coffee Pass session.
SESSION_SALT = 'coffee_pass.customer_session'


class OTPError(Exception):
    """Raised with a stable, SAFE reason code — never leaks whether a phone exists."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def _settings():
    return getattr(settings, 'COFFEE_PASS_SETTINGS', {})


def _cfg(key, default):
    return _settings().get(key, default)


def hash_code(code: str) -> str:
    """
    SHA-256 with the project SECRET_KEY as a pepper.

    A raw SHA-256 of a 6-digit code is trivially rainbow-tabled; peppering means
    a database leak alone cannot recover codes.
    """
    return hashlib.sha256(f'{settings.SECRET_KEY}:{code}'.encode('utf-8')).hexdigest()


def generate_code() -> str:
    """A cryptographically random 6-digit code (secrets, never random)."""
    return f'{secrets.randbelow(1_000_000):06d}'


# ──────────────────────────────────────────────────────────────────────
# Rate limiting (per phone + per IP, on top of DRF's per-IP throttle)
# ──────────────────────────────────────────────────────────────────────
def _bump(key: str, window: int) -> int:
    """
    Increment a fixed-window counter. Fails OPEN (returns 0) on cache outage —
    consistent with Phase 0 idempotency: an outage must not lock customers out.
    """
    try:
        added = cache.add(key, 1, window)
        if added:
            return 1
        return cache.incr(key)
    except Exception:
        logger.warning('OTP rate-limit cache unavailable for %s', key)
        return 0


def check_send_limits(phone: str, ip: str) -> None:
    """Raise OTPError('rate_limited') when a phone or IP is asking too often."""
    window = _cfg('OTP_RATE_WINDOW_SECONDS', 3600)
    max_per_phone = _cfg('OTP_MAX_SENDS_PER_PHONE', 5)
    max_per_ip = _cfg('OTP_MAX_SENDS_PER_IP', 20)

    if phone and _bump(f'cp:otp:phone:{phone}', window) > max_per_phone:
        raise OTPError('rate_limited')
    if ip and _bump(f'cp:otp:ip:{hashlib.sha256(ip.encode()).hexdigest()[:32]}', window) > max_per_ip:
        raise OTPError('rate_limited')


# ──────────────────────────────────────────────────────────────────────
# OTP lifecycle
# ──────────────────────────────────────────────────────────────────────
def request_code(*, organization, phone, ip=''):
    """
    Mint and deliver an OTP. Returns (otp, raw_code).

    The CALLER must return a generic success regardless of outcome — the raw code
    is returned here only so delivery (and tests) can use it. It is never put in
    an HTTP response.
    """
    normalized = normalize_phone(phone)
    if not normalized:
        raise OTPError('invalid_phone')

    check_send_limits(normalized, ip)

    code = generate_code()
    ttl = _cfg('OTP_TTL_SECONDS', 300)

    # Invalidate outstanding codes for this phone: only the newest may verify,
    # so an attacker who saw an older SMS can't use it after a re-request.
    CoffeePassOTP.objects.filter(
        organization=organization, phone=normalized, consumed_at__isnull=True,
    ).update(consumed_at=timezone.now())

    otp = CoffeePassOTP.objects.create(
        organization=organization,
        phone=normalized,
        code_hash=hash_code(code),
        expires_at=timezone.now() + timezone.timedelta(seconds=ttl),
        ip_hash=hashlib.sha256(ip.encode()).hexdigest() if ip else '',
    )
    return otp, code


def verify_code(*, organization, phone, code):
    """
    Verify an OTP and return the resolved CRMCustomer.

    Consumes the OTP on success. On failure, increments the attempt counter and
    burns the code once the attempt ceiling is hit, so a 6-digit code cannot be
    brute-forced within its short life.
    """
    from apps.crm.models import CustomerSource
    from apps.crm.services.customer_service import get_or_create_customer

    normalized = normalize_phone(phone)
    if not normalized:
        raise OTPError('invalid_code')

    otp = (
        CoffeePassOTP.objects
        .filter(organization=organization, phone=normalized, consumed_at__isnull=True)
        .order_by('-created_at')
        .first()
    )
    if otp is None or otp.expires_at <= timezone.now():
        raise OTPError('invalid_code')

    max_attempts = _cfg('OTP_MAX_ATTEMPTS', 5)
    if otp.attempt_count >= max_attempts:
        raise OTPError('invalid_code')

    if otp.code_hash != hash_code(str(code).strip()):
        otp.attempt_count += 1
        fields = ['attempt_count']
        if otp.attempt_count >= max_attempts:
            # Burn it — no further guesses against this code.
            otp.consumed_at = timezone.now()
            fields.append('consumed_at')
        otp.save(update_fields=fields)
        raise OTPError('invalid_code')

    otp.consumed_at = timezone.now()
    otp.save(update_fields=['consumed_at'])

    # Identity resolves through the EXISTING CRM service — never a second
    # customer table, and phone normalization stays in one place.
    customer, _ = get_or_create_customer(
        organization, phone=normalized,
        defaults={'source': CustomerSource.WALK_IN, 'name': 'Coffee Pass customer'},
    )
    return customer


# ──────────────────────────────────────────────────────────────────────
# Signed public session
# ──────────────────────────────────────────────────────────────────────
def issue_session(customer) -> str:
    """
    Mint a signed, expiring session token bound to one customer.

    Carries ids only — no phone, no name. Tampering invalidates the signature.
    """
    return signing.dumps(
        {'cid': str(customer.id), 'oid': str(customer.organization_id)},
        salt=SESSION_SALT,
    )


def resolve_session(token: str):
    """
    Validate a session token and return the CRMCustomer, or None.

    Returns None (never raises) for expired, tampered, or stale-customer tokens
    so callers uniformly answer 401 without branching on failure mode.
    """
    from apps.crm.models import CRMCustomer

    if not token:
        return None
    try:
        data = signing.loads(
            token, salt=SESSION_SALT, max_age=_cfg('SESSION_TTL_SECONDS', 3600),
        )
    except signing.BadSignature:
        return None

    customer = CRMCustomer.objects.filter(
        id=data.get('cid'), organization_id=data.get('oid'), is_active=True,
    ).select_related('organization').first()
    return customer
