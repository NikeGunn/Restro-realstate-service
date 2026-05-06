from django.contrib import admin
from .models import (
    InventoryCategory, Supplier, InventoryItem, StockMovement,
    StockAlert, InventoryAuditLog,
)


@admin.register(InventoryCategory)
class InventoryCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'is_active', 'created_at')
    list_filter = ('is_active', 'organization')
    search_fields = ('name',)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'payment_terms', 'is_active')
    list_filter = ('is_active', 'payment_terms', 'organization')
    search_fields = ('name', 'contact_name', 'email')


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ('sku', 'name', 'organization', 'unit', 'current_stock', 'reorder_level', 'is_active')
    list_filter = ('is_active', 'is_perishable', 'unit', 'organization')
    search_fields = ('sku', 'name', 'barcode')
    readonly_fields = ('sku', 'current_stock', 'created_at', 'updated_at')


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('item', 'movement_type', 'quantity', 'movement_date', 'is_reversed')
    list_filter = ('movement_type', 'is_reversed', 'movement_date')
    search_fields = ('item__name', 'item__sku', 'notes')
    readonly_fields = tuple(f.name for f in StockMovement._meta.fields)

    def has_change_permission(self, request, obj=None):
        return False  # ledger is immutable


@admin.register(StockAlert)
class StockAlertAdmin(admin.ModelAdmin):
    list_display = ('item', 'alert_type', 'is_resolved', 'triggered_at')
    list_filter = ('alert_type', 'is_resolved')


@admin.register(InventoryAuditLog)
class InventoryAuditLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'model_name', 'object_repr', 'performed_by', 'timestamp')
    list_filter = ('action', 'model_name')
    search_fields = ('object_repr',)
    readonly_fields = tuple(f.name for f in InventoryAuditLog._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
