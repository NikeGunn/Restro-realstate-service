"""
Inventory serializers.
"""
from decimal import Decimal

from rest_framework import serializers

from .models import (
    InventoryCategory, Supplier, InventoryItem, StockMovement,
    StockAlert, InventoryAuditLog,
    PurchaseOrder, PurchaseOrderItem,
    Recipe, RecipeIngredient, RecipeVersion,
    SalesImport, SupplierImport,
    LocationStock, LocationItemPricing, StockTake, StockTakeLine,
    PurchaseOrderEmail,
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
    locked_fields = serializers.SerializerMethodField()

    class Meta:
        model = Supplier
        fields = [
            'id', 'organization', 'location', 'name', 'contact_name',
            'email', 'phone', 'address', 'tax_id', 'payment_terms',
            'notes', 'is_active', 'item_count', 'locked_fields',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at',
                            'item_count', 'locked_fields']

    def get_item_count(self, obj):
        return obj.items.filter(is_active=True).count()

    def get_locked_fields(self, obj):
        if obj and obj.pk and obj.tax_id and obj.purchase_orders.exists():
            return ['tax_id']
        return []

    def validate_tax_id(self, value):
        # Once a supplier has POs and a tax_id is set, it's frozen.
        if self.instance and self.instance.tax_id and self.instance.tax_id != value:
            if self.instance.purchase_orders.exists():
                raise serializers.ValidationError(
                    'Tax ID cannot be changed once purchase orders exist for this supplier.'
                )
        return value


class InventoryItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    stock_status = serializers.SerializerMethodField()
    effective_stock = serializers.SerializerMethodField()
    locked_fields = serializers.SerializerMethodField()

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
            'stock_status', 'effective_stock', 'locked_fields',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'sku', 'current_stock',
            'created_at', 'updated_at',
            'category_name', 'supplier_name',
            'stock_status', 'effective_stock', 'locked_fields',
        ]

    def get_locked_fields(self, obj):
        return ['sku', 'unit'] if obj and obj.pk else []

    def get_stock_status(self, obj):
        if obj.current_stock < 0:
            return 'negative'
        if obj.reorder_level > 0 and obj.current_stock <= obj.reorder_level:
            return 'critical'
        if obj.reorder_level > 0 and obj.current_stock <= obj.reorder_level * 2:
            return 'low'
        return 'ok'

    def get_effective_stock(self, obj):
        from .services.tolerance_engine import ToleranceEngine
        es = ToleranceEngine.effective_stock(
            obj.current_stock, obj.reorder_level, obj.tolerance_percent,
        )
        return es.to_dict()

    def update(self, instance, validated_data):
        # Defensive: drop unit if someone tried to slip it past read_only_fields
        validated_data.pop('unit', None)
        validated_data.pop('sku', None)
        return super().update(instance, validated_data)


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


# ──────────────────────────────────────────────────────────────────────
# Purchase Orders
# ──────────────────────────────────────────────────────────────────────
class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_sku = serializers.CharField(source='item.sku', read_only=True)
    item_unit = serializers.CharField(source='item.unit', read_only=True)
    line_total = serializers.SerializerMethodField()
    # purchase_order is set by the parent on create; not part of inner payload.
    purchase_order = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = PurchaseOrderItem
        fields = [
            'id', 'purchase_order', 'item', 'item_name', 'item_sku', 'item_unit',
            'quantity_ordered', 'quantity_received',
            'unit_cost', 'notes', 'line_total',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'quantity_received',
            'item_name', 'item_sku', 'item_unit', 'line_total',
        ]

    def get_line_total(self, obj):
        return str((obj.quantity_ordered * obj.unit_cost).quantize(Decimal('0.0001')))


class PurchaseOrderSerializer(serializers.ModelSerializer):
    items = PurchaseOrderItemSerializer(many=True, required=False)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    locked_fields = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrder
        fields = [
            'id', 'organization', 'location', 'supplier', 'supplier_name',
            'order_number', 'status', 'order_date', 'expected_date', 'received_date',
            'notes', 'total_amount', 'sent_at', 'sent_to_email',
            'items', 'locked_fields',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'order_number', 'received_date', 'total_amount',
            'sent_at', 'sent_to_email',
            'created_at', 'updated_at', 'supplier_name', 'locked_fields',
        ]

    def get_locked_fields(self, obj):
        if not obj or not obj.pk:
            return []
        if obj.status != PurchaseOrder.Status.DRAFT:
            return ['supplier', 'order_number']
        return ['order_number']

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        po = PurchaseOrder.objects.create(**validated_data)
        for item_data in items_data:
            PurchaseOrderItem.objects.create(purchase_order=po, **item_data)
        po.recompute_total()
        po.refresh_from_db()
        return po

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        # Block supplier change once non-draft (also enforced at model save).
        if instance.status != PurchaseOrder.Status.DRAFT:
            validated_data.pop('supplier', None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        if items_data is not None and instance.status == PurchaseOrder.Status.DRAFT:
            # Replace lines wholesale only while still draft.
            instance.items.all().delete()
            for item_data in items_data:
                PurchaseOrderItem.objects.create(purchase_order=instance, **item_data)
        instance.recompute_total()
        instance.refresh_from_db()
        return instance


class PurchaseOrderReceiveSerializer(serializers.Serializer):
    """Input for PO receive endpoint."""
    line_id = serializers.UUIDField()
    quantity_received = serializers.DecimalField(max_digits=10, decimal_places=4)
    unit_cost = serializers.DecimalField(
        max_digits=10, decimal_places=4, required=False, allow_null=True,
    )


# ──────────────────────────────────────────────────────────────────────
# Recipes
# ──────────────────────────────────────────────────────────────────────
class RecipeIngredientSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_sku = serializers.CharField(source='item.sku', read_only=True)
    item_unit = serializers.CharField(source='item.unit', read_only=True)
    locked_fields = serializers.SerializerMethodField()
    # recipe is set by the parent on create; not part of inner payload.
    recipe = serializers.PrimaryKeyRelatedField(read_only=True)
    # unit defaults from item.unit if omitted.
    unit = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = RecipeIngredient
        fields = [
            'id', 'recipe', 'item', 'item_name', 'item_sku', 'item_unit',
            'quantity', 'unit', 'is_optional', 'notes', 'locked_fields',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at',
            'item_name', 'item_sku', 'item_unit', 'locked_fields',
        ]

    def get_locked_fields(self, obj):
        return ['item', 'unit'] if obj and obj.pk else []

    def update(self, instance, validated_data):
        validated_data.pop('item', None)
        validated_data.pop('unit', None)
        return super().update(instance, validated_data)


class RecipeSerializer(serializers.ModelSerializer):
    ingredients = RecipeIngredientSerializer(many=True, required=False)
    output_item_name = serializers.CharField(source='output_item.name', read_only=True)

    class Meta:
        model = Recipe
        fields = [
            'id', 'organization', 'location', 'name', 'description',
            'category', 'output_item', 'output_item_name',
            'output_quantity', 'output_unit', 'yield_percent',
            'is_active', 'version', 'ingredients',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'version', 'created_at', 'updated_at', 'output_item_name',
        ]

    def create(self, validated_data):
        ingredients_data = validated_data.pop('ingredients', [])
        recipe = Recipe.objects.create(**validated_data)
        for ing_data in ingredients_data:
            ing_data.setdefault('unit', ing_data['item'].unit)
            RecipeIngredient.objects.create(recipe=recipe, **ing_data)
        recipe.refresh_from_db()
        return recipe

    def update(self, instance, validated_data):
        ingredients_data = validated_data.pop('ingredients', None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        if ingredients_data is not None:
            # Replace ingredients wholesale; signals bump the version per change.
            instance.ingredients.all().delete()
            for ing_data in ingredients_data:
                ing_data.setdefault('unit', ing_data['item'].unit)
                RecipeIngredient.objects.create(recipe=instance, **ing_data)
        instance.refresh_from_db()
        return instance


class RecipeVersionSerializer(serializers.ModelSerializer):
    changed_by_email = serializers.CharField(source='changed_by.email', read_only=True)

    class Meta:
        model = RecipeVersion
        fields = [
            'id', 'recipe', 'version_number', 'snapshot',
            'changed_by', 'changed_by_email', 'changed_at', 'reason',
        ]
        read_only_fields = fields


class RecipeBatchSerializer(serializers.Serializer):
    batches = serializers.DecimalField(max_digits=10, decimal_places=4, min_value=Decimal('0.01'))


# ──────────────────────────────────────────────────────────────────────
# Imports
# ──────────────────────────────────────────────────────────────────────
class _BaseImportSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    def get_file_url(self, obj):
        try:
            return obj.import_file.url if obj.import_file else None
        except Exception:
            return None


class SalesImportSerializer(_BaseImportSerializer):
    class Meta:
        model = SalesImport
        fields = [
            'id', 'organization', 'location', 'import_file', 'file_url', 'file_name',
            'status', 'row_count', 'processed_count', 'error_count',
            'error_log', 'batch_id', 'imported_at', 'summary', 'column_map',
            'task_id', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'file_url', 'status', 'row_count', 'processed_count',
            'error_count', 'error_log', 'batch_id', 'imported_at',
            'summary', 'column_map', 'task_id', 'created_at', 'updated_at',
        ]


class SupplierImportSerializer(_BaseImportSerializer):
    class Meta:
        model = SupplierImport
        fields = [
            'id', 'organization', 'location', 'supplier',
            'import_file', 'file_url', 'file_name',
            'status', 'row_count', 'processed_count', 'error_count',
            'error_log', 'batch_id', 'imported_at', 'summary', 'column_map',
            'task_id', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'file_url', 'status', 'row_count', 'processed_count',
            'error_count', 'error_log', 'batch_id', 'imported_at',
            'summary', 'column_map', 'task_id', 'created_at', 'updated_at',
        ]


class ImportColumnMapSerializer(serializers.Serializer):
    """Optional override map applied at commit time."""
    column_map = serializers.DictField(child=serializers.IntegerField(), required=False)


# ──────────────────────────────────────────────────────────────────────
# AI
# ──────────────────────────────────────────────────────────────────────
class InventoryAIQuerySerializer(serializers.Serializer):
    question = serializers.CharField(min_length=2, max_length=500)
    organization = serializers.UUIDField(required=False)
    location = serializers.UUIDField(required=False, allow_null=True)


# ──────────────────────────────────────────────────────────────────────
# Phase 4 — LocationStock, StockTake, LocationItemPricing
# ──────────────────────────────────────────────────────────────────────
class LocationStockSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_sku = serializers.CharField(source='item.sku', read_only=True)
    item_unit = serializers.CharField(source='item.unit', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True, default=None)
    effective_reorder = serializers.SerializerMethodField()

    class Meta:
        model = LocationStock
        fields = [
            'id', 'item', 'item_name', 'item_sku', 'item_unit',
            'location', 'location_name',
            'current_stock', 'reorder_level_override', 'effective_reorder',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'item_name', 'item_sku', 'item_unit', 'location_name',
            'current_stock', 'effective_reorder', 'created_at', 'updated_at',
        ]

    def get_effective_reorder(self, obj):
        return str(obj.effective_reorder_level)


class StockTakeLineSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_sku = serializers.CharField(source='item.sku', read_only=True)
    item_unit = serializers.CharField(source='item.unit', read_only=True)
    variance = serializers.SerializerMethodField()

    class Meta:
        model = StockTakeLine
        fields = [
            'id', 'stock_take', 'item', 'item_name', 'item_sku', 'item_unit',
            'system_count', 'counted', 'variance', 'notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'stock_take', 'item_name', 'item_sku', 'item_unit',
            'variance', 'created_at', 'updated_at',
        ]

    def get_variance(self, obj):
        return str(obj.variance)


class StockTakeSerializer(serializers.ModelSerializer):
    lines = StockTakeLineSerializer(many=True, required=False)
    location_name = serializers.CharField(source='location.name', read_only=True, default=None)

    class Meta:
        model = StockTake
        fields = [
            'id', 'organization', 'location', 'location_name',
            'name', 'notes', 'status',
            'started_at', 'committed_at', 'created_by',
            'lines', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'status', 'committed_at', 'started_at',
            'location_name', 'created_at', 'updated_at',
        ]

    def create(self, validated_data):
        lines_data = validated_data.pop('lines', [])
        st = StockTake.objects.create(**validated_data)
        for ln in lines_data:
            StockTakeLine.objects.create(stock_take=st, **ln)
        return st

    def update(self, instance, validated_data):
        if instance.status != StockTake.Status.IN_PROGRESS:
            raise serializers.ValidationError(
                'Cannot edit a stock-take that is not in progress.'
            )
        lines_data = validated_data.pop('lines', None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        if lines_data is not None:
            instance.lines.all().delete()
            for ln in lines_data:
                StockTakeLine.objects.create(stock_take=instance, **ln)
        return instance


class LocationItemPricingSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)

    class Meta:
        model = LocationItemPricing
        fields = [
            'id', 'item', 'item_name', 'location', 'location_name',
            'unit_cost', 'selling_price', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'item_name', 'location_name', 'created_at', 'updated_at']


# ──────────────────────────────────────────────────────────────────────
# Phase 4 — PurchaseOrder send
# ──────────────────────────────────────────────────────────────────────
class PurchaseOrderSendSerializer(serializers.Serializer):
    to_email = serializers.EmailField(required=False, allow_blank=True)


class PurchaseOrderEmailSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseOrderEmail
        fields = [
            'id', 'purchase_order', 'to_email', 'subject', 'sent_at',
            'error', 'sent_by', 'created_at',
        ]
        read_only_fields = fields


# ──────────────────────────────────────────────────────────────────────
# Phase 4 — Bulk item edit
# ──────────────────────────────────────────────────────────────────────
class BulkItemEditSerializer(serializers.Serializer):
    """
    Whitelisted bulk patch: only safe fields. unit/sku/current_stock are
    NEVER bulk-editable (immutable / signal-managed).
    """
    ALLOWED = {'reorder_level', 'reorder_quantity', 'category', 'supplier', 'is_active'}

    ids = serializers.ListField(
        child=serializers.UUIDField(), min_length=1, max_length=500,
    )
    patch = serializers.DictField()

    def validate_patch(self, value):
        bad = set(value.keys()) - self.ALLOWED
        if bad:
            raise serializers.ValidationError(
                f'Fields not permitted in bulk edit: {sorted(bad)}'
            )
        if not value:
            raise serializers.ValidationError('patch is empty.')
        return value
