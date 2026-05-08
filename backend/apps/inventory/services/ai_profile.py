"""
Per-organization AI inventory profile.

Builds a small JSON snapshot of an org's inventory shape so the
InventoryAIEngine prompt is informative without recomputing everything
on every query. The profile is regenerated daily by Celery and on-demand
when stale (older than INVENTORY_SETTINGS['AI_PROFILE_TTL_HOURS']).
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Count
from django.utils import timezone


def build_profile(organization) -> dict:
    """Compute a fresh profile dict for one organization."""
    from apps.inventory.models import (
        InventoryItem, StockAlert, StockMovement, Supplier, Recipe,
    )

    items = list(
        InventoryItem.objects.filter(organization=organization, is_active=True)
        .select_related('category', 'supplier')
    )
    if not items:
        return {
            'item_count': 0,
            'top_items': [],
            'top_suppliers': [],
            'recipe_count': 0,
            'open_alerts': 0,
            'recent_negative_count': 0,
        }

    # Top 10 items by inventory value (current_stock × unit_cost).
    by_value = sorted(
        items,
        key=lambda it: (it.current_stock or Decimal('0')) * (it.unit_cost or Decimal('0')),
        reverse=True,
    )[:10]
    top_items = [
        {
            'sku': it.sku,
            'name': it.name,
            'unit': it.unit,
            'current_stock': str(it.current_stock or Decimal('0')),
            'reorder_level': str(it.reorder_level or Decimal('0')),
            'category': it.category.name if it.category_id else None,
        }
        for it in by_value
    ]

    # Top 5 suppliers by attached active item count.
    suppliers = (
        Supplier.objects.filter(organization=organization, is_active=True)
        .annotate(item_count=Count('items', distinct=True))
        .order_by('-item_count')[:5]
    )
    top_suppliers = [
        {'name': s.name, 'payment_terms': s.payment_terms}
        for s in suppliers
    ]

    week_ago = timezone.now() - timedelta(days=7)
    recent_negative_count = StockMovement.objects.filter(
        organization=organization, quantity__lt=0,
        created_at__gte=week_ago, is_reversed=False,
    ).count()

    open_alerts = StockAlert.objects.filter(
        organization=organization, is_resolved=False,
    ).count()

    return {
        'item_count': len(items),
        'top_items': top_items,
        'top_suppliers': top_suppliers,
        'recipe_count': Recipe.objects.filter(
            organization=organization, is_active=True,
        ).count(),
        'open_alerts': open_alerts,
        'recent_negative_count': recent_negative_count,
    }


def get_or_build_profile(organization) -> dict:
    """
    Return the cached profile for an org if fresh; otherwise rebuild it,
    persist to InventoryAIProfile, and return.
    """
    from apps.inventory.models import InventoryAIProfile

    ttl_hours = (
        getattr(settings, 'INVENTORY_SETTINGS', {}).get('AI_PROFILE_TTL_HOURS', 36)
    )
    cutoff = timezone.now() - timedelta(hours=ttl_hours)

    row = (
        InventoryAIProfile.objects.filter(organization=organization).first()
    )
    if row and row.generated_at and row.generated_at >= cutoff and row.profile:
        return row.profile

    profile = build_profile(organization)
    if row:
        row.profile = profile
        row.generated_at = timezone.now()
        row.save(update_fields=['profile', 'generated_at', 'updated_at'])
    else:
        InventoryAIProfile.objects.create(
            organization=organization,
            profile=profile,
            generated_at=timezone.now(),
        )
    return profile


def render_profile_block(profile: dict) -> str:
    """Render the cached profile as a short text block for prompt injection."""
    if not profile or profile.get('item_count', 0) == 0:
        return ''
    lines = ['=== INVENTORY PROFILE (cached) ===']
    lines.append(
        f"Items: {profile.get('item_count', 0)} active · "
        f"Recipes: {profile.get('recipe_count', 0)} · "
        f"Open alerts: {profile.get('open_alerts', 0)} · "
        f"Negative movements (7d): {profile.get('recent_negative_count', 0)}"
    )
    top = profile.get('top_items') or []
    if top:
        lines.append('Top items by value:')
        for it in top[:5]:
            lines.append(
                f"  - {it['sku']} {it['name']} | {it['current_stock']} {it['unit']} "
                f"(reorder {it['reorder_level']})"
            )
    sups = profile.get('top_suppliers') or []
    if sups:
        lines.append('Key suppliers: ' + ', '.join(s['name'] for s in sups))
    return '\n'.join(lines)
