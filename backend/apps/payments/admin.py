"""Payments admin. Purchases are read-only audit records (no manual edits)."""
from django.contrib import admin

from .models import CreditPack, CreditPurchase


@admin.register(CreditPack)
class CreditPackAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'credits', 'price_hkd', 'currency', 'is_active', 'sort_order']
    list_filter = ['is_active', 'currency']
    search_fields = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(CreditPurchase)
class CreditPurchaseAdmin(admin.ModelAdmin):
    list_display = [
        'created_at', 'organization', 'pack', 'status', 'credits', 'amount_hkd',
        'credited', 'refunded_amount_hkd',
    ]
    list_filter = ['status', 'credited', 'currency']
    search_fields = [
        'organization__name', 'stripe_session_id', 'stripe_payment_intent_id',
    ]
    readonly_fields = [f.name for f in CreditPurchase._meta.fields]

    # Purchases are append/observe-only — created and mutated by the saga, never
    # hand-edited (a manual edit could desync the wallet).
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
