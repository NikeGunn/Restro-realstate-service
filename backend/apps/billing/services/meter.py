"""
Lightweight usage metering for non-credit AI calls (e.g. inventory AI queries).

Unlike Content Studio image generation (which goes through the reserve→confirm
saga because it consumes paid credits), inventory AI queries are metered as a
flat, free `success` UsageEvent for reporting only — no balance mutation, no cap
enforcement. Callers must treat this as best-effort: it never raises.
"""
import logging
from decimal import Decimal

from django.apps import apps as django_apps

logger = logging.getLogger(__name__)


def record_usage(*, organization, module, event_type, user=None,
                 provider='', model='', cost_usd=Decimal('0'), metadata=None):
    """Append a free `success` UsageEvent. Best-effort; swallows all errors.

    Safe to call from any app — it checks billing is installed and never imports
    billing models at the caller's module level.
    """
    if not django_apps.is_installed('apps.billing'):
        return None
    try:
        from ..models import UsageEvent, EventStatus
        from django.conf import settings
        rate = Decimal(str(settings.BILLING_SETTINGS.get('USD_TO_HKD', 7.8)))
        cost_hkd = (Decimal(cost_usd) * rate).quantize(Decimal('0.0001'))
        return UsageEvent.objects.create(
            organization=organization,
            user=user,
            module=module,
            event_type=event_type,
            provider=provider or '',
            model=model or '',
            credits_used=0,
            is_free_credit=True,
            cost_usd=Decimal(cost_usd),
            cost_hkd=cost_hkd,
            billable_amount_hkd=Decimal('0'),
            status=EventStatus.SUCCESS,
            metadata=metadata or {},
        )
    except Exception:
        logger.exception('record_usage failed (module=%s type=%s)', module, event_type)
        return None
