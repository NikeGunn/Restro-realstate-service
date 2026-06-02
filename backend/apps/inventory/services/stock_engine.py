"""
StockEngine
===========
Single creation point for StockMovement records. All stock mutation
operations — manual adjustments, PO receipts, recipe consumption, import
applications, reversals — go through here.
"""
from datetime import date
from decimal import Decimal
from typing import Optional

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.inventory.models import (
    InventoryItem, StockMovement, PurchaseOrder, PurchaseOrderItem,
)


class StockEngine:
    def __init__(self, organization, location=None, performed_by=None):
        self.organization = organization
        self.location = location
        self.performed_by = performed_by

    # ──────────────────────────────────────────────────────────────
    # Internal: single creation point
    # ──────────────────────────────────────────────────────────────
    def _create_movement(
        self, item: InventoryItem, movement_type: str,
        quantity: Decimal, **kwargs,
    ) -> StockMovement:
        return StockMovement.objects.create(
            organization=self.organization,
            location=self.location or item.location,
            item=item,
            movement_type=movement_type,
            quantity=quantity,
            created_by=self.performed_by,
            **kwargs,
        )

    # ──────────────────────────────────────────────────────────────
    # Manual adjustment
    # ──────────────────────────────────────────────────────────────
    def manual_adjustment(
        self, item: InventoryItem, quantity: Decimal,
        reason: str, movement_date: Optional[date] = None,
    ) -> StockMovement:
        if not reason or len(reason.strip()) < 5:
            raise ValidationError(
                {'reason': 'Manual adjustment requires a reason (min 5 characters).'}
            )
        return self._create_movement(
            item=item,
            movement_type=StockMovement.MovementType.ADJUSTMENT,
            quantity=quantity,
            notes=reason,
            movement_date=movement_date or date.today(),
        )

    # ──────────────────────────────────────────────────────────────
    # Reversal
    # ──────────────────────────────────────────────────────────────
    @transaction.atomic
    def reverse_movement(self, movement_id: str, reason: str) -> StockMovement:
        try:
            movement = StockMovement.objects.select_for_update().get(
                pk=movement_id, organization=self.organization,
            )
        except StockMovement.DoesNotExist:
            raise ValidationError('Movement not found in your organization.')
        if movement.is_reversed:
            raise ValidationError('This movement has already been reversed.')

        reversal = self._create_movement(
            item=movement.item,
            movement_type=StockMovement.MovementType.ADJUSTMENT,
            quantity=-movement.quantity,
            notes=f'REVERSAL of {movement_id}: {reason}',
            reference_id=str(movement.id),
            reference_type='adjustment',
        )
        StockMovement.objects.filter(pk=movement_id).update(
            is_reversed=True, reversed_by=reversal,
        )
        return reversal

    # ──────────────────────────────────────────────────────────────
    # Purchase order receipt
    # ──────────────────────────────────────────────────────────────
    @transaction.atomic
    def receive_purchase_order_item(
        self, po_item: PurchaseOrderItem,
        quantity_received: Decimal, unit_cost: Optional[Decimal] = None,
    ) -> StockMovement:
        if quantity_received <= 0:
            raise ValidationError({'quantity_received': 'Must be positive.'})
        unit_cost = unit_cost if unit_cost is not None else po_item.unit_cost
        po_item.quantity_received = (po_item.quantity_received or Decimal('0')) + quantity_received
        po_item.save(update_fields=['quantity_received', 'updated_at'])

        mv = self._create_movement(
            item=po_item.item,
            movement_type=StockMovement.MovementType.PURCHASE,
            quantity=quantity_received,
            unit_cost=unit_cost,
            reference_id=str(po_item.purchase_order_id),
            reference_type='purchase_order',
            notes=f'Received from PO {po_item.purchase_order.order_number}',
        )

        po = po_item.purchase_order
        # Bypass any prefetch_related cache on po.items — query fresh.
        from apps.inventory.models import PurchaseOrderItem as _POI
        sibling_lines = list(_POI.objects.filter(purchase_order=po).values(
            'quantity_ordered', 'quantity_received',
        ))
        total_ordered = sum(
            (li['quantity_ordered'] for li in sibling_lines), Decimal('0'),
        )
        total_received = sum(
            (li['quantity_received'] for li in sibling_lines), Decimal('0'),
        )
        if total_received >= total_ordered:
            po.status = PurchaseOrder.Status.RECEIVED
            po.received_date = date.today()
        elif total_received > 0:
            po.status = PurchaseOrder.Status.PARTIAL
        PurchaseOrder.objects.filter(pk=po.pk).update(
            status=po.status, received_date=po.received_date,
        )
        return mv

    # ──────────────────────────────────────────────────────────────
    # Recipe consumption
    # ──────────────────────────────────────────────────────────────
    @transaction.atomic
    def consume_recipe(self, recipe, batches: Decimal, consumption_type=None) -> dict:
        from .recipe_engine import RecipeEngine
        from apps.inventory.models import ConsumptionLog

        batches = Decimal(batches)
        if batches <= 0:
            raise ValidationError({'batches': 'Must be positive.'})

        calc = RecipeEngine.calculate_batch(recipe, batches)
        if not calc['feasible']:
            raise ValidationError({
                'shortfalls': calc['shortfalls'],
                'message': 'Insufficient stock to complete this recipe.',
            })

        # Phase 4 — 1+1 / promo deduction. A linked MenuPromoRule multiplies
        # the inventory deducted per serve WITHOUT changing the recorded sale.
        # Read via the string-FK relation only — no restaurant import here.
        deduction_multiplier = self._promo_deduction_multiplier(recipe)

        # Default classification: cocktail/drink serves are tagged accordingly,
        # promo-linked consumption is a promo_sale, everything else is manual.
        if consumption_type is None:
            consumption_type = self._default_consumption_type(recipe, deduction_multiplier)

        yield_factor = recipe.yield_percent / Decimal('100')
        movements = []
        logs = []
        # StockMovement.quantity is Decimal(max_digits=10, decimal_places=4).
        # Recipe math (ing.quantity × batches / yield_factor × multiplier) can
        # produce values with more than 4 decimal places when operands carry
        # trailing zeros from DB Decimal storage. Quantize to 4 decimals.
        _Q4 = Decimal('0.0001')
        for ing in recipe.ingredients.filter(is_optional=False).select_related('item'):
            required = (
                (ing.quantity * batches * deduction_multiplier) / yield_factor
            ).quantize(_Q4)
            mv = self._create_movement(
                item=ing.item,
                movement_type=StockMovement.MovementType.RECIPE_CONSUMPTION,
                quantity=-required,
                reference_id=str(recipe.id),
                reference_type='recipe',
                notes=f'Recipe: {recipe.name} × {batches} batch(es)',
            )
            movements.append(mv)
            logs.append(ConsumptionLog(
                organization=self.organization,
                recipe=recipe,
                movement=mv,
                consumption_type=consumption_type,
                quantity_consumed=required,
            ))
        ConsumptionLog.objects.bulk_create(logs)

        if recipe.output_item:
            output_qty = (recipe.output_quantity * batches).quantize(_Q4)
            self._create_movement(
                item=recipe.output_item,
                movement_type=StockMovement.MovementType.PURCHASE,
                quantity=output_qty,
                reference_id=str(recipe.id),
                reference_type='recipe',
                notes=f'Produced by recipe: {recipe.name} × {batches} batch(es)',
            )

        return {
            'movements_created': len(movements),
            'batches': str(batches),
            'recipe_id': str(recipe.id),
            'recipe_version': recipe.version,
            'deduction_multiplier': str(deduction_multiplier),
            'consumption_type': consumption_type,
        }

    @staticmethod
    def _promo_deduction_multiplier(recipe) -> Decimal:
        """Inventory-deduction multiplier from the recipe's linked promo rule
        (1 if none). One-directional read of restaurant data via the FK."""
        rule = getattr(recipe, 'linked_promo_rule', None)
        if rule is None:
            return Decimal('1')
        return Decimal(rule.inventory_deduction_multiplier or 1)

    @staticmethod
    def _default_consumption_type(recipe, deduction_multiplier) -> str:
        from apps.inventory.models import ConsumptionLog
        if recipe.linked_promo_rule_id and deduction_multiplier != Decimal('1'):
            return ConsumptionLog.ConsumptionType.PROMO_SALE
        if recipe.formula_type in ('cocktail_formula', 'drink_formula'):
            return ConsumptionLog.ConsumptionType.COCKTAIL_SERVE
        return ConsumptionLog.ConsumptionType.MANUAL

    # ──────────────────────────────────────────────────────────────
    # Import application
    # ──────────────────────────────────────────────────────────────
    @transaction.atomic
    def apply_sales_import(self, sales_import, parsed_rows: list) -> dict:
        """
        parsed_rows: list of dicts with keys: item (InventoryItem),
        quantity (Decimal, positive), movement_date, unit_cost (optional).
        """
        from apps.inventory.models import SalesImport
        summary = {}
        for row in parsed_rows:
            item = row['item']
            qty = Decimal(row['quantity'])
            mv = self._create_movement(
                item=item,
                movement_type=StockMovement.MovementType.IMPORT_SALE,
                quantity=-qty,
                movement_date=row.get('movement_date') or date.today(),
                unit_cost=row.get('unit_cost'),
                reference_id=str(sales_import.id),
                reference_type='sales_import',
                batch_id=sales_import.batch_id,
                notes=f'Sales import {sales_import.file_name}',
            )
            entry = summary.setdefault(str(item.id), {
                'name': item.name, 'sku': item.sku, 'unit': item.unit,
                'deducted': Decimal('0'),
            })
            entry['deducted'] += qty
        item_ids = list(summary.keys())
        if item_ids:
            for it in InventoryItem.objects.filter(pk__in=item_ids):
                summary[str(it.id)]['new_stock'] = str(it.current_stock)
        for v in summary.values():
            v['deducted'] = str(v['deducted'])
        return summary

    @transaction.atomic
    def apply_purchase_import(self, supplier_import, parsed_rows: list) -> dict:
        summary = {}
        for row in parsed_rows:
            item = row['item']
            qty = Decimal(row['quantity'])
            unit_cost = row.get('unit_cost')
            mv = self._create_movement(
                item=item,
                movement_type=StockMovement.MovementType.IMPORT_PURCHASE,
                quantity=qty,
                movement_date=row.get('movement_date') or date.today(),
                unit_cost=unit_cost,
                reference_id=str(supplier_import.id),
                reference_type='supplier_import',
                batch_id=supplier_import.batch_id,
                notes=f'Purchase import {supplier_import.file_name}',
            )
            entry = summary.setdefault(str(item.id), {
                'name': item.name, 'sku': item.sku, 'unit': item.unit,
                'received': Decimal('0'),
            })
            entry['received'] += qty
        item_ids = list(summary.keys())
        if item_ids:
            for it in InventoryItem.objects.filter(pk__in=item_ids):
                summary[str(it.id)]['new_stock'] = str(it.current_stock)
        for v in summary.values():
            v['received'] = str(v['received'])
        return summary
