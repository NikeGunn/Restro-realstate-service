"""
Django admin for Coffee Pass.

Deliberately read-mostly. Passes, purchases, redemptions, audit events and
outbox rows are all owned by services that maintain invariants (one-way latches,
snapshot immutability, atomic token consumption). Letting a staffer hand-edit a
pass in admin would route around every one of those guarantees, so those models
are registered for VISIBILITY, not mutation.

Plans are the exception: they are configuration, and editing one is safe by
design because sold passes read their own snapshot.
"""
import json

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    CoffeeExperience, CoffeePass, CoffeePassAuditEvent, CoffeePassOTP,
    CoffeePassOutboxEvent, CoffeePassPlan, CoffeePassPurchase,
    CoffeePassRedemption, CoffeePassVerificationToken,
)


def _pretty_json(value):
    """Render a JSON field readably; admin JSON blobs are unusable raw."""
    if not value:
        return '—'
    return format_html(
        '<pre style="white-space:pre-wrap;max-width:800px">{}</pre>',
        json.dumps(value, indent=2, ensure_ascii=False, default=str),
    )


class ReadOnlyAdmin(admin.ModelAdmin):
    """Visibility without mutation — service-owned models use this."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CoffeePassPlan)
class CoffeePassPlanAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'organization', 'location', 'price_hkd', 'discount_percent',
        'duration_days', 'status', 'created_at',
    ]
    list_filter = ['status', 'organization', 'allow_neutral_feedback']
    search_fields = ['name', 'organization__name', 'location__name']
    filter_horizontal = ['eligible_items']
    # public_token is generated, never typed; editing it would break live QR codes.
    readonly_fields = ['public_token', 'created_at', 'updated_at']


@admin.register(CoffeeExperience)
class CoffeeExperienceAdmin(ReadOnlyAdmin):
    list_display = ['customer', 'location', 'sentiment', 'routine_context',
                    'source', 'offer_shown_at', 'created_at']
    list_filter = ['sentiment', 'routine_context', 'source', 'organization']
    search_fields = ['customer__name', 'customer__phone']
    readonly_fields = ['comment']


@admin.register(CoffeePassPurchase)
class CoffeePassPurchaseAdmin(ReadOnlyAdmin):
    list_display = ['id', 'customer', 'plan', 'status', 'amount_hkd',
                    'activated', 'paid_at', 'created_at']
    list_filter = ['status', 'activated', 'organization']
    search_fields = ['customer__name', 'customer__phone', 'stripe_session_id',
                     'stripe_payment_intent_id']
    readonly_fields = ['snapshot_display']

    @admin.display(description='Plan snapshot')
    def snapshot_display(self, obj):
        return _pretty_json(obj.plan_snapshot)


@admin.register(CoffeePass)
class CoffeePassAdmin(ReadOnlyAdmin):
    list_display = ['id', 'customer', 'location', 'status', 'starts_at',
                    'expires_at', 'created_at']
    list_filter = ['status', 'organization', 'location']
    search_fields = ['customer__name', 'customer__phone']
    readonly_fields = ['snapshot_display']

    @admin.display(description='Plan snapshot (immutable terms)')
    def snapshot_display(self, obj):
        return _pretty_json(obj.plan_snapshot)


@admin.register(CoffeePassRedemption)
class CoffeePassRedemptionAdmin(ReadOnlyAdmin):
    list_display = ['id', 'customer', 'location', 'eligible_subtotal_hkd',
                    'discount_amount_hkd', 'status', 'redeemed_by', 'redeemed_at']
    list_filter = ['status', 'organization', 'location']
    search_fields = ['customer__name', 'pos_receipt_reference']
    date_hierarchy = 'redeemed_at'


@admin.register(CoffeePassVerificationToken)
class CoffeePassVerificationTokenAdmin(ReadOnlyAdmin):
    """Hashes only — the raw code never exists at rest, so there is nothing to show."""
    list_display = ['id', 'coffee_pass', 'expires_at', 'consumed_at', 'created_at']
    list_filter = ['expires_at']


@admin.register(CoffeePassOTP)
class CoffeePassOTPAdmin(ReadOnlyAdmin):
    list_display = ['masked_phone', 'organization', 'expires_at',
                    'consumed_at', 'attempt_count', 'created_at']
    list_filter = ['organization']

    @admin.display(description='Phone')
    def masked_phone(self, obj):
        """Mask in the changelist — an OTP list should not be a phone directory."""
        return f'••••{obj.phone[-4:]}' if obj.phone else '—'


@admin.register(CoffeePassAuditEvent)
class CoffeePassAuditEventAdmin(ReadOnlyAdmin):
    list_display = ['action', 'entity_type', 'entity_id', 'actor',
                    'organization', 'created_at']
    list_filter = ['action', 'organization']
    search_fields = ['entity_id', 'correlation_id']
    date_hierarchy = 'created_at'
    readonly_fields = ['metadata_display']

    @admin.display(description='Metadata')
    def metadata_display(self, obj):
        return _pretty_json(obj.metadata)


@admin.register(CoffeePassOutboxEvent)
class CoffeePassOutboxEventAdmin(ReadOnlyAdmin):
    list_display = ['event_type', 'status', 'attempt_count', 'available_at',
                    'processed_at', 'organization']
    list_filter = ['status', 'event_type', 'organization']
    search_fields = ['idempotency_key', 'aggregate_id']
    readonly_fields = ['payload_display']

    @admin.display(description='Payload')
    def payload_display(self, obj):
        return _pretty_json(obj.payload)
