"""
Consent service (Phase 1) — HK PDPO-aware.

Consent is append-only & immutable: each record is a new row, withdrawal is a
new row with consent_given=False. The customer's marketing_consent_status is
always recomputed from the latest row. has_marketing_consent() is THE single
gate every outbound WhatsApp/marketing push must call.
"""
from django.db import transaction
from django.utils import timezone

from ..models import CRMConsent, CRMCustomer, ConsentStatus


@transaction.atomic
def record_consent(customer, given, source, text_snapshot='', text_version='v1',
                   channels=None, ip_hash=None, privacy_notice_version=''):
    """
    Append a consent record and recompute the customer's status.

    Per spec, the consent checkbox is NEVER pre-checked: callers that receive a
    missing/false consent simply should not call this with given=True. This
    function records exactly what it's told.
    """
    record = CRMConsent.objects.create(
        organization=customer.organization,
        customer=customer,
        consent_given=bool(given),
        consent_source=source,
        consent_text_snapshot=text_snapshot or '',
        consent_text_version=text_version or 'v1',
        marketing_channels_allowed=list(channels or []),
        opt_out_timestamp=timezone.now() if not given else None,
        privacy_notice_version=privacy_notice_version or '',
        ip_address_hashed=ip_hash or '',
    )
    _recompute_status(customer)
    return record


def _recompute_status(customer):
    """Set marketing_consent_status from the latest consent row."""
    latest = (
        CRMConsent.objects.filter(customer=customer).order_by('-created_at').first()
    )
    if latest is None:
        status = ConsentStatus.NOT_ASKED
    elif latest.consent_given:
        status = ConsentStatus.GIVEN
    else:
        # Distinguish a withdrawal (had given before) from an initial refusal.
        had_given = CRMConsent.objects.filter(
            customer=customer, consent_given=True
        ).exists()
        status = ConsentStatus.WITHDRAWN if had_given else ConsentStatus.REFUSED

    CRMCustomer.objects.filter(pk=customer.pk).update(
        marketing_consent_status=status
    )
    customer.marketing_consent_status = status


def has_marketing_consent(customer, channel=None):
    """
    THE gate. Returns True only if the latest consent row is given=True and (if
    a channel is specified) that channel is in marketing_channels_allowed.
    """
    latest = (
        CRMConsent.objects.filter(customer=customer).order_by('-created_at').first()
    )
    if latest is None or not latest.consent_given:
        return False
    if channel is None:
        return True
    allowed = latest.marketing_channels_allowed or []
    return channel in allowed
