"""Consent tests: never pre-checked, withdrawal = new row, status recompute, gate."""
import pytest

from apps.crm.models import CRMConsent, ConsentStatus, ConsentSource
from apps.crm.services import consent_service

pytestmark = pytest.mark.django_db


def test_record_given_sets_status(customer):
    consent_service.record_consent(customer, given=True, source=ConsentSource.LUCKY_DRAW_FORM,
                                   channels=['whatsapp'])
    customer.refresh_from_db()
    assert customer.marketing_consent_status == ConsentStatus.GIVEN


def test_refusal_first_time_is_refused(customer):
    consent_service.record_consent(customer, given=False, source=ConsentSource.BOOKING_FORM)
    customer.refresh_from_db()
    assert customer.marketing_consent_status == ConsentStatus.REFUSED


def test_withdrawal_after_given_is_withdrawn(customer):
    consent_service.record_consent(customer, given=True, source=ConsentSource.MANUAL,
                                   channels=['whatsapp'])
    consent_service.record_consent(customer, given=False, source=ConsentSource.MANUAL)
    customer.refresh_from_db()
    assert customer.marketing_consent_status == ConsentStatus.WITHDRAWN
    # Withdrawal is a NEW row, not an edit.
    assert CRMConsent.objects.filter(customer=customer).count() == 2


def test_withdrawal_sets_opt_out_timestamp(customer):
    rec = consent_service.record_consent(customer, given=False, source=ConsentSource.MANUAL)
    assert rec.opt_out_timestamp is not None


def test_has_marketing_consent_gate(customer):
    assert consent_service.has_marketing_consent(customer, 'whatsapp') is False
    consent_service.record_consent(customer, given=True, source=ConsentSource.MANUAL,
                                   channels=['whatsapp'])
    assert consent_service.has_marketing_consent(customer, 'whatsapp') is True
    # Channel not in allow-list -> False.
    assert consent_service.has_marketing_consent(customer, 'sms') is False


def test_gate_false_after_withdrawal(customer):
    consent_service.record_consent(customer, given=True, source=ConsentSource.MANUAL,
                                   channels=['whatsapp'])
    consent_service.record_consent(customer, given=False, source=ConsentSource.MANUAL)
    assert consent_service.has_marketing_consent(customer, 'whatsapp') is False
