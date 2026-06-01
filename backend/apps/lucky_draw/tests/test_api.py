"""
Authenticated API tests (Phase 2) — campaign CRUD, actions, stats, redeem,
permissions, cross-org isolation.
"""
import pytest
from django.utils import timezone

from apps.lucky_draw.models import (
    LuckyDrawCampaign, LuckyDrawPrize, LuckyDrawEntry, CampaignStatus, EntryStatus,
)
from apps.lucky_draw.services import entry_service

pytestmark = pytest.mark.django_db

BASE = '/api/v1/lucky_draw'


# ── CRUD + permissions ────────────────────────────────────────────────
def test_owner_creates_campaign(owner_client, org):
    resp = owner_client.post(f'{BASE}/campaigns/', {
        'organization': str(org.id), 'name': 'New Draw',
        'start_date': str(timezone.localdate()),
        'consent_text': 'I agree.',
    }, format='json')
    assert resp.status_code == 201
    assert resp.data['status'] == 'draft'


def test_manager_cannot_create_campaign(manager_client, org):
    resp = manager_client.post(f'{BASE}/campaigns/', {
        'organization': str(org.id), 'name': 'Nope',
        'start_date': str(timezone.localdate()), 'consent_text': 'x',
    }, format='json')
    assert resp.status_code == 403


def test_manager_can_read_campaigns(manager_client, campaign):
    resp = manager_client.get(f'{BASE}/campaigns/')
    assert resp.status_code == 200
    names = [c['name'] for c in resp.data['results']]
    assert 'Spin & Win' in names


def test_outsider_denied(api_client, outsider, campaign):
    api_client.force_authenticate(user=outsider)
    resp = api_client.get(f'{BASE}/campaigns/')
    assert resp.status_code == 403


def test_cross_org_campaign_404(owner_client, org_b):
    other = LuckyDrawCampaign.objects.create(
        organization=org_b, name='Other', start_date=timezone.localdate(),
        consent_text='x',
    )
    resp = owner_client.get(f'{BASE}/campaigns/{other.id}/')
    assert resp.status_code == 404


# ── status transitions ────────────────────────────────────────────────
def test_activate_requires_prize(owner_client, org):
    c = LuckyDrawCampaign.objects.create(
        organization=org, name='Empty', start_date=timezone.localdate(), consent_text='x',
    )
    resp = owner_client.post(f'{BASE}/campaigns/{c.id}/activate/')
    assert resp.status_code == 400


def test_activate_pause_end(owner_client, campaign):
    # campaign fixture starts active; pause then end then activate.
    r = owner_client.post(f'{BASE}/campaigns/{campaign.id}/pause/')
    assert r.status_code == 200 and r.data['status'] == 'paused'
    r = owner_client.post(f'{BASE}/campaigns/{campaign.id}/end/')
    assert r.status_code == 200 and r.data['status'] == 'ended'
    r = owner_client.post(f'{BASE}/campaigns/{campaign.id}/activate/')
    assert r.status_code == 200 and r.data['status'] == 'active'


# ── prizes ─────────────────────────────────────────────────────────────
def test_add_prize_owner(owner_client, campaign):
    resp = owner_client.post(f'{BASE}/campaigns/{campaign.id}/prizes/', {
        'discount_percent': '15.00', 'weight': 3, 'label': '15% off',
    }, format='json')
    assert resp.status_code == 201
    assert campaign.prizes.filter(discount_percent=15).exists()


def test_manager_cannot_add_prize(manager_client, campaign):
    resp = manager_client.post(f'{BASE}/campaigns/{campaign.id}/prizes/', {
        'discount_percent': '15.00', 'weight': 3,
    }, format='json')
    assert resp.status_code == 403


# ── QR codes ───────────────────────────────────────────────────────────
def test_create_qr_code(owner_client, campaign):
    resp = owner_client.post(f'{BASE}/campaigns/{campaign.id}/qr-codes/', {
        'label': 'Front door',
    }, format='json')
    assert resp.status_code == 201
    assert resp.data['url_token']
    assert resp.data['entry_url'].endswith(f"/{resp.data['url_token']}/")


# ── entries + stats ────────────────────────────────────────────────────
def test_entries_action(owner_client, campaign):
    entry_service.create_entry(campaign, name='E1', phone='+85290000001', consent_given=False)
    resp = owner_client.get(f'{BASE}/campaigns/{campaign.id}/entries/')
    assert resp.status_code == 200
    assert resp.data['count'] == 1


def test_stats_includes_referral_funnel_and_delivery_rate(owner_client, campaign):
    referrer = entry_service.create_entry(campaign, name='R', phone='+85290000010', consent_given=True)
    entry_service.create_entry(
        campaign, name='Friend', phone='+85290000011', consent_given=True,
        referral_token=referrer.referral_token,
    )
    resp = owner_client.get(f'{BASE}/campaigns/{campaign.id}/stats/')
    assert resp.status_code == 200
    data = resp.data
    assert data['total_entries'] == 2
    assert 'whatsapp_delivery_rate' in data
    assert data['referral_funnel']['shared'] == 1
    assert data['referral_funnel']['referred_entries'] == 1
    assert isinstance(data['prize_distribution'], list)


# ── redeem ─────────────────────────────────────────────────────────────
def test_redeem_flow(owner_client, campaign):
    entry = entry_service.create_entry(campaign, name='Buyer', phone='+85290000020', consent_given=False)
    resp = owner_client.post(f'{BASE}/entries/redeem/', {
        'coupon_code': entry.coupon_code,
    }, format='json')
    assert resp.status_code == 200
    assert resp.data['status'] == EntryStatus.REDEEMED
    entry.refresh_from_db()
    assert entry.redeemed_at is not None
    assert entry.redeemed_by_id is not None
    # coupon_redeemed interaction logged.
    assert entry.crm_customer.interactions.filter(interaction_type='coupon_redeemed').exists()


def test_redeem_already_redeemed_conflict(owner_client, campaign):
    entry = entry_service.create_entry(campaign, name='Buyer', phone='+85290000021', consent_given=False)
    owner_client.post(f'{BASE}/entries/redeem/', {'coupon_code': entry.coupon_code}, format='json')
    resp = owner_client.post(f'{BASE}/entries/redeem/', {'coupon_code': entry.coupon_code}, format='json')
    assert resp.status_code == 409


def test_redeem_unknown_code_404(owner_client, campaign):
    resp = owner_client.post(f'{BASE}/entries/redeem/', {'coupon_code': 'NOPENOPE'}, format='json')
    assert resp.status_code == 404


def test_redeem_expired_gone(owner_client, campaign):
    entry = entry_service.create_entry(campaign, name='Late', phone='+85290000022', consent_given=False)
    entry.expires_at = timezone.now() - timezone.timedelta(days=1)
    entry.save(update_fields=['expires_at'])
    resp = owner_client.post(f'{BASE}/entries/redeem/', {'coupon_code': entry.coupon_code}, format='json')
    assert resp.status_code == 410


def test_cross_org_redeem_not_found(owner_client, org_b):
    """An owner cannot redeem a coupon belonging to another org's campaign."""
    other = LuckyDrawCampaign.objects.create(
        organization=org_b, name='Other', start_date=timezone.localdate(),
        consent_text='x', status=CampaignStatus.ACTIVE,
    )
    LuckyDrawPrize.objects.create(campaign=other, discount_percent=5, weight=1)
    entry = entry_service.create_entry(other, name='X', phone='+85290000099', consent_given=False)
    resp = owner_client.post(f'{BASE}/entries/redeem/', {'coupon_code': entry.coupon_code}, format='json')
    assert resp.status_code == 404


