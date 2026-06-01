"""Entry eligibility tests (Phase 2) — per-phone HARD limits, per-IP SOFT, time window."""
import pytest
from django.utils import timezone

from apps.lucky_draw.models import CampaignStatus
from apps.lucky_draw.services import draw_engine, entry_service

pytestmark = pytest.mark.django_db


def test_eligible_active_campaign(campaign):
    ok, reason = draw_engine.validate_entry_eligibility(campaign, '+85291234567', 'iphash')
    assert ok is True
    assert reason == 'ok'


def test_inactive_campaign_blocked(campaign):
    campaign.status = CampaignStatus.PAUSED
    campaign.save(update_fields=['status'])
    ok, reason = draw_engine.validate_entry_eligibility(campaign, '+85291234567', 'iphash')
    assert ok is False
    assert reason == 'campaign_not_active'


def test_campaign_not_started(campaign):
    campaign.start_date = timezone.localdate() + timezone.timedelta(days=3)
    campaign.save(update_fields=['start_date'])
    ok, reason = draw_engine.validate_entry_eligibility(campaign, '+85291234567', 'iphash')
    assert ok is False
    assert reason == 'campaign_not_started'


def test_campaign_ended(campaign):
    campaign.end_date = timezone.localdate() - timezone.timedelta(days=1)
    campaign.save(update_fields=['end_date'])
    ok, reason = draw_engine.validate_entry_eligibility(campaign, '+85291234567', 'iphash')
    assert ok is False
    assert reason == 'campaign_ended'


def test_daily_limit_per_phone_hard(campaign):
    """daily_entry_limit_per_customer=1 -> the second same-phone entry today is blocked."""
    phone = '+85291234567'
    entry_service.create_entry(campaign, name='A', phone=phone, consent_given=False)
    ok, reason = draw_engine.validate_entry_eligibility(campaign, phone, 'iphash')
    assert ok is False
    assert reason == 'daily_limit_reached'


def test_total_limit_per_phone_hard(campaign):
    campaign.daily_entry_limit_per_customer = 10
    campaign.total_entry_limit_per_customer = 1
    campaign.save(update_fields=['daily_entry_limit_per_customer', 'total_entry_limit_per_customer'])
    phone = '+85299990000'
    entry_service.create_entry(campaign, name='A', phone=phone, consent_given=False)
    ok, reason = draw_engine.validate_entry_eligibility(campaign, phone, 'iphash')
    assert ok is False
    assert reason == 'total_limit_reached'


def test_per_ip_is_soft_not_blocking(campaign):
    """
    Different phones from the SAME IP are both allowed — HK restaurants share NAT
    IPs, so per-IP is logged/soft, never a hard block while the phone limit is ok.
    """
    e1 = entry_service.create_entry(campaign, name='A', phone='+85291111111',
                                    consent_given=False, ip_address='1.2.3.4')
    e2 = entry_service.create_entry(campaign, name='B', phone='+85292222222',
                                    consent_given=False, ip_address='1.2.3.4')
    assert e1.status == 'drawn'
    assert e2.status == 'drawn'
    assert e1.ip_address_hashed == e2.ip_address_hashed  # same IP, both hashed equally
