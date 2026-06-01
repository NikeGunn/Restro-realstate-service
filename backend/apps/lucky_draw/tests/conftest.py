"""Shared fixtures for Lucky Draw (Phase 2) tests."""
import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Organization, OrganizationMembership, User
from apps.lucky_draw.models import (
    LuckyDrawCampaign, LuckyDrawPrize, LuckyDrawQRCode, CampaignStatus,
)


@pytest.fixture
def org(db):
    return Organization.objects.create(
        name="LD Test Org", business_type=Organization.BusinessType.RESTAURANT,
    )


@pytest.fixture
def org_b(db):
    return Organization.objects.create(
        name="LD Other Org", business_type=Organization.BusinessType.RESTAURANT,
    )


@pytest.fixture
def owner(db, org):
    user = User.objects.create_user(email='ld_owner@t.test', username='ld_owner', password='pw')
    OrganizationMembership.objects.create(
        user=user, organization=org, role=OrganizationMembership.Role.OWNER)
    return user


@pytest.fixture
def owner_b(db, org_b):
    user = User.objects.create_user(email='ld_owner_b@t.test', username='ld_owner_b', password='pw')
    OrganizationMembership.objects.create(
        user=user, organization=org_b, role=OrganizationMembership.Role.OWNER)
    return user


@pytest.fixture
def manager(db, org):
    user = User.objects.create_user(email='ld_mgr@t.test', username='ld_mgr', password='pw')
    OrganizationMembership.objects.create(
        user=user, organization=org, role=OrganizationMembership.Role.MANAGER)
    return user


@pytest.fixture
def outsider(db):
    return User.objects.create_user(email='ld_rando@t.test', username='ld_rando', password='pw')


@pytest.fixture
def campaign(db, org):
    """A draft campaign with a standard weight distribution, then activated."""
    c = LuckyDrawCampaign.objects.create(
        organization=org,
        name="Spin & Win",
        status=CampaignStatus.DRAFT,
        start_date=timezone.localdate(),
        consent_text="I agree to receive marketing messages.",
        deliver_coupon_via_whatsapp=True,
        referral_enabled=True,
        coupon_validity_days=14,
    )
    LuckyDrawPrize.objects.create(campaign=c, label="1% off", discount_percent=1, weight=60)
    LuckyDrawPrize.objects.create(campaign=c, label="5% off", discount_percent=5, weight=25)
    LuckyDrawPrize.objects.create(campaign=c, label="10% off", discount_percent=10, weight=10)
    LuckyDrawPrize.objects.create(campaign=c, label="20% off", discount_percent=20, weight=4)
    LuckyDrawPrize.objects.create(campaign=c, label="50% off", discount_percent=50, weight=1)
    c.status = CampaignStatus.ACTIVE
    c.save(update_fields=['status'])
    return c


@pytest.fixture
def qr_code(db, campaign):
    return LuckyDrawQRCode.objects.create(
        campaign=campaign, label="Table tent", url_token="testtoken12345",
    )


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def owner_client(api_client, owner):
    api_client.force_authenticate(user=owner)
    return api_client


@pytest.fixture
def manager_client(api_client, manager):
    api_client.force_authenticate(user=manager)
    return api_client
