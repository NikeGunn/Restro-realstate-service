"""
Inventory serializers.
"""
from decimal import Decimal

from rest_framework import serializers

from .models import (
    InventoryCategory, Supplier, InventoryItem, StockMovement,
    StockAlert, InventoryAuditLog,
)


class InventoryCategorySerializer(serializers.ModelSerializer):
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = InventoryCategory
        fields = [
            'id', 'organization', 'location', 'name', 'description',
            'is_active', 'item_count', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'item_count']

    def get_item_count(self, obj):
        return obj.items.filter(is_active=True).count()


class SupplierSerializer(serializers.ModelSerializer):
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Supplier
        fields = [
            'id', 'organization', 'location', 'name', 'contact_name',
            'email', 'phone', 'address', 'tax_id', 'payment_terms',
            'notes', 'is_active', 'item_count', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'item_count']

    def get_item_count(self, obj):
        return obj.items.filter(is_active=True).count()


class InventoryItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    stock_status = serializers.SerializerMethodField()
    effective_stock = serializers.SerializerMethodField()

    class Meta:
        model = InventoryItem
        fields = [
            'id', 'organization', 'location', 'sku', 'name', 'description',
            'category', 'category_name',
            'unit', 'unit_cost', 'selling_price',
            'reorder_level', 'reorder_quantity',
            'current_stock', 'tolerance_percent',
            'is_active', 'is_perishable', 'expiry_days',
            'supplier', 'supplier_name', 'barcode',
            'stock_status', 'effective_stock',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'sku', 'current_stock',
            'created_at', 'updated_at',
            'category_name', 'supplier_name',
            'stock_status', 'effective_stock',
        ]

    def get_stock_status(self, obj):
        if obj.current_stock < 0:
            return 'negative'
        if obj.reorder_level > 0 and obj.current_stock <= obj.reorder_level:
            return 'critical'
        if obj.reorder_level > 0 and obj.current_stock <= obj.reorder_level * 2:
            return 'low'
        return 'ok'

    def get_effective_stock(self, obj):
        t = obj.tolerance_percent / Decimal('100')
        lower = obj.current_stock * (1 - t)
        upper = obj.current_stock * (1 + t)
        return {
            'raw': str(obj.current_stock),
            'reported': str(obj.current_stock.quantize(Decimal('0.01'))),
            'lower_bound': str(lower.quantize(Decimal('0.0001'))),
            'upper_bound': str(upper.quantize(Decimal('0.0001'))),
            'tolerance_percent': str(obj.tolerance_percent),
        }


class StockMovementSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_sku = serializers.CharField(source='item.sku', read_only=True)
    item_unit = serializers.CharField(source='item.unit', read_only=True)
    created_by_email = serializers.CharField(source='created_by.email', read_only=True)

    class Meta:
        model = StockMovement
        fields = [
            'id', 'organization', 'location', 'item', 'item_name', 'item_sku', 'item_unit',
            'movement_type', 'quantity', 'unit_cost',
            'reference_id', 'reference_type', 'notes',
            'movement_date', 'created_by', 'created_by_email',
            'batch_id', 'is_reversed', 'reversed_by', 'created_at',
        ]
        read_only_fields = [
            'id', 'created_at', 'is_reversed', 'reversed_by',
            'item_name', 'item_sku', 'item_unit', 'created_by_email',
        ]


class StockAlertSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_sku = serializers.CharField(source='item.sku', read_only=True)
    item_current_stock = serializers.DecimalField(
        source='item.current_stock', max_digits=12, decimal_places=4, read_only=True,
    )
    item_unit = serializers.CharField(source='item.unit', read_only=True)

    class Meta:
        model = StockAlert
        fields = [
            'id', 'organization', 'location', 'item',
            'item_name', 'item_sku', 'item_current_stock', 'item_unit',
            'alert_type', 'message',
            'is_resolved', 'resolved_at', 'resolved_by',
            'triggered_at', 'whatsapp_sent', 'whatsapp_sent_at',
        ]
        read_only_fields = [
            'id', 'triggered_at', 'whatsapp_sent', 'whatsapp_sent_at',
            'item_name', 'item_sku', 'item_current_stock', 'item_unit',
        ]


class InventoryAuditLogSerializer(serializers.ModelSerializer):
    performed_by_email = serializers.CharField(source='performed_by.email', read_only=True)

    class Meta:
        model = InventoryAuditLog
        fields = [
            'id', 'organization', 'location', 'action', 'model_name',
            'object_id', 'object_repr', 'before', 'after', 'diff',
            'performed_by', 'performed_by_email', 'timestamp', 'ip_address',
        ]
        read_only_fields = fields  # entire log is read-only


class StockAdjustmentSerializer(serializers.Serializer):
    """Input for the manual stock adjustment endpoint."""
    quantity = serializers.DecimalField(max_digits=12, decimal_places=4)
    reason = serializers.CharField(min_length=5, max_length=500)
    movement_date = serializers.DateField(required=False)
