"""
Cap monitor — recompute the spend-cap status band and notify the owner on a
threshold *crossing*.

Bands (% of UsageLimit.monthly_ai_spend_cap_hkd):
    <50% → active · 50–79% → warning_50 · 80–99% → warning_80 · ≥100% → blocked

Free credits never trigger `blocked` — only billable (paid) spend counts toward
the cap, and `current_estimated_spend_hkd` is only incremented for paid usage
(see credit_service.confirm_credits).
"""
import logging
from decimal import Decimal

from django.conf import settings

from ..models import CapStatus, UsageLimit

logger = logging.getLogger(__name__)


def _band(spend: Decimal, cap: Decimal) -> str:
    if cap is None or cap <= 0:
        return CapStatus.ACTIVE
    pct = (spend / cap) * 100
    if pct >= 100:
        return CapStatus.BLOCKED
    if pct >= 80:
        return CapStatus.WARNING_80
    if pct >= 50:
        return CapStatus.WARNING_50
    return CapStatus.ACTIVE


def recompute_cap_status(balance, *, persist=True):
    """Recompute and (optionally) persist `balance.cap_status`. Returns the new
    status. Notifies the owner when the band *crosses up* into a warning/blocked.
    """
    limit = UsageLimit.objects.filter(organization=balance.organization_id).first()
    cap = limit.monthly_ai_spend_cap_hkd if limit else Decimal('200')
    old = balance.cap_status
    new = _band(balance.current_estimated_spend_hkd, cap)

    if new != old:
        balance.cap_status = new
        if persist:
            balance.save(update_fields=['cap_status', 'updated_at'])
        # Notify only on an *upward* crossing into a non-active band.
        if _rank(new) > _rank(old) and new != CapStatus.ACTIVE:
            _notify_owner(balance, new, cap)
    return new


_RANK = {
    CapStatus.ACTIVE: 0,
    CapStatus.WARNING_50: 1,
    CapStatus.WARNING_80: 2,
    CapStatus.BLOCKED: 3,
}


def _rank(status) -> int:
    return _RANK.get(status, 0)


def _notify_owner(balance, status, cap):
    """Reuse the inventory owner-WhatsApp path. Failure-safe — never raises."""
    if not settings.BILLING_SETTINGS.get('NOTIFY_OWNER_ON_CAP', True):
        return
    try:
        from apps.accounts.models import Organization
        org = Organization.objects.get(pk=balance.organization_id)
        from apps.inventory.tasks import _resolve_owner_phone
        phone, owner = _resolve_owner_phone(org)
        if not phone:
            return
        msg = _message(status, balance.current_estimated_spend_hkd, cap, org)
        from apps.channels.whatsapp_service import WhatsAppService
        service = WhatsAppService.get_for_organization(org)
        if service:
            service.send_message(phone, msg)
    except Exception:  # notification must never break the credit saga
        logger.exception('cap alert notify failed for org %s', balance.organization_id)


def _message(status, spend, cap, org) -> str:
    name = getattr(org, 'name', 'Your organization')
    if status == CapStatus.BLOCKED:
        return (f'⚠️ {name}: your monthly AI spend cap of HKD {cap} has been reached. '
                f'Paid AI generation is paused until you raise the limit. '
                f'Your free monthly credits keep working.')
    pct = '80%' if status == CapStatus.WARNING_80 else '50%'
    return (f'ℹ️ {name}: AI usage has reached {pct} of your HKD {cap} monthly cap '
            f'(HKD {spend} so far). You can raise the cap in Billing settings.')
