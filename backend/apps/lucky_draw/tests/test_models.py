"""Model invariant tests (Phase 2) — append-only entry, unique coupon, prize range, signals."""
import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.lucky_draw.models import (
    LuckyDrawCampaign, LuckyDrawPrize, LuckyDrawEntry, EntryStatus, ENTRY_MUTABLE_FIELDS,
)
from apps.lucky_draw.services import entry_service

pytestmark = pytest.mark.django_db


def test_entry_status_transition_allowed(campaign):
    entry = entry_service.create_entry(campaign, name='A', phone='+85287000001', consent_given=False)
    entry.status = EntryStatus.REDEEMED
    entry.redeemed_at = timezone.now()
    # Whitelisted fields via update_fields -> allowed.
    entry.save(update_fields=['status', 'redeemed_at'])
    entry.refresh_from_db()
    assert entry.status == EntryStatus.REDEEMED


def test_entry_immutable_field_update_rejected(campaign):
    entry = entry_service.create_entry(campaign, name='A', phone='+85287000002', consent_given=False)
    entry.customer_name = 'Tampered'
    with pytest.raises(ValueError):
        entry.save(update_fields=['customer_name'])


def test_entry_save_without_update_fields_rejected(campaign):
    entry = entry_service.create_entry(campaign, name='A', phone='+85287000003', consent_given=False)
    entry.status = EntryStatus.EXPIRED
    with pytest.raises(ValueError):
        entry.save()  # no update_fields -> blocked


def test_mutable_whitelist_contents():
    assert 'status' in ENTRY_MUTABLE_FIELDS
    assert 'coupon_code' in ENTRY_MUTABLE_FIELDS
    assert 'customer_name' not in ENTRY_MUTABLE_FIELDS
    assert 'phone' not in ENTRY_MUTABLE_FIELDS
    assert 'consent_given' not in ENTRY_MUTABLE_FIELDS


def test_coupon_code_unique(campaign):
    e1 = entry_service.create_entry(campaign, name='A', phone='+85287000004', consent_given=False)
    e2 = LuckyDrawEntry(campaign=campaign, customer_name='B', phone='+85287000005',
                        coupon_code=e1.coupon_code)
    with pytest.raises(IntegrityError):
        e2.save()


def test_prize_discount_range_constraint(campaign):
    with pytest.raises(IntegrityError):
        LuckyDrawPrize.objects.create(campaign=campaign, discount_percent=0, weight=1)


def test_campaign_create_seeds_system_tags(org):
    """The signal ensures lucky_draw_lead + buffet_customer tags exist for the org."""
    from apps.crm.models import CRMTag
    LuckyDrawCampaign.objects.create(
        organization=org, name='Seeder', start_date=timezone.localdate(), consent_text='x',
    )
    assert CRMTag.objects.filter(organization=org, name='lucky_draw_lead').exists()
    assert CRMTag.objects.filter(organization=org, name='buffet_customer').exists()
