"""
Credit adapter — the boundary between Content Studio (Phase 5) and Billing (Phase 6).

The generation saga (reserve → confirm-or-refund) is defined in REQUIREMENTS § 0 #9.
Phase 6 owns the real `billing.credit_service` with `select_for_update` row locks.
Until Phase 6 lands, this adapter degrades gracefully: it ALLOWS generation and
records no charge (free), so Content Studio is fully usable in isolation. When the
billing app appears in INSTALLED_APPS, this transparently delegates to it — no
change needed in `generation_service`.

Contract returned by `reserve(...)`:
    Reservation(event_id: str|None, allowed: bool, reason: str)

`event_id` is the billing.UsageEvent id when billing is active, else None.
"""
import logging
from dataclasses import dataclass
from decimal import Decimal

from django.apps import apps as django_apps

logger = logging.getLogger(__name__)


class InsufficientCreditsError(Exception):
    """Raised when the spend cap / credit balance blocks a reservation."""


@dataclass
class Reservation:
    event_id: str | None
    allowed: bool
    reason: str = ''


def _billing_service():
    """Return billing.credit_service if the billing app is installed, else None."""
    if not django_apps.is_installed('apps.billing'):
        return None
    try:
        from apps.billing.services import credit_service  # type: ignore
        return credit_service
    except Exception:  # pragma: no cover - defensive
        logger.exception('billing app installed but credit_service import failed')
        return None


def reserve(*, organization, credits, cost_usd_estimate, reference_id,
            idempotency_key, user=None, event_type='content_studio_image',
            provider='', model='') -> Reservation:
    """Reserve credits for a job. Idempotent on idempotency_key (Celery-retry safe)."""
    svc = _billing_service()
    if svc is None:
        # No billing yet → allow, no charge. Reservation carries no event id.
        return Reservation(event_id=None, allowed=True, reason='billing_not_installed')
    try:
        event = svc.reserve_credits(
            organization, credits,
            event_type=event_type, provider=provider, model=model,
            cost_usd_estimate=Decimal(cost_usd_estimate),
            reference_id=reference_id, idempotency_key=idempotency_key, user=user,
        )
        return Reservation(event_id=str(event.id), allowed=True)
    except Exception as e:  # billing raises InsufficientCreditsError on cap/credit block
        return Reservation(event_id=None, allowed=False, reason=str(e))


def confirm(*, event_id, credits_actual, cost_usd_actual) -> None:
    """Move reserved credits → used on provider success. No-op without billing."""
    svc = _billing_service()
    if svc is None or not event_id:
        return
    try:
        event = svc.get_event(event_id)
        svc.confirm_credits(
            event, credits_actual=credits_actual,
            cost_usd_actual=Decimal(cost_usd_actual),
        )
    except Exception:
        logger.exception('credit confirm failed for event %s', event_id)


def refund(*, event_id) -> None:
    """Release the reservation on provider failure/cancel. No-op without billing.

    Technical failures must NEVER charge — this restores the reservation.
    """
    svc = _billing_service()
    if svc is None or not event_id:
        return
    try:
        event = svc.get_event(event_id)
        svc.refund_credits(event)
    except Exception:
        logger.exception('credit refund failed for event %s', event_id)
