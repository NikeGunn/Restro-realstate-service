"""Billing serializers."""
from rest_framework import serializers

from .models import (
    SubscriptionPlan, AccountSubscription, UsageCreditBalance,
    UsageEvent, UsageLimit, MonthlyUsageSummary,
)


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = [
            'id', 'name', 'slug', 'price_hkd', 'monthly_image_credits',
            'plan_code', 'enabled_modules', 'created_at',
        ]


class AccountSubscriptionSerializer(serializers.ModelSerializer):
    plan_detail = SubscriptionPlanSerializer(source='plan', read_only=True)

    class Meta:
        model = AccountSubscription
        fields = [
            'id', 'organization', 'plan', 'plan_detail', 'status',
            'current_period_start', 'current_period_end',
            'monthly_ai_spend_cap_hkd', 'created_at', 'updated_at',
        ]


class UsageCreditBalanceSerializer(serializers.ModelSerializer):
    total_available = serializers.IntegerField(read_only=True)

    class Meta:
        model = UsageCreditBalance
        fields = [
            'id', 'organization', 'free_credits_remaining', 'paid_credits_remaining',
            'free_credits_used_this_month', 'paid_credits_used_this_month',
            'reserved_credits', 'total_available', 'current_estimated_spend_hkd',
            'cap_status', 'period_start', 'updated_at',
        ]


class UsageEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = UsageEvent
        fields = [
            'id', 'organization', 'user', 'module', 'event_type', 'provider',
            'model', 'credits_used', 'is_free_credit', 'cost_usd', 'cost_hkd',
            'billable_amount_hkd', 'status', 'reference_id', 'created_at', 'metadata',
        ]


class UsageLimitSerializer(serializers.ModelSerializer):
    class Meta:
        model = UsageLimit
        fields = [
            'id', 'organization', 'monthly_ai_spend_cap_hkd',
            'monthly_image_credits_extra_allowed', 'alert_at_percent', 'updated_at',
        ]
        read_only_fields = ['id', 'organization', 'updated_at']


class MonthlyUsageSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = MonthlyUsageSummary
        fields = [
            'id', 'organization', 'year', 'month', 'free_credits_used',
            'paid_credits_used', 'total_cost_usd', 'total_cost_hkd',
            'total_billable_hkd', 'image_generations', 'ai_queries', 'created_at',
        ]
