"""
Inventory admin — Plane B operational data, owner-facing only.

V2 spec Part 5:
- sku, current_stock are readonly on InventoryItem (computed from ledger)
- StockMovement ledger is fully immutable
- StockAlert has an inline 'resolve selected' bulk action
- Import error_log renders as pretty-printed JSON (not raw dict repr)
- RecipeIngredient appears as a TabularInline on RecipeAdmin
- PurchaseOrderItem appears as a TabularInline on PurchaseOrderAdmin
"""
import json

from django.contrib import admin
from django.utils import timezone
from django.utils.safestring import mark_safe

from .models import (
    InventoryCategory, Supplier, InventoryItem, LocationStock,
    StockMovement, StockAlert, InventoryAuditLog,
    PurchaseOrder, PurchaseOrderItem, PurchaseOrderEmail,
    Recipe, RecipeIngredient, RecipeVersion,
    SalesImport, SupplierImport,
    StockTake, StockTakeLine,
    LocationItemPricing,
    RecipeBookingLink, InventoryAIProfile,
    ConsumptionLog,
)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────
def _pretty_json(value):
    """Render a dict/list as a <pre>-formatted JSON block, safe for admin."""
    if value in (None, '', [], {}):
        return '—'
    try:
        text = json.dumps(value, indent=2, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(value)
    return mark_safe(f'<pre style="white-space:pre-wrap;max-height:400px;overflow:auto">{text}</pre>')


# ──────────────────────────────────────────────────────────────────────
# Categories / Suppliers
# ──────────────────────────────────────────────────────────────────────
@admin.register(InventoryCategory)
class InventoryCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'is_active', 'created_at')
    list_filter = ('is_active', 'organization')
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'payment_terms', 'is_active')
    list_filter = ('is_active', 'payment_terms', 'organization')
    search_fields = ('name', 'contact_name', 'email', 'tax_id')
    readonly_fields = ('created_at', 'updated_at')


# ──────────────────────────────────────────────────────────────────────
# Items + per-location stock
# ──────────────────────────────────────────────────────────────────────
class LocationStockInline(admin.TabularInline):
    model = LocationStock
    extra = 0
    readonly_fields = ('current_stock', 'updated_at')
    fields = ('location', 'current_stock', 'reorder_level_override', 'updated_at')
    can_delete = False


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = (
        'sku', 'name', 'organization', 'unit',
        'current_stock', 'reorder_level', 'is_active',
    )
    list_filter = ('is_active', 'is_perishable', 'unit', 'organization')
    search_fields = ('sku', 'name', 'barcode')
    # sku + current_stock are computed from the ledger and immutable per V2 spec.
    readonly_fields = ('sku', 'current_stock', 'created_at', 'updated_at')
    inlines = [LocationStockInline]


@admin.register(LocationStock)
class LocationStockAdmin(admin.ModelAdmin):
    list_display = ('item', 'location', 'current_stock', 'updated_at')
    list_filter = ('location',)
    search_fields = ('item__name', 'item__sku')
    readonly_fields = ('current_stock', 'created_at', 'updated_at')


# ──────────────────────────────────────────────────────────────────────
# Ledger (append-only)
# ──────────────────────────────────────────────────────────────────────
@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = (
        'item', 'movement_type', 'quantity',
        'movement_date', 'is_reversed', 'created_at',
    )
    list_filter = ('movement_type', 'is_reversed', 'movement_date')
    search_fields = ('item__name', 'item__sku', 'notes', 'reference_number')
    date_hierarchy = 'movement_date'
    readonly_fields = tuple(f.name for f in StockMovement._meta.fields)

    def has_add_permission(self, request):
        return False  # ledger entries come from StockEngine only

    def has_change_permission(self, request, obj=None):
        return False  # ledger is immutable

    def has_delete_permission(self, request, obj=None):
        return False


# ──────────────────────────────────────────────────────────────────────
# Alerts (with bulk resolve)
# ──────────────────────────────────────────────────────────────────────
@admin.register(StockAlert)
class StockAlertAdmin(admin.ModelAdmin):
    list_display = (
        'item', 'alert_type', 'is_resolved',
        'whatsapp_sent', 'triggered_at',
    )
    list_filter = ('alert_type', 'is_resolved', 'whatsapp_sent')
    search_fields = ('item__name', 'item__sku', 'message')
    date_hierarchy = 'triggered_at'
    readonly_fields = (
        'organization', 'location', 'item', 'alert_type', 'message',
        'whatsapp_sent', 'whatsapp_sent_at', 'triggered_at',
        'created_at', 'updated_at',
    )
    actions = ('action_resolve_selected',)

    @admin.action(description='Mark selected alerts as resolved')
    def action_resolve_selected(self, request, queryset):
        n = queryset.filter(is_resolved=False).update(
            is_resolved=True, resolved_at=timezone.now(),
        )
        self.message_user(request, f'{n} alert(s) marked as resolved.')


# ──────────────────────────────────────────────────────────────────────
# Audit log (read-only)
# ──────────────────────────────────────────────────────────────────────
@admin.register(InventoryAuditLog)
class InventoryAuditLogAdmin(admin.ModelAdmin):
    list_display = (
        'action', 'model_name', 'object_repr',
        'performed_by', 'timestamp',
    )
    list_filter = ('action', 'model_name')
    search_fields = ('object_repr', 'object_id')
    date_hierarchy = 'timestamp'
    readonly_fields = tuple(f.name for f in InventoryAuditLog._meta.fields) + (
        'before_pretty', 'after_pretty', 'changes_pretty',
    )
    exclude = ('before', 'after', 'changes')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='Before')
    def before_pretty(self, obj):
        return _pretty_json(obj.before)

    @admin.display(description='After')
    def after_pretty(self, obj):
        return _pretty_json(obj.after)

    @admin.display(description='Changes')
    def changes_pretty(self, obj):
        return _pretty_json(obj.changes)


# ──────────────────────────────────────────────────────────────────────
# Purchase orders + items + email log
# ──────────────────────────────────────────────────────────────────────
class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 0
    fields = ('item', 'quantity_ordered', 'quantity_received', 'unit_cost')


class PurchaseOrderEmailInline(admin.TabularInline):
    model = PurchaseOrderEmail
    extra = 0
    fields = ('sent_at', 'to_email', 'subject', 'error')
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = (
        'order_number', 'supplier', 'status',
        'expected_date', 'total_amount', 'created_at',
    )
    list_filter = ('status', 'organization', 'supplier')
    search_fields = ('order_number', 'notes')
    date_hierarchy = 'created_at'
    readonly_fields = (
        'order_number', 'total_amount', 'sent_at', 'sent_to_email',
        'created_at', 'updated_at',
    )
    inlines = [PurchaseOrderItemInline, PurchaseOrderEmailInline]


# ──────────────────────────────────────────────────────────────────────
# Recipes
# ──────────────────────────────────────────────────────────────────────
class RecipeIngredientInline(admin.TabularInline):
    model = RecipeIngredient
    extra = 0
    fields = ('item', 'quantity', 'unit', 'is_optional')
    autocomplete_fields = ('item',)


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'formula_type', 'output_item', 'output_quantity',
        'serving_ml', 'yield_percent', 'version', 'is_active',
    )
    list_filter = ('is_active', 'organization', 'formula_type')
    search_fields = ('name',)
    readonly_fields = ('version', 'created_at', 'updated_at')
    autocomplete_fields = ('linked_promo_rule',)
    inlines = [RecipeIngredientInline]


@admin.register(RecipeVersion)
class RecipeVersionAdmin(admin.ModelAdmin):
    list_display = ('recipe', 'version_number', 'changed_at', 'changed_by')
    list_filter = ('recipe',)
    readonly_fields = (
        'recipe', 'version_number', 'snapshot_pretty',
        'changed_at', 'changed_by', 'reason',
    )
    exclude = ('snapshot',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description='Snapshot')
    def snapshot_pretty(self, obj):
        return _pretty_json(obj.snapshot)


# ──────────────────────────────────────────────────────────────────────
# Imports
# ──────────────────────────────────────────────────────────────────────
class _ImportAdminBase(admin.ModelAdmin):
    list_display = (
        'id', 'organization', 'status', 'row_count',
        'processed_count', 'error_count', 'created_at',
    )
    list_filter = ('status', 'organization')
    date_hierarchy = 'created_at'
    readonly_fields = (
        'created_by', 'organization',
        'row_count', 'processed_count', 'error_count',
        'imported_at', 'created_at', 'updated_at',
        'error_log_pretty', 'summary_pretty', 'column_map_pretty',
    )
    exclude = ('error_log', 'summary', 'column_map')

    @admin.display(description='Error log')
    def error_log_pretty(self, obj):
        return _pretty_json(obj.error_log)

    @admin.display(description='Summary')
    def summary_pretty(self, obj):
        return _pretty_json(obj.summary)

    @admin.display(description='Column map')
    def column_map_pretty(self, obj):
        return _pretty_json(obj.column_map)


@admin.register(SalesImport)
class SalesImportAdmin(_ImportAdminBase):
    pass


@admin.register(SupplierImport)
class SupplierImportAdmin(_ImportAdminBase):
    pass


# ──────────────────────────────────────────────────────────────────────
# Stock takes
# ──────────────────────────────────────────────────────────────────────
class StockTakeLineInline(admin.TabularInline):
    model = StockTakeLine
    extra = 0
    fields = ('item', 'system_count', 'counted', 'variance')
    readonly_fields = ('system_count', 'variance')


@admin.register(StockTake)
class StockTakeAdmin(admin.ModelAdmin):
    list_display = ('id', 'organization', 'location', 'status', 'created_at', 'committed_at')
    list_filter = ('status', 'organization')
    readonly_fields = ('committed_at', 'created_at', 'updated_at', 'created_by')
    inlines = [StockTakeLineInline]


# ──────────────────────────────────────────────────────────────────────
# Per-location pricing
# ──────────────────────────────────────────────────────────────────────
@admin.register(LocationItemPricing)
class LocationItemPricingAdmin(admin.ModelAdmin):
    list_display = ('item', 'location', 'unit_cost', 'selling_price', 'updated_at')
    list_filter = ('location',)
    search_fields = ('item__name', 'item__sku')
    readonly_fields = ('created_at', 'updated_at')


# ──────────────────────────────────────────────────────────────────────
# Phase 6 — Plane A bridge + AI profile
# ──────────────────────────────────────────────────────────────────────
@admin.register(RecipeBookingLink)
class RecipeBookingLinkAdmin(admin.ModelAdmin):
    list_display = ('booking', 'recipe', 'batches', 'consumed_at', 'created_at')
    list_filter = ('organization',)
    search_fields = ('recipe__name',)
    readonly_fields = ('consumed_at', 'created_at', 'updated_at')


@admin.register(InventoryAIProfile)
class InventoryAIProfileAdmin(admin.ModelAdmin):
    list_display = ('organization', 'generated_at', 'updated_at')
    readonly_fields = (
        'organization', 'generated_at', 'profile_pretty',
        'created_at', 'updated_at',
    )
    exclude = ('profile',)

    @admin.display(description='Profile')
    def profile_pretty(self, obj):
        return _pretty_json(obj.profile)


# ──────────────────────────────────────────────────────────────────────
# Consumption Log (Phase 4) — append-only audit, read-only in admin.
# ──────────────────────────────────────────────────────────────────────
@admin.register(ConsumptionLog)
class ConsumptionLogAdmin(admin.ModelAdmin):
    list_display = (
        'recipe', 'consumption_type', 'quantity_consumed', 'movement', 'created_at',
    )
    list_filter = ('consumption_type', 'organization')
    search_fields = ('recipe__name',)
    readonly_fields = (
        'organization', 'recipe', 'movement', 'consumption_type',
        'quantity_consumed', 'created_at', 'updated_at',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
