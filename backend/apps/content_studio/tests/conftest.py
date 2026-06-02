"""Shared fixtures for Content Studio (Phase 5) tests."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Organization, OrganizationMembership, User
from apps.content_studio.models import (
    ContentUseCase, ContentPromptTemplate, BrandKit,
)


@pytest.fixture(autouse=True)
def _isolated_media(settings, tmp_path):
    """Write generated images to a per-test temp dir so runs don't accumulate
    files (and never touch the real media-pvc path).

    FileSystemStorage caches `location`/`base_location` on first use, and the
    global `default_storage` is a lazy proxy — so we reset the cached attrs on
    BOTH the proxy and its wrapped storage so the new MEDIA_ROOT takes effect."""
    settings.MEDIA_ROOT = str(tmp_path)
    from django.core.files.storage import default_storage
    targets = [default_storage]
    wrapped = getattr(default_storage, '_wrapped', None)
    if wrapped is not None:
        targets.append(wrapped)
    for storage in targets:
        d = getattr(storage, '__dict__', {})
        for attr in ('location', 'base_location'):
            d.pop(attr, None)


@pytest.fixture
def org(db):
    # Power plan — Content Studio is power-gated.
    return Organization.objects.create(
        name='Studio Org', business_type=Organization.BusinessType.RESTAURANT,
        plan=Organization.Plan.POWER,
    )


@pytest.fixture
def basic_org(db):
    return Organization.objects.create(
        name='Basic Org', business_type=Organization.BusinessType.RESTAURANT,
        plan=Organization.Plan.BASIC,
    )


@pytest.fixture
def org_b(db):
    return Organization.objects.create(
        name='Other Studio Org', business_type=Organization.BusinessType.RESTAURANT,
        plan=Organization.Plan.POWER,
    )


def _member(email, org, role):
    user = User.objects.create_user(email=email, username=email.split('@')[0], password='pw')
    OrganizationMembership.objects.create(user=user, organization=org, role=role)
    return user


@pytest.fixture
def owner(db, org):
    return _member('studio_owner@t.test', org, OrganizationMembership.Role.OWNER)


@pytest.fixture
def manager(db, org):
    return _member('studio_mgr@t.test', org, OrganizationMembership.Role.MANAGER)


@pytest.fixture
def owner_b(db, org_b):
    return _member('studio_owner_b@t.test', org_b, OrganizationMembership.Role.OWNER)


@pytest.fixture
def basic_owner(db, basic_org):
    return _member('studio_basic@t.test', basic_org, OrganizationMembership.Role.OWNER)


@pytest.fixture
def outsider(db):
    return User.objects.create_user(email='studio_rando@t.test', username='studio_rando', password='pw')


@pytest.fixture
def use_case(db):
    """A test-only use case + template (distinct key so it never collides with the
    12 rows seeded by the data migration in the test DB)."""
    uc = ContentUseCase.objects.create(
        use_case_key='test_offer_poster',
        display_name='Test Offer Poster',
        icon='badge-percent',
        required_fields=[{'key': 'offer_title', 'label': 'Offer Title', 'type': 'text'},
                         {'key': 'discount_value', 'label': 'Discount', 'type': 'text'}],
        optional_fields=[{'key': 'hero_dish', 'label': 'Hero Dish', 'type': 'text'}],
        supported_formats=['square', 'portrait'],
        credit_cost=1, active=True, sort_order=900,
    )
    ContentPromptTemplate.objects.create(
        use_case=uc,
        prompt_template='SHOT & SUBJECT: poster for "{{offer_title}}" at {{discount_value}}; '
                        'hero {{hero_dish}}.',
        negative_prompt='garbled text',
        system_instructions='Role: art director.',
    )
    return uc


@pytest.fixture
def testimonial_use_case(db):
    """Test-only testimonial use case keyed to require the consent gate.

    The view's consent gate keys on use_case_key == 'review_testimonial_graphic',
    so this fixture uses that exact key — but the data migration already seeded it,
    so we fetch-or-update rather than create to avoid a unique collision."""
    uc, _ = ContentUseCase.objects.update_or_create(
        use_case_key='review_testimonial_graphic',
        defaults={
            'display_name': 'Review Testimonial',
            'icon': 'quote',
            'required_fields': [
                {'key': 'review_text', 'label': 'Review', 'type': 'textarea'},
                {'key': 'reviewer_name', 'label': 'Reviewer', 'type': 'text'},
                {'key': 'permission_confirmed', 'label': 'Permission', 'type': 'checkbox'}],
            'supported_formats': ['square'],
            'credit_cost': 1, 'active': True, 'sort_order': 901,
        },
    )
    ContentPromptTemplate.objects.update_or_create(
        use_case=uc,
        defaults={'prompt_template': 'Quote "{{review_text}}" — {{reviewer_name}}.'},
    )
    return uc


@pytest.fixture
def brand_kit(db, org):
    return BrandKit.objects.create(
        organization=org, restaurant_name='Bargachi',
        brand_colors=['#E11D48', '#1E293B'], preferred_language='zh-TW',
        default_cta='Book now',
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


@pytest.fixture
def basic_client(api_client, basic_owner):
    api_client.force_authenticate(user=basic_owner)
    return api_client
