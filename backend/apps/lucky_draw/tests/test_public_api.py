"""
Public API tests (Phase 2) — the scan→win pipeline end-to-end.

Covers: config GET (+ scan_count), full enter flow creates CRM customer +
consent + tag + interaction, idempotency replay, consent-not-pre-checked.
"""
import pytest
from rest_framework.test import APIClient

from apps.crm.models import CRMCustomer, CRMConsent, CRMCustomerTag, ConsentStatus
from apps.lucky_draw.models import LuckyDrawEntry, EntryStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def public_client():
    return APIClient()


def _config_url(token):
    return f'/public/lucky-draw/{token}/config/'


def _enter_url(token):
    return f'/public/lucky-draw/{token}/enter/'


def test_config_returns_campaign_and_bumps_scan_count(public_client, qr_code):
    resp = public_client.get(_config_url(qr_code.url_token))
    assert resp.status_code == 200
    assert resp.data['name'] == 'Spin & Win'
    assert resp.data['is_open'] is True
    assert resp.data['max_discount'] == 50.0
    qr_code.refresh_from_db()
    assert qr_code.scan_count == 1


def test_config_unknown_token_404(public_client):
    resp = public_client.get(_config_url('does-not-exist'))
    assert resp.status_code == 404


def test_enter_full_pipeline(public_client, qr_code, org):
    resp = public_client.post(_enter_url(qr_code.url_token), {
        'name': 'Wong Tai', 'phone': '91234567', 'consent_given': True,
        'idempotency_key': 'k1',
    }, format='json')
    assert resp.status_code == 201
    body = resp.data
    assert body['won'] is True
    assert body['coupon_code']
    assert body['discount_percent'] in (1, 5, 10, 20, 50)
    assert body['referral_url']  # referral enabled
    assert body['share_text']

    # Entry persisted as drawn with a coupon + expiry + referral token.
    entry = LuckyDrawEntry.objects.get(coupon_code=body['coupon_code'])
    assert entry.status == EntryStatus.DRAWN
    assert entry.expires_at is not None
    assert entry.referral_token

    # CRM customer created (phone normalized to E.164), source lucky_draw.
    cust = CRMCustomer.objects.get(organization=org, phone='+85291234567')
    assert cust.source == 'lucky_draw'
    assert entry.crm_customer_id == cust.id

    # Consent recorded (given=True) -> status GIVEN.
    assert CRMConsent.objects.filter(customer=cust, consent_given=True).exists()
    cust.refresh_from_db()
    assert cust.marketing_consent_status == ConsentStatus.GIVEN

    # lucky_draw_lead tag applied.
    assert CRMCustomerTag.objects.filter(
        customer=cust, tag__name='lucky_draw_lead'
    ).exists()

    # A lucky_draw_entry interaction logged.
    assert cust.interactions.filter(interaction_type='lucky_draw_entry').exists()


def test_consent_not_pre_checked(public_client, qr_code, org):
    """consent_given=False -> customer created, but NO consent row, status not_asked."""
    resp = public_client.post(_enter_url(qr_code.url_token), {
        'name': 'No Consent', 'phone': '92345678', 'consent_given': False,
        'idempotency_key': 'k2',
    }, format='json')
    assert resp.status_code == 201
    cust = CRMCustomer.objects.get(organization=org, phone='+85292345678')
    assert not CRMConsent.objects.filter(customer=cust).exists()
    assert cust.marketing_consent_status == ConsentStatus.NOT_ASKED


def test_idempotency_replay_returns_same_result_no_second_entry(public_client, qr_code):
    payload = {'name': 'Repeat', 'phone': '93456789', 'consent_given': True,
               'idempotency_key': 'same-key-123'}
    r1 = public_client.post(_enter_url(qr_code.url_token), payload, format='json')
    assert r1.status_code == 201
    r2 = public_client.post(_enter_url(qr_code.url_token), payload, format='json')
    assert r2.status_code == 200  # replay
    assert r1.data['coupon_code'] == r2.data['coupon_code']
    # Only ONE entry exists for that phone.
    assert LuckyDrawEntry.objects.filter(phone='+85293456789').count() == 1


def test_enter_missing_required_field_422(public_client, qr_code):
    # requires_phone=True by default; omit phone.
    resp = public_client.post(_enter_url(qr_code.url_token), {
        'name': 'No Phone', 'consent_given': True, 'idempotency_key': 'k3',
    }, format='json')
    assert resp.status_code == 422
    assert resp.data['detail'] == 'missing_required_fields'
    assert 'phone' in resp.data['fields']


def test_enter_paused_campaign_422(public_client, qr_code, campaign):
    from apps.lucky_draw.models import CampaignStatus
    campaign.status = CampaignStatus.PAUSED
    campaign.save(update_fields=['status'])
    resp = public_client.post(_enter_url(qr_code.url_token), {
        'name': 'X', 'phone': '94567890', 'consent_given': True, 'idempotency_key': 'k4',
    }, format='json')
    assert resp.status_code == 422
    assert resp.data['detail'] == 'campaign_not_active'


def test_prize_counters_increment(public_client, qr_code, campaign):
    public_client.post(_enter_url(qr_code.url_token), {
        'name': 'Counter', 'phone': '95678901', 'consent_given': False, 'idempotency_key': 'k5',
    }, format='json')
    total = sum(p.wins_total_count for p in campaign.prizes.all())
    today = sum(p.wins_today_count for p in campaign.prizes.all())
    assert total == 1
    assert today == 1
