"""
Phase 6 — Plane A integration tests.

Two features:
  1. RecipeBookingLink + signal: completing a Booking auto-consumes its
     linked recipe(s) via StockEngine, but ONLY when the
     INVENTORY_SETTINGS['AUTO_CONSUME_ON_BOOKING_COMPLETE'] flag is on.
  2. InventoryAIProfile: per-org cached profile, refreshed by Celery task
     and on-demand when stale, injected into InventoryAIEngine prompts.
"""
from __future__ import annotations

from datetime import date, time, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.accounts.models import Location
from apps.restaurant.models import Booking
from apps.inventory.models import (
    InventoryItem, RecipeBookingLink, StockMovement, InventoryAIProfile,
)
from apps.inventory.services.stock_engine import StockEngine
from apps.inventory.services import ai_profile as ai_profile_service
from apps.inventory.tasks import refresh_inventory_ai_profiles_task


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────
@pytest.fixture
def location(db, org):
    return Location.objects.create(organization=org, name='Main', is_primary=True)


@pytest.fixture
def stocked_item(db, item):
    """Give the item enough stock that a recipe consumption can succeed."""
    StockMovement.objects.create(
        organization=item.organization, item=item,
        movement_type=StockMovement.MovementType.PURCHASE,
        quantity=Decimal('100'),
    )
    item.refresh_from_db()
    return item


@pytest.fixture
def stocked_item_b(db, item_b):
    StockMovement.objects.create(
        organization=item_b.organization, item=item_b,
        movement_type=StockMovement.MovementType.PURCHASE,
        quantity=Decimal('100'),
    )
    item_b.refresh_from_db()
    return item_b


@pytest.fixture
def booking(db, org, location):
    return Booking.objects.create(
        organization=org, location=location,
        booking_date=date.today() + timedelta(days=1),
        booking_time=time(19, 0),
        party_size=4,
        customer_name='Test Guest',
        customer_phone='+10000000000',
        status=Booking.Status.CONFIRMED,
    )


# ──────────────────────────────────────────────────────────────────────
# RecipeBookingLink + signal
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
def test_link_creation(org, booking, recipe):
    link = RecipeBookingLink.objects.create(
        organization=org, booking=booking, recipe=recipe, batches=Decimal('2'),
    )
    assert link.consumed_at is None
    # unique constraint on (booking, recipe)
    with pytest.raises(Exception):
        RecipeBookingLink.objects.create(
            organization=org, booking=booking, recipe=recipe, batches=Decimal('1'),
        )


@pytest.mark.django_db
@override_settings(
    INVENTORY_SETTINGS={
        'DEFAULT_TOLERANCE_PERCENT': Decimal('0.5'),
        'MAX_TOLERANCE_PERCENT': Decimal('5.0'),
        'EXCEL_MAX_FILE_SIZE_MB': 10,
        'EXCEL_PREVIEW_ROWS': 10,
        'IMPORT_ERROR_THRESHOLD_PERCENT': 30,
        'LOW_STOCK_ALERT_COOLDOWN_HOURS': 24,
        'AI_INVENTORY_ENABLED': True,
        'AI_INVENTORY_MODEL': 'gpt-4o-mini',
        'STOCK_ALERT_CHANNELS': ['whatsapp'],
        'AUTO_CONSUME_ON_BOOKING_COMPLETE': False,
        'AI_PROFILE_TTL_HOURS': 36,
    }
)
def test_signal_disabled_by_default(org, booking, recipe, stocked_item, stocked_item_b):
    """With the flag OFF, completing a booking must NOT consume anything."""
    RecipeBookingLink.objects.create(
        organization=org, booking=booking, recipe=recipe, batches=Decimal('1'),
    )
    movements_before = StockMovement.objects.filter(organization=org).count()

    booking.complete()

    assert StockMovement.objects.filter(organization=org).count() == movements_before
    link = RecipeBookingLink.objects.get(booking=booking)
    assert link.consumed_at is None


@pytest.mark.django_db
@override_settings(
    INVENTORY_SETTINGS={
        'DEFAULT_TOLERANCE_PERCENT': Decimal('0.5'),
        'MAX_TOLERANCE_PERCENT': Decimal('5.0'),
        'EXCEL_MAX_FILE_SIZE_MB': 10,
        'EXCEL_PREVIEW_ROWS': 10,
        'IMPORT_ERROR_THRESHOLD_PERCENT': 30,
        'LOW_STOCK_ALERT_COOLDOWN_HOURS': 24,
        'AI_INVENTORY_ENABLED': True,
        'AI_INVENTORY_MODEL': 'gpt-4o-mini',
        'STOCK_ALERT_CHANNELS': ['whatsapp'],
        'AUTO_CONSUME_ON_BOOKING_COMPLETE': True,
        'AI_PROFILE_TTL_HOURS': 36,
    }
)
def test_signal_consumes_when_flag_on(org, booking, recipe, stocked_item, stocked_item_b):
    """With the flag ON, completing a booking consumes linked recipes."""
    RecipeBookingLink.objects.create(
        organization=org, booking=booking, recipe=recipe, batches=Decimal('1'),
    )
    before_a = stocked_item.current_stock
    before_b = stocked_item_b.current_stock

    booking.complete()

    stocked_item.refresh_from_db()
    stocked_item_b.refresh_from_db()
    # Recipe consumes 2 of item, 0.1 of item_b per batch (× 1 batch).
    assert stocked_item.current_stock == before_a - Decimal('2')
    assert stocked_item_b.current_stock == before_b - Decimal('0.1')

    link = RecipeBookingLink.objects.get(booking=booking)
    assert link.consumed_at is not None


@pytest.mark.django_db
@override_settings(
    INVENTORY_SETTINGS={
        'DEFAULT_TOLERANCE_PERCENT': Decimal('0.5'),
        'MAX_TOLERANCE_PERCENT': Decimal('5.0'),
        'EXCEL_MAX_FILE_SIZE_MB': 10,
        'EXCEL_PREVIEW_ROWS': 10,
        'IMPORT_ERROR_THRESHOLD_PERCENT': 30,
        'LOW_STOCK_ALERT_COOLDOWN_HOURS': 24,
        'AI_INVENTORY_ENABLED': True,
        'AI_INVENTORY_MODEL': 'gpt-4o-mini',
        'STOCK_ALERT_CHANNELS': ['whatsapp'],
        'AUTO_CONSUME_ON_BOOKING_COMPLETE': True,
        'AI_PROFILE_TTL_HOURS': 36,
    }
)
def test_signal_does_not_double_consume(org, booking, recipe, stocked_item, stocked_item_b):
    """Re-saving an already-completed booking must not consume the link twice."""
    RecipeBookingLink.objects.create(
        organization=org, booking=booking, recipe=recipe, batches=Decimal('1'),
    )
    booking.complete()
    after_first = InventoryItem.objects.get(pk=stocked_item.pk).current_stock

    # Re-save the booking (still COMPLETED). The link is consumed; signal must skip.
    booking.save(update_fields=['updated_at'])

    after_second = InventoryItem.objects.get(pk=stocked_item.pk).current_stock
    assert after_first == after_second


@pytest.mark.django_db
@override_settings(
    INVENTORY_SETTINGS={
        'DEFAULT_TOLERANCE_PERCENT': Decimal('0.5'),
        'MAX_TOLERANCE_PERCENT': Decimal('5.0'),
        'EXCEL_MAX_FILE_SIZE_MB': 10,
        'EXCEL_PREVIEW_ROWS': 10,
        'IMPORT_ERROR_THRESHOLD_PERCENT': 30,
        'LOW_STOCK_ALERT_COOLDOWN_HOURS': 24,
        'AI_INVENTORY_ENABLED': True,
        'AI_INVENTORY_MODEL': 'gpt-4o-mini',
        'STOCK_ALERT_CHANNELS': ['whatsapp'],
        'AUTO_CONSUME_ON_BOOKING_COMPLETE': True,
        'AI_PROFILE_TTL_HOURS': 36,
    }
)
def test_signal_swallows_failures(org, booking, recipe):
    """
    If consumption fails (e.g., insufficient stock), the booking save must
    still succeed — inventory is downstream of bookings, not gating.
    """
    # No stock seeded → consume_recipe will raise. Signal must catch.
    RecipeBookingLink.objects.create(
        organization=org, booking=booking, recipe=recipe, batches=Decimal('1'),
    )
    # Should not raise.
    booking.complete()
    booking.refresh_from_db()
    assert booking.status == Booking.Status.COMPLETED


# ──────────────────────────────────────────────────────────────────────
# RecipeBookingLink API
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
def test_link_api_owner_can_create(auth_owner_client, org, booking, recipe):
    res = auth_owner_client.post(
        '/api/v1/inventory/recipe-booking-links/',
        {
            'organization': str(org.id),
            'booking': str(booking.id),
            'recipe': str(recipe.id),
            'batches': '2',
        },
        format='json',
    )
    assert res.status_code in (200, 201), res.content


@pytest.mark.django_db
def test_link_api_manager_cannot_create(auth_manager_client, org, booking, recipe):
    res = auth_manager_client.post(
        '/api/v1/inventory/recipe-booking-links/',
        {
            'organization': str(org.id),
            'booking': str(booking.id),
            'recipe': str(recipe.id),
            'batches': '1',
        },
        format='json',
    )
    assert res.status_code == 403


# ──────────────────────────────────────────────────────────────────────
# InventoryAIProfile (#9)
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
def test_build_profile_for_empty_org(org):
    profile = ai_profile_service.build_profile(org)
    assert profile['item_count'] == 0
    assert profile['top_items'] == []


@pytest.mark.django_db
def test_build_profile_with_items(org, item, item_b, recipe, supplier):
    profile = ai_profile_service.build_profile(org)
    assert profile['item_count'] >= 2
    assert profile['recipe_count'] >= 1
    skus = {it['sku'] for it in profile['top_items']}
    assert item.sku in skus
    sup_names = {s['name'] for s in profile['top_suppliers']}
    assert supplier.name in sup_names


@pytest.mark.django_db
def test_get_or_build_caches_within_ttl(org, item):
    p1 = ai_profile_service.get_or_build_profile(org)
    row = InventoryAIProfile.objects.get(organization=org)
    first_generated = row.generated_at
    # Second call within TTL must NOT regenerate.
    p2 = ai_profile_service.get_or_build_profile(org)
    row.refresh_from_db()
    assert row.generated_at == first_generated
    assert p1 == p2


@pytest.mark.django_db
def test_get_or_build_rebuilds_when_stale(org, item):
    ai_profile_service.get_or_build_profile(org)
    row = InventoryAIProfile.objects.get(organization=org)
    # Force staleness: backdate.
    row.generated_at = timezone.now() - timedelta(hours=72)
    row.save(update_fields=['generated_at'])

    ai_profile_service.get_or_build_profile(org)
    row.refresh_from_db()
    assert row.generated_at > timezone.now() - timedelta(minutes=1)


@pytest.mark.django_db
def test_render_profile_block_handles_empty():
    assert ai_profile_service.render_profile_block({}) == ''
    assert ai_profile_service.render_profile_block({'item_count': 0}) == ''


@pytest.mark.django_db
def test_render_profile_block_emits_summary(org, item, item_b, supplier):
    profile = ai_profile_service.build_profile(org)
    block = ai_profile_service.render_profile_block(profile)
    assert 'INVENTORY PROFILE' in block
    assert 'Items:' in block


@pytest.mark.django_db
def test_refresh_task_writes_profile_for_each_org(org, org_b, item):
    refresh_inventory_ai_profiles_task()
    # Both orgs get a row, even the empty one.
    assert InventoryAIProfile.objects.filter(organization=org).exists()
    assert InventoryAIProfile.objects.filter(organization=org_b).exists()


@pytest.mark.django_db
def test_ai_engine_injects_profile_into_prompt(org, item):
    """
    InventoryAIEngine.query() should silently consult ai_profile and
    prepend the rendered block to the prompt context. We verify by
    asserting the profile row gets written when query() is called.
    """
    from apps.inventory.services.ai_engine import InventoryAIEngine

    # Simulate "no API key" path so we don't hit OpenAI but still go past
    # the empty-inventory short-circuit. _call_openai handles that.
    engine = InventoryAIEngine()
    with patch.object(engine, '_call_openai', return_value={
        'answer': 'ok', 'confidence': 0.9, 'data_points_used': [],
    }):
        engine.query('how much salt?', org)

    assert InventoryAIProfile.objects.filter(organization=org).exists()
