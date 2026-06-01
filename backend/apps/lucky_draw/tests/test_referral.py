"""Referral loop tests (Phase 2) — valid token grants bonus; self/same-phone rejected; idempotent."""
import pytest

from apps.lucky_draw.models import LuckyDrawEntry
from apps.lucky_draw.services import entry_service, referral_service

pytestmark = pytest.mark.django_db


def test_valid_referral_links_and_bumps_count(campaign):
    referrer = entry_service.create_entry(
        campaign, name='Referrer', phone='+85291110001', consent_given=False,
    )
    token = referrer.referral_token

    referee = entry_service.create_entry(
        campaign, name='Referee', phone='+85291110002', consent_given=False,
        referral_token=token,
    )
    referee.refresh_from_db()
    referrer.refresh_from_db()

    assert referee.referred_by_entry_id == referrer.id
    assert referrer.referral_count == 1


def test_self_referral_rejected(campaign):
    entry = entry_service.create_entry(
        campaign, name='Solo', phone='+85291110003', consent_given=False,
    )
    # Present the entry's own token on itself.
    result = referral_service.apply_referral(entry, entry.referral_token)
    assert result is None
    entry.refresh_from_db()
    assert entry.referral_count == 0


def test_same_phone_referral_rejected(campaign):
    referrer = entry_service.create_entry(
        campaign, name='R', phone='+85291110004', consent_given=False,
    )
    # Build a second entry with the SAME phone, then attempt to attribute it.
    same = LuckyDrawEntry(
        campaign=campaign, customer_name='Same', phone='+85291110004',
    )
    same.referral_token = entry_service._unique_referral_token()
    same.save()
    result = referral_service.apply_referral(same, referrer.referral_token)
    assert result is None


def test_referral_idempotent_per_referee_phone(campaign):
    referrer = entry_service.create_entry(
        campaign, name='R', phone='+85291110005', consent_given=False,
    )
    token = referrer.referral_token
    # First referee from this phone counts.
    entry_service.create_entry(
        campaign, name='Friend', phone='+85291110006', consent_given=False,
        referral_token=token,
    )
    referrer.refresh_from_db()
    assert referrer.referral_count == 1

    # A SECOND entry from the same referee phone must not double-count.
    second = LuckyDrawEntry(campaign=campaign, customer_name='Friend2', phone='+85291110006')
    second.referral_token = entry_service._unique_referral_token()
    second.save()
    referral_service.apply_referral(second, token)
    referrer.refresh_from_db()
    assert referrer.referral_count == 1


def test_unknown_token_is_noop(campaign):
    entry = entry_service.create_entry(
        campaign, name='X', phone='+85291110007', consent_given=False,
    )
    assert referral_service.apply_referral(entry, 'totally-unknown') is None
