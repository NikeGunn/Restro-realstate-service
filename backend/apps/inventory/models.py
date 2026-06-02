"""
Inventory models — Plane B.

All tables prefixed `inv_` for visual isolation in DB tooling.
StockMovement is an append-only ledger; InventoryAuditLog is non-deletable.
InventoryItem.current_stock is signal-computed from StockMovement and must
NEVER be written to directly.
"""
import uuid
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models

from apps.accounts.models import Organization, Location, User


# ──────────────────────────────────────────────────────────────────────
# Mixins
# ──────────────────────────────────────────────────────────────────────
class _InventoryTimestamps(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ──────────────────────────────────────────────────────────────────────
# Category
# ──────────────────────────────────────────────────────────────────────
class InventoryCategory(_InventoryTimestamps):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='inventory_categories'
    )
    location = models.ForeignKey(
        Location, on_delete=models.CASCADE,
        null=True, blank=True, related_name='inventory_categories',
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_inventory_categories',
    )

    class Meta:
        db_table = 'inv_category'
        unique_together = [('organization', 'name')]
        ordering = ['name']
        verbose_name = 'Inventory Category'
        verbose_name_plural = 'Inventory Categories'

    def __str__(self):
        return self.name


# ──────────────────────────────────────────────────────────────────────
# Supplier
# ──────────────────────────────────────────────────────────────────────
class Supplier(_InventoryTimestamps):
    class PaymentTerms(models.TextChoices):
        COD = 'cod', 'Cash on Delivery'
        NET7 = 'net7', 'Net 7'
        NET15 = 'net15', 'Net 15'
        NET30 = 'net30', 'Net 30'
        NET60 = 'net60', 'Net 60'

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='suppliers'
    )
    location = models.ForeignKey(
        Location, on_delete=models.SET_NULL, null=True, blank=True, related_name='suppliers',
    )
    name = models.CharField(max_length=200)
    contact_name = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    tax_id = models.CharField(max_length=50, blank=True)
    payment_terms = models.CharField(
        max_length=10, choices=PaymentTerms.choices, default=PaymentTerms.COD,
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_suppliers',
    )

    class Meta:
        db_table = 'inv_supplier'
        ordering = ['name']
        indexes = [models.Index(fields=['organization', 'is_active'])]

    def __str__(self):
        return self.name


# ──────────────────────────────────────────────────────────────────────
# Item
# ──────────────────────────────────────────────────────────────────────
class InventoryItem(_InventoryTimestamps):
    class Unit(models.TextChoices):
        KG = 'kg', 'Kilogram'
        G = 'g', 'Gram'
        LITER = 'liter', 'Liter'
        ML = 'ml', 'Milliliter'
        CL = 'cl', 'Centiliter'        # Phase 4 — cocktail/drink formulas
        FL_OZ = 'fl_oz', 'Fluid Ounce'  # Phase 4 — cocktail/drink formulas
        PIECE = 'piece', 'Piece'
        BOX = 'box', 'Box'
        BAG = 'bag', 'Bag'
        DOZEN = 'dozen', 'Dozen'
        PACK = 'pack', 'Pack'

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='inventory_items'
    )
    location = models.ForeignKey(
        Location, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='inventory_items',
    )
    sku = models.CharField(max_length=50, blank=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        InventoryCategory, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='items',
    )
    unit = models.CharField(max_length=10, choices=Unit.choices)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal('0'))
    selling_price = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True,
    )
    reorder_level = models.DecimalField(
        max_digits=10, decimal_places=4, default=Decimal('0'),
    )
    reorder_quantity = models.DecimalField(
        max_digits=10, decimal_places=4, default=Decimal('0'),
    )
    current_stock = models.DecimalField(
        max_digits=12, decimal_places=4, default=Decimal('0'),
        help_text="Computed by signal from StockMovement ledger. Do not write directly.",
    )
    tolerance_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0.5'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('5'))],
    )
    is_active = models.BooleanField(default=True)
    is_perishable = models.BooleanField(default=False)
    expiry_days = models.PositiveIntegerField(null=True, blank=True)
    supplier = models.ForeignKey(
        Supplier, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='items',
    )
    barcode = models.CharField(max_length=100, null=True, blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_inventory_items',
    )

    class Meta:
        db_table = 'inv_item'
        unique_together = [
            ('organization', 'sku'),
            ('organization', 'barcode'),
        ]
        ordering = ['name']
        indexes = [
            models.Index(fields=['organization', 'is_active']),
            models.Index(fields=['organization', 'category']),
        ]

    def __str__(self):
        return f"{self.sku} — {self.name}"

    def save(self, *args, **kwargs):
        if self._state.adding:
            if not self.sku:
                self.sku = self._generate_sku()
        else:
            original = type(self).objects.get(pk=self.pk)
            if original.unit != self.unit:
                raise ValidationError(
                    {'unit': 'Unit cannot be changed after item creation.'}
                )
            if original.sku != self.sku:
                raise ValidationError(
                    {'sku': 'SKU cannot be changed after item creation.'}
                )
        super().save(*args, **kwargs)

    def _generate_sku(self):
        prefix = ''.join(c for c in self.organization.name if c.isalnum())[:4].upper() or 'INV'
        date_str = date.today().strftime('%Y%m%d')
        last = (
            type(self).objects.filter(
                organization=self.organization,
                sku__startswith=f'INV-{prefix}-{date_str}-',
            )
            .order_by('-sku')
            .first()
        )
        seq = 1
        if last:
            try:
                seq = int(last.sku.split('-')[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        return f'INV-{prefix}-{date_str}-{seq:04d}'


# ──────────────────────────────────────────────────────────────────────
# LocationStock — per-location projection of the StockMovement ledger.
#
# One row per (item, location). location=NULL is a valid bucket for
# movements/items that have no location FK. InventoryItem.current_stock
# remains the org-wide aggregate (sum of all LocationStock rows for the
# item) and is signal-maintained for backward compatibility with every
# existing query, report, and serializer.
# ──────────────────────────────────────────────────────────────────────
class LocationStock(_InventoryTimestamps):
    item = models.ForeignKey(
        InventoryItem, on_delete=models.CASCADE, related_name='location_stocks',
    )
    location = models.ForeignKey(
        Location, on_delete=models.CASCADE,
        null=True, blank=True, related_name='item_stocks',
    )
    current_stock = models.DecimalField(
        max_digits=12, decimal_places=4, default=Decimal('0'),
        help_text="Per-location stock projection. Maintained by the StockMovement signal.",
    )
    reorder_level_override = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True,
        help_text="Optional per-location reorder level. Falls back to item.reorder_level when null.",
    )

    class Meta:
        db_table = 'inv_location_stock'
        constraints = [
            models.UniqueConstraint(
                fields=['item', 'location'],
                name='uniq_location_stock_item_location',
                condition=models.Q(location__isnull=False),
            ),
            models.UniqueConstraint(
                fields=['item'],
                name='uniq_location_stock_item_null_location',
                condition=models.Q(location__isnull=True),
            ),
        ]
        indexes = [models.Index(fields=['item', 'location'])]
        verbose_name = 'Location Stock'
        verbose_name_plural = 'Location Stocks'

    def __str__(self):
        loc = self.location.name if self.location_id else 'no-location'
        return f'{self.item.name} @ {loc}: {self.current_stock}'

    @property
    def effective_reorder_level(self):
        return (
            self.reorder_level_override
            if self.reorder_level_override is not None
            else self.item.reorder_level
        )


# ──────────────────────────────────────────────────────────────────────
# StockMovement (append-only ledger)
# ──────────────────────────────────────────────────────────────────────
class StockMovement(_InventoryTimestamps):
    class MovementType(models.TextChoices):
        PURCHASE = 'purchase', 'Purchase'
        SALE = 'sale', 'Sale'
        WASTE = 'waste', 'Waste / Spoilage'
        ADJUSTMENT = 'adjustment', 'Manual Adjustment'
        RECIPE_CONSUMPTION = 'recipe_consumption', 'Recipe Consumption'
        SUPPLIER_RETURN = 'supplier_return', 'Supplier Return'
        OPENING_STOCK = 'opening_stock', 'Opening Stock'
        IMPORT_SALE = 'import_sale', 'Imported Sale'
        IMPORT_PURCHASE = 'import_purchase', 'Imported Purchase'

    NEGATIVE_TYPES = {'sale', 'waste', 'recipe_consumption', 'import_sale'}
    POSITIVE_TYPES = {'purchase', 'supplier_return', 'opening_stock', 'import_purchase'}

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='stock_movements'
    )
    location = models.ForeignKey(
        Location, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_movements',
    )
    item = models.ForeignKey(
        InventoryItem, on_delete=models.PROTECT, related_name='movements',
    )
    movement_type = models.CharField(max_length=24, choices=MovementType.choices)
    quantity = models.DecimalField(max_digits=12, decimal_places=4)
    unit_cost = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True,
    )
    reference_id = models.CharField(max_length=200, blank=True)
    reference_type = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)
    movement_date = models.DateField(default=date.today)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_movements',
    )
    batch_id = models.UUIDField(null=True, blank=True, db_index=True)
    is_reversed = models.BooleanField(default=False)
    reversed_by = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reversal_of',
    )

    class Meta:
        db_table = 'inv_stock_movement'
        ordering = ['-movement_date', '-created_at']
        indexes = [
            models.Index(fields=['item', 'movement_date']),
            models.Index(fields=['organization', '-created_at']),
        ]

    def __str__(self):
        return f"{self.movement_type} {self.quantity} {self.item.name}"

    def clean(self):
        super().clean()
        if self.movement_type in self.NEGATIVE_TYPES and self.quantity > 0:
            raise ValidationError(
                {'quantity': f'{self.movement_type} movements must have a negative quantity.'}
            )
        if self.movement_type in self.POSITIVE_TYPES and self.quantity < 0:
            raise ValidationError(
                {'quantity': f'{self.movement_type} movements must have a positive quantity.'}
            )

    def save(self, *args, **kwargs):
        if self.pk and not self._state.adding:
            raise ValidationError(
                "StockMovement is an append-only ledger. "
                "To correct an error, use StockEngine.reverse_movement(). "
                f"Record ID: {self.pk}"
            )
        self.full_clean(exclude=['organization', 'item'])
        super().save(*args, **kwargs)


# ──────────────────────────────────────────────────────────────────────
# StockAlert
# ──────────────────────────────────────────────────────────────────────
class StockAlert(_InventoryTimestamps):
    class AlertType(models.TextChoices):
        LOW_STOCK = 'low_stock', 'Low Stock'
        EXPIRY = 'expiry', 'Expiring Soon'
        NEGATIVE_STOCK = 'negative_stock', 'Negative Stock'
        VARIANCE = 'variance', 'Variance Detected'
        OVERSTOCK = 'overstock', 'Overstock'

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='inventory_alerts'
    )
    location = models.ForeignKey(
        Location, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='inventory_alerts',
    )
    item = models.ForeignKey(
        InventoryItem, on_delete=models.CASCADE, related_name='alerts',
    )
    alert_type = models.CharField(max_length=20, choices=AlertType.choices)
    message = models.TextField()
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='resolved_inventory_alerts',
    )
    triggered_at = models.DateTimeField(auto_now_add=True)
    whatsapp_sent = models.BooleanField(default=False)
    whatsapp_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'inv_stock_alert'
        ordering = ['-triggered_at']
        indexes = [
            models.Index(fields=['organization', 'is_resolved']),
            models.Index(fields=['item', 'is_resolved']),
        ]

    def __str__(self):
        return f"{self.alert_type}: {self.item.name}"


# ──────────────────────────────────────────────────────────────────────
# Audit Log (non-deletable)
# ──────────────────────────────────────────────────────────────────────
class InventoryAuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='inventory_audit_logs'
    )
    location = models.ForeignKey(
        Location, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='inventory_audit_logs',
    )
    action = models.CharField(max_length=50)
    model_name = models.CharField(max_length=100)
    object_id = models.UUIDField()
    object_repr = models.CharField(max_length=200)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    diff = models.JSONField(null=True, blank=True)
    performed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='inventory_audit_logs',
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = 'inv_audit_log'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['organization', '-timestamp']),
            models.Index(fields=['model_name', 'object_id']),
        ]

    def __str__(self):
        return f"{self.action} {self.model_name} {self.object_repr} @ {self.timestamp:%Y-%m-%d %H:%M}"

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit log entries cannot be deleted.")


# ──────────────────────────────────────────────────────────────────────
# PurchaseOrder
# ──────────────────────────────────────────────────────────────────────
class PurchaseOrder(_InventoryTimestamps):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        SENT = 'sent', 'Sent'
        PARTIAL = 'partial', 'Partially Received'
        RECEIVED = 'received', 'Received'
        CANCELLED = 'cancelled', 'Cancelled'

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='purchase_orders'
    )
    location = models.ForeignKey(
        Location, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='purchase_orders',
    )
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name='purchase_orders',
    )
    order_number = models.CharField(max_length=50, blank=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.DRAFT,
    )
    order_date = models.DateField(default=date.today)
    expected_date = models.DateField(null=True, blank=True)
    received_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    sent_to_email = models.EmailField(blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_purchase_orders',
    )

    class Meta:
        db_table = 'inv_purchase_order'
        unique_together = [('organization', 'order_number')]
        ordering = ['-order_date', '-created_at']
        indexes = [models.Index(fields=['organization', 'status'])]

    def __str__(self):
        return self.order_number or f'PO {self.id}'

    def save(self, *args, **kwargs):
        if self._state.adding:
            if not self.order_number:
                self.order_number = self._generate_order_number()
        else:
            original = type(self).objects.get(pk=self.pk)
            if original.order_number != self.order_number:
                raise ValidationError(
                    {'order_number': 'Order number is immutable.'}
                )
            if (
                original.status != self.Status.DRAFT
                and original.supplier_id != self.supplier_id
            ):
                raise ValidationError(
                    {'supplier': 'Supplier cannot be changed once order leaves draft status.'}
                )
        super().save(*args, **kwargs)

    def _generate_order_number(self):
        prefix = ''.join(c for c in self.organization.name if c.isalnum())[:4].upper() or 'ORG'
        date_str = date.today().strftime('%Y%m%d')
        last = (
            type(self).objects.filter(
                organization=self.organization,
                order_number__startswith=f'PO-{date_str}-{prefix}-',
            )
            .order_by('-order_number')
            .first()
        )
        seq = 1
        if last:
            try:
                seq = int(last.order_number.split('-')[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        return f'PO-{date_str}-{prefix}-{seq:04d}'

    def recompute_total(self):
        total = sum(
            (li.quantity_ordered * li.unit_cost for li in self.items.all()),
            Decimal('0'),
        )
        type(self).objects.filter(pk=self.pk).update(total_amount=total)
        return total


class PurchaseOrderItem(_InventoryTimestamps):
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name='items',
    )
    item = models.ForeignKey(
        InventoryItem, on_delete=models.PROTECT, related_name='purchase_order_lines',
    )
    quantity_ordered = models.DecimalField(max_digits=10, decimal_places=4)
    quantity_received = models.DecimalField(
        max_digits=10, decimal_places=4, default=Decimal('0'),
    )
    unit_cost = models.DecimalField(max_digits=10, decimal_places=4)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'inv_purchase_order_item'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.item.name} × {self.quantity_ordered}"

    @property
    def line_total(self):
        return self.quantity_ordered * self.unit_cost


# ──────────────────────────────────────────────────────────────────────
# Recipe
# ──────────────────────────────────────────────────────────────────────
class Recipe(_InventoryTimestamps):
    class FormulaType(models.TextChoices):
        FOOD_RECIPE = 'food_recipe', 'Food Recipe'
        DRINK_FORMULA = 'drink_formula', 'Drink Formula'
        COCKTAIL_FORMULA = 'cocktail_formula', 'Cocktail Formula'
        BATCH_RECIPE = 'batch_recipe', 'Batch Recipe'
        PROMO_COMBO_FORMULA = 'promo_combo_formula', 'Promo Combo Formula'

    # Formula types that pour liquid and therefore use pour-variance tolerance.
    POUR_FORMULA_TYPES = {'drink_formula', 'cocktail_formula'}

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='recipes'
    )
    location = models.ForeignKey(
        Location, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='recipes',
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        InventoryCategory, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='recipes',
    )
    # Phase 4 — drink/cocktail formula support.
    formula_type = models.CharField(
        max_length=20, choices=FormulaType.choices,
        default=FormulaType.FOOD_RECIPE,
    )
    serving_ml = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text='Total expected serve volume (ml) — drives pour variance.',
    )
    pour_variance_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text='Overrides per-item tolerance for drink/cocktail formulas. '
                  'Defaults to INVENTORY_SETTINGS[DEFAULT_POUR_VARIANCE_PERCENT].',
    )
    # Bridge for 1+1-style deduction. String ref → no restaurant import here
    # (inventory→restaurant stays one-directional).
    linked_promo_rule = models.ForeignKey(
        'restaurant.MenuPromoRule', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='inventory_recipes',
    )
    output_item = models.ForeignKey(
        InventoryItem, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='produced_by_recipes',
    )
    output_quantity = models.DecimalField(
        max_digits=10, decimal_places=4, default=Decimal('1'),
    )
    output_unit = models.CharField(max_length=20, blank=True)
    yield_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('100'),
        validators=[MinValueValidator(Decimal('1')), MaxValueValidator(Decimal('100'))],
    )
    is_active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_recipes',
    )

    class Meta:
        db_table = 'inv_recipe'
        ordering = ['name']
        indexes = [
            models.Index(fields=['organization', 'is_active']),
            models.Index(fields=['organization', 'formula_type']),
        ]

    def __str__(self):
        return self.name

    @property
    def is_pour_formula(self) -> bool:
        return self.formula_type in self.POUR_FORMULA_TYPES

    def resolved_pour_variance_percent(self):
        """
        The pour variance to apply for this recipe: the explicit override if
        set, otherwise the settings default. Returns None for non-pour
        formulas (so callers fall back to per-item tolerance). Single source
        of truth for variance resolution (DRY).
        """
        if not self.is_pour_formula:
            return None
        if self.pour_variance_percent is not None:
            return self.pour_variance_percent
        from django.conf import settings
        return settings.INVENTORY_SETTINGS.get('DEFAULT_POUR_VARIANCE_PERCENT')


class RecipeIngredient(_InventoryTimestamps):
    recipe = models.ForeignKey(
        Recipe, on_delete=models.CASCADE, related_name='ingredients',
    )
    item = models.ForeignKey(
        InventoryItem, on_delete=models.PROTECT, related_name='recipe_ingredients',
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=4)
    unit = models.CharField(max_length=20)
    is_optional = models.BooleanField(default=False)
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = 'inv_recipe_ingredient'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.recipe.name} :: {self.item.name}"

    def clean(self):
        super().clean()
        if self.unit and self.item_id and self.unit != self.item.unit:
            raise ValidationError(
                {'unit': f'Unit must match the inventory item unit ({self.item.unit}).'}
            )

    def save(self, *args, **kwargs):
        if self._state.adding:
            if not self.unit and self.item_id:
                self.unit = self.item.unit
        else:
            original = type(self).objects.get(pk=self.pk)
            if original.item_id != self.item_id:
                raise ValidationError(
                    {'item': 'Ingredient item cannot be changed after creation.'}
                )
            if original.unit != self.unit:
                raise ValidationError(
                    {'unit': 'Ingredient unit cannot be changed after creation.'}
                )
        # Light validation; full_clean() called at view layer
        if self.item_id and self.unit and self.unit != self.item.unit:
            raise ValidationError(
                {'unit': f'Unit must match the inventory item unit ({self.item.unit}).'}
            )
        super().save(*args, **kwargs)


class RecipeVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipe = models.ForeignKey(
        Recipe, on_delete=models.CASCADE, related_name='versions',
    )
    version_number = models.PositiveIntegerField()
    snapshot = models.JSONField()
    changed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='recipe_version_changes',
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = 'inv_recipe_version'
        ordering = ['-version_number']
        unique_together = [('recipe', 'version_number')]

    def __str__(self):
        return f'{self.recipe.name} v{self.version_number}'


# ──────────────────────────────────────────────────────────────────────
# Imports
# ──────────────────────────────────────────────────────────────────────
class _BaseImport(_InventoryTimestamps):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='+',
    )
    location = models.ForeignKey(
        Location, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    file_name = models.CharField(max_length=255)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING,
    )
    row_count = models.PositiveIntegerField(default=0)
    processed_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    error_log = models.JSONField(default=list, blank=True)
    batch_id = models.UUIDField(default=uuid.uuid4)
    imported_at = models.DateTimeField(null=True, blank=True)
    summary = models.JSONField(default=dict, blank=True)
    column_map = models.JSONField(default=dict, blank=True)
    task_id = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )

    class Meta:
        abstract = True
        ordering = ['-created_at']


class SalesImport(_BaseImport):
    import_file = models.FileField(upload_to='sales_imports/%Y/%m/')

    class Meta(_BaseImport.Meta):
        db_table = 'inv_sales_import'

    def __str__(self):
        return f'SalesImport {self.file_name} [{self.status}]'


class SupplierImport(_BaseImport):
    import_file = models.FileField(upload_to='supplier_imports/%Y/%m/')
    supplier = models.ForeignKey(
        Supplier, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='imports',
    )

    class Meta(_BaseImport.Meta):
        db_table = 'inv_supplier_import'

    def __str__(self):
        return f'SupplierImport {self.file_name} [{self.status}]'


# ──────────────────────────────────────────────────────────────────────
# Phase 4 — Stock-take / cycle count
# ──────────────────────────────────────────────────────────────────────
class StockTake(_InventoryTimestamps):
    class Status(models.TextChoices):
        IN_PROGRESS = 'in_progress', 'In Progress'
        COMMITTED = 'committed', 'Committed'
        CANCELLED = 'cancelled', 'Cancelled'

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='stock_takes',
    )
    location = models.ForeignKey(
        Location, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_takes',
    )
    name = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.IN_PROGRESS,
    )
    started_at = models.DateTimeField(auto_now_add=True)
    committed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_stock_takes',
    )

    class Meta:
        db_table = 'inv_stock_take'
        ordering = ['-started_at']
        indexes = [models.Index(fields=['organization', 'status'])]


class StockTakeLine(_InventoryTimestamps):
    stock_take = models.ForeignKey(
        StockTake, on_delete=models.CASCADE, related_name='lines',
    )
    item = models.ForeignKey(
        InventoryItem, on_delete=models.PROTECT, related_name='stock_take_lines',
    )
    system_count = models.DecimalField(max_digits=12, decimal_places=4)
    counted = models.DecimalField(max_digits=12, decimal_places=4)
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = 'inv_stock_take_line'
        ordering = ['created_at']
        unique_together = [('stock_take', 'item')]

    @property
    def variance(self):
        return self.counted - self.system_count


# ──────────────────────────────────────────────────────────────────────
# Phase 4 — Per-location item pricing override
# ──────────────────────────────────────────────────────────────────────
class LocationItemPricing(_InventoryTimestamps):
    item = models.ForeignKey(
        InventoryItem, on_delete=models.CASCADE, related_name='location_pricing',
    )
    location = models.ForeignKey(
        Location, on_delete=models.CASCADE, related_name='item_pricing',
    )
    unit_cost = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True,
    )
    selling_price = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True,
    )

    class Meta:
        db_table = 'inv_location_item_pricing'
        unique_together = [('item', 'location')]
        ordering = ['item__name']


# ──────────────────────────────────────────────────────────────────────
# Phase 4 — PurchaseOrder send + email tracking
# Add fields by extending PurchaseOrder lazily via a separate "PurchaseOrderEmail"
# tracking model so we don't break the existing PO migration.
# ──────────────────────────────────────────────────────────────────────
class PurchaseOrderEmail(_InventoryTimestamps):
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name='emails',
    )
    to_email = models.EmailField()
    subject = models.CharField(max_length=300)
    body = models.TextField()
    sent_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)
    sent_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sent_po_emails',
    )

    class Meta:
        db_table = 'inv_po_email'
        ordering = ['-created_at']


# ──────────────────────────────────────────────────────────────────────
# Phase 6 — Plane A integration: link a Booking to one or more recipes
# whose ingredients should be consumed when the booking is fulfilled.
#
# This is the ONLY model that names a Plane A entity (`restaurant.Booking`).
# The relationship is one-directional: Plane A has no awareness of Plane B.
# A signal in apps.inventory.signals watches Booking.status flips to
# COMPLETED and consumes the recipes via StockEngine. Auto-consumption is
# gated by INVENTORY_SETTINGS['AUTO_CONSUME_ON_BOOKING_COMPLETE'] (default
# False), so production behavior is unchanged until explicitly enabled.
# ──────────────────────────────────────────────────────────────────────
class RecipeBookingLink(_InventoryTimestamps):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE,
        related_name='recipe_booking_links',
    )
    booking = models.ForeignKey(
        'restaurant.Booking', on_delete=models.CASCADE,
        related_name='recipe_links',
    )
    recipe = models.ForeignKey(
        Recipe, on_delete=models.PROTECT, related_name='booking_links',
    )
    batches = models.DecimalField(
        max_digits=10, decimal_places=4, default=Decimal('1'),
        validators=[MinValueValidator(Decimal('0.0001'))],
    )
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'inv_recipe_booking_link'
        unique_together = [('booking', 'recipe')]
        ordering = ['created_at']
        indexes = [models.Index(fields=['organization', 'consumed_at'])]

    def __str__(self):
        return f'{self.recipe.name} × {self.batches} → booking {self.booking_id}'


# ──────────────────────────────────────────────────────────────────────
# Phase 6 — Plane B AI inventory profile (per-org, refreshed daily).
#
# A compact JSON snapshot of an org's inventory shape (top items, suppliers,
# recipes, recent issues) that InventoryAIEngine injects into the prompt
# instead of recomputing context on every query. One row per organization.
# ──────────────────────────────────────────────────────────────────────
class InventoryAIProfile(_InventoryTimestamps):
    organization = models.OneToOneField(
        Organization, on_delete=models.CASCADE,
        related_name='inventory_ai_profile',
    )
    profile = models.JSONField(default=dict, blank=True)
    generated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'inv_ai_profile'

    def __str__(self):
        return f'AIProfile({self.organization.name})'


# ──────────────────────────────────────────────────────────────────────
# Phase 4 — Consumption log (append-only).
#
# Every recipe consumption that produces stock movements writes one
# ConsumptionLog row per ingredient movement, classifying WHY stock was
# consumed (cocktail serve, promo sale, spoilage, …). Mirrors the
# StockMovement append-only guard — it is an audit ledger, never edited.
# ──────────────────────────────────────────────────────────────────────
class ConsumptionLog(_InventoryTimestamps):
    class ConsumptionType(models.TextChoices):
        MANUAL = 'manual', 'Manual'
        BOOKING_AUTO = 'booking_auto', 'Booking Auto-consume'
        PROMO_SALE = 'promo_sale', 'Promo Sale'
        SALES_IMPORT = 'sales_import', 'Sales Import'
        COCKTAIL_SERVE = 'cocktail_serve', 'Cocktail Serve'
        STAFF_USE = 'staff_use', 'Staff Use'
        SPOILAGE = 'spoilage', 'Spoilage'
        WASTAGE = 'wastage', 'Wastage'
        COMPLIMENTARY = 'complimentary', 'Complimentary'
        GIVEAWAY = 'giveaway', 'Giveaway'

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='consumption_logs'
    )
    recipe = models.ForeignKey(
        Recipe, on_delete=models.CASCADE, related_name='consumption_logs',
    )
    movement = models.ForeignKey(
        StockMovement, on_delete=models.CASCADE, related_name='consumption_logs',
    )
    consumption_type = models.CharField(
        max_length=20, choices=ConsumptionType.choices,
        default=ConsumptionType.MANUAL,
    )
    quantity_consumed = models.DecimalField(max_digits=10, decimal_places=4)

    class Meta:
        db_table = 'inv_consumption_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', 'consumption_type', '-created_at']),
        ]

    def __str__(self):
        return f'{self.consumption_type} {self.quantity_consumed} ({self.recipe.name})'

    def save(self, *args, **kwargs):
        if self.pk and not self._state.adding:
            raise ValidationError(
                "ConsumptionLog is an append-only ledger and cannot be edited. "
                f"Record ID: {self.pk}"
            )
        super().save(*args, **kwargs)
