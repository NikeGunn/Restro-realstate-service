"""Billing admin. UsageEvent is append-only (no add/change/delete)."""
import json

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    SubscriptionPlan, AccountSubscription, UsageCreditBalance,
    UsageEvent, UsageLimit, MonthlyUsageSummary,
)


def _pretty_json(value):
    try:
        return format_html('<pre>{}</pre>', json.dumps(value, indent=2, ensure_ascii=False))
    except Exception:
        return str(value)


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'plan_code', 'price_hkd', 'monthly_image_credits']
    list_filter = ['plan_code']
    search_fields = ['name', 'slug']


@admin.register(AccountSubscription)
class AccountSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['organization', 'plan', 'status', 'current_period_start', 'current_period_end']
    list_filter = ['status']
    search_fields = ['organization__name']
    autocomplete_fields = ['organization', 'plan']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(UsageCreditBalance)
class UsageCreditBalanceAdmin(admin.ModelAdmin):
    list_display = [
        'organization', 'free_credits_remaining', 'paid_credits_remaining',
        'reserved_credits', 'current_estimated_spend_hkd', 'cap_status', 'period_start',
    ]
    list_filter = ['cap_status']
    search_fields = ['organization__name']
    readonly_fields = ['updated_at']


@admin.register(UsageEvent)
class UsageEventAdmin(admin.ModelAdmin):
    list_display = [
        'created_at', 'organization', 'module', 'event_type', 'status',
        'credits_used', 'is_free_credit', 'billable_amount_hkd',
    ]
    list_filter = ['module', 'status', 'is_free_credit']
    search_fields = ['organization__name', 'event_type', 'idempotency_key']
    readonly_fields = [f.name for f in UsageEvent._meta.fields] + ['metadata_pretty']
    exclude = ['metadata']

    def metadata_pretty(self, obj):
        return _pretty_json(obj.metadata)
    metadata_pretty.short_description = 'metadata'

    # Append-only: no add / change / delete in admin.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UsageLimit)
class UsageLimitAdmin(admin.ModelAdmin):
    list_display = ['organization', 'monthly_ai_spend_cap_hkd', 'alert_at_percent']
    search_fields = ['organization__name']
    readonly_fields = ['updated_at']


@admin.register(MonthlyUsageSummary)
class MonthlyUsageSummaryAdmin(admin.ModelAdmin):
    list_display = [
        'organization', 'year', 'month', 'free_credits_used', 'paid_credits_used',
        'total_billable_hkd', 'image_generations', 'ai_queries',
    ]
    list_filter = ['year', 'month']
    search_fields = ['organization__name']
    readonly_fields = [f.name for f in MonthlyUsageSummary._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
