"""CRM admin (Phase 1). Append-only models are add/change-locked."""
import json

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    CRMCustomer, CRMTag, CRMCustomerTag, CRMInteraction, CRMConsent, CRMSegment,
)


def _pretty_json(value):
    if not value:
        return '—'
    return format_html('<pre>{}</pre>', json.dumps(value, indent=2, ensure_ascii=False))


class CRMCustomerTagInline(admin.TabularInline):
    model = CRMCustomerTag
    extra = 0
    autocomplete_fields = ['tag']


@admin.register(CRMCustomer)
class CRMCustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'email', 'source', 'marketing_consent_status',
                    'visit_count', 'is_active', 'created_at']
    list_filter = ['source', 'marketing_consent_status', 'is_active', 'gender']
    search_fields = ['name', 'phone', 'email', 'whatsapp_number']
    readonly_fields = ['birthday_month', 'visit_count', 'last_interaction_at',
                       'marketing_consent_status', 'created_at', 'updated_at']
    inlines = [CRMCustomerTagInline]


@admin.register(CRMTag)
class CRMTagAdmin(admin.ModelAdmin):
    list_display = ['name', 'organization', 'color', 'is_system', 'created_at']
    list_filter = ['is_system']
    search_fields = ['name']


@admin.register(CRMInteraction)
class CRMInteractionAdmin(admin.ModelAdmin):
    list_display = ['interaction_type', 'customer', 'source_channel', 'created_at']
    list_filter = ['interaction_type', 'source_channel']
    search_fields = ['customer__name', 'summary']
    readonly_fields = ['created_at']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(CRMConsent)
class CRMConsentAdmin(admin.ModelAdmin):
    list_display = ['customer', 'consent_given', 'consent_source', 'created_at']
    list_filter = ['consent_given', 'consent_source']
    search_fields = ['customer__name']
    readonly_fields = ['created_at', 'channels_pretty']

    def channels_pretty(self, obj):
        return _pretty_json(obj.marketing_channels_allowed)
    channels_pretty.short_description = 'Channels allowed'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CRMSegment)
class CRMSegmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'organization', 'customer_count', 'is_dynamic',
                    'last_evaluated_at']
    search_fields = ['name']
    readonly_fields = ['customer_count', 'last_evaluated_at', 'rules_pretty',
                       'created_at', 'updated_at']

    def rules_pretty(self, obj):
        return _pretty_json(obj.filter_rules)
    rules_pretty.short_description = 'Filter rules'
