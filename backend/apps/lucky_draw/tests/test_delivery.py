"""
Delivery tests (Phase 2) — WhatsApp coupon send is consent-gated and failure-safe.
"""
from unittest import mock

import pytest

from apps.crm.services import consent_service
from apps.lucky_draw.services import entry_service, delivery_service

pytestmark = pytest.mark.django_db


def _entry_with_customer(campaign, phone='+85288880000', consent=True):
    entry = entry_service.create_entry(
        campaign, name='Recipient', phone=phone, consent_given=consent,
    )
    return entry


def test_no_send_without_consent(campaign):
    entry = _entry_with_customer(campaign, consent=False)
    with mock.patch(
        'apps.channels.whatsapp_service.WhatsAppService.get_for_organization'
    ) as get_svc:
        sent = delivery_service.deliver_coupon_whatsapp(entry)
    assert sent is False
    # Service should never even be resolved when consent is absent.
    get_svc.assert_not_called()
    entry.refresh_from_db()
    assert entry.whatsapp_sent_at is None


def test_send_with_consent_sets_timestamp_and_logs(campaign):
    entry = _entry_with_customer(campaign, consent=True)

    fake_service = mock.Mock()
    fake_service.send_message.return_value = 'wamid.123'
    with mock.patch(
        'apps.channels.whatsapp_service.WhatsAppService.get_for_organization',
        return_value=fake_service,
    ):
        sent = delivery_service.deliver_coupon_whatsapp(entry)

    assert sent is True
    fake_service.send_message.assert_called_once()
    entry.refresh_from_db()
    assert entry.whatsapp_sent_at is not None
    # whatsapp_coupon_sent interaction logged on the customer.
    assert entry.crm_customer.interactions.filter(
        interaction_type='whatsapp_coupon_sent'
    ).exists()


def test_send_idempotent_when_already_sent(campaign):
    entry = _entry_with_customer(campaign, consent=True)
    fake_service = mock.Mock()
    fake_service.send_message.return_value = 'wamid.1'
    with mock.patch(
        'apps.channels.whatsapp_service.WhatsAppService.get_for_organization',
        return_value=fake_service,
    ):
        assert delivery_service.deliver_coupon_whatsapp(entry) is True
        # Second call is a no-op (whatsapp_sent_at already set).
        assert delivery_service.deliver_coupon_whatsapp(entry) is False
    assert fake_service.send_message.call_count == 1


def test_send_failure_does_not_raise(campaign):
    entry = _entry_with_customer(campaign, consent=True)
    with mock.patch(
        'apps.channels.whatsapp_service.WhatsAppService.get_for_organization',
        side_effect=RuntimeError('boom'),
    ):
        # Must swallow the error and return False, never propagate.
        assert delivery_service.deliver_coupon_whatsapp(entry) is False


def test_no_send_when_campaign_opts_out(campaign):
    campaign.deliver_coupon_via_whatsapp = False
    campaign.save(update_fields=['deliver_coupon_via_whatsapp'])
    entry = _entry_with_customer(campaign, consent=True)
    with mock.patch(
        'apps.channels.whatsapp_service.WhatsAppService.get_for_organization'
    ) as get_svc:
        assert delivery_service.deliver_coupon_whatsapp(entry) is False
    get_svc.assert_not_called()


def test_expiry_reminder_gated_by_consent(campaign):
    entry = _entry_with_customer(campaign, consent=False)
    # Withdraw any consent to be explicit, then assert no reminder is sent.
    assert consent_service.has_marketing_consent(entry.crm_customer, 'whatsapp') is False
    with mock.patch(
        'apps.channels.whatsapp_service.WhatsAppService.get_for_organization'
    ) as get_svc:
        assert delivery_service.send_expiry_reminder(entry) is False
    get_svc.assert_not_called()
