"""
RecipeEngine
============
Read-only calculations for recipes. Mutations live in StockEngine.consume_recipe.
"""
from decimal import Decimal

from .tolerance_engine import ToleranceEngine


class RecipeEngine:

    @staticmethod
    def calculate_batch(recipe, batches: Decimal) -> dict:
        batches = Decimal(batches)
        yield_factor = recipe.yield_percent / Decimal('100')
        # Movements persisted by StockEngine.consume_recipe are constrained
        # to 4 decimal places, so we quantize calculated quantities the
        # same way for both display and feasibility math.
        _Q4 = Decimal('0.0001')
        # For drink/cocktail formulas the recipe's pour variance overrides each
        # item's own tolerance (resolved once per recipe — DRY).
        effective_variance = recipe.resolved_pour_variance_percent()
        ingredients_data = []
        for ing in recipe.ingredients.select_related('item').filter(is_optional=False):
            required = ((ing.quantity * batches) / yield_factor).quantize(_Q4)
            item = ing.item
            item.refresh_from_db(fields=['current_stock', 'tolerance_percent', 'reorder_level', 'unit_cost'])
            es = ToleranceEngine.effective_stock_with_pour_variance(
                item.current_stock, item.reorder_level, item.tolerance_percent,
                formula_type=recipe.formula_type,
                pour_variance_percent=effective_variance,
            )
            tolerance_applied = ToleranceEngine.resolve_tolerance(
                item.tolerance_percent, recipe.formula_type, effective_variance,
            )
            ingredients_data.append({
                'item_id': str(item.id),
                'item_name': item.name,
                'unit': ing.unit,
                'required_quantity': str(required),
                'available_raw': str(es.raw),
                'available_reported': str(es.reported),
                'lower_bound': str(es.lower_bound),
                'upper_bound': str(es.upper_bound),
                'shortfall': str(max(required - es.raw, Decimal('0'))),
                # echoed back for the feasibility helper
                'raw_stock': es.raw,
                'reorder_level': item.reorder_level,
                # Feasibility uses the SAME tolerance the band was built with
                # (pour variance for drinks/cocktails, item tolerance otherwise).
                'tolerance_percent': tolerance_applied,
                'quantity_required': required,
                'unit_cost': item.unit_cost,
            })
        feasibility = ToleranceEngine.check_recipe_feasibility(ingredients_data)
        output_qty = (
            (recipe.output_quantity * batches).quantize(_Q4)
            if recipe.output_item else None
        )

        # Strip raw Decimals from the response payload
        for ing in ingredients_data:
            for k in ('raw_stock', 'reorder_level', 'tolerance_percent',
                      'quantity_required', 'unit_cost'):
                if k in ing:
                    ing[k] = str(ing[k])

        return {
            'recipe_id': str(recipe.id),
            'recipe_name': recipe.name,
            'version': recipe.version,
            'batches': str(batches),
            'yield_percent': str(recipe.yield_percent),
            'output_quantity': str(output_qty) if output_qty else None,
            'output_item': recipe.output_item.name if recipe.output_item else None,
            'feasible': feasibility.feasible,
            'shortfalls': feasibility.shortfalls,
            'warnings': feasibility.warnings,
            'estimated_cost': str(feasibility.total_cost),
            'cost_per_output': (
                str((feasibility.total_cost / output_qty).quantize(Decimal('0.0001')))
                if output_qty and output_qty > 0 else None
            ),
            'ingredients': ingredients_data,
        }

    @staticmethod
    def suggest_batches(recipe) -> Decimal:
        max_batches = None
        yield_factor = recipe.yield_percent / Decimal('100')
        for ing in recipe.ingredients.select_related('item').filter(is_optional=False):
            item = ing.item
            item.refresh_from_db(fields=['current_stock', 'tolerance_percent'])
            effective_lower = item.current_stock * (
                Decimal('1') - item.tolerance_percent / Decimal('100')
            )
            if ing.quantity <= 0:
                continue
            per_batch = ing.quantity / yield_factor
            if per_batch <= 0:
                continue
            possible = effective_lower / per_batch
            if max_batches is None or possible < max_batches:
                max_batches = possible
        if max_batches is None:
            return Decimal('0')
        return max(max_batches.quantize(Decimal('0.01')), Decimal('0'))

    @staticmethod
    def cost_of_batch(recipe, batches: Decimal) -> Decimal:
        total = Decimal('0')
        yield_factor = recipe.yield_percent / Decimal('100')
        for ing in recipe.ingredients.select_related('item').filter(is_optional=False):
            required = (ing.quantity * Decimal(batches)) / yield_factor
            total += required * ing.item.unit_cost
        return total.quantize(Decimal('0.0001'))

    @staticmethod
    def version_diff(recipe, v1: int, v2: int) -> dict:
        rv1 = recipe.versions.filter(version_number=v1).first()
        rv2 = recipe.versions.filter(version_number=v2).first()
        if not rv1 or not rv2:
            raise ValueError(f'Version {v1} or {v2} not found for recipe {recipe.id}')
        ings1 = {i['item_id']: i for i in rv1.snapshot.get('ingredients', [])}
        ings2 = {i['item_id']: i for i in rv2.snapshot.get('ingredients', [])}
        added = [ings2[k] for k in ings2 if k not in ings1]
        removed = [ings1[k] for k in ings1 if k not in ings2]
        changed = []
        for k in ings1:
            if k in ings2 and ings1[k] != ings2[k]:
                changed.append({'before': ings1[k], 'after': ings2[k]})
        return {'added': added, 'removed': removed, 'changed': changed, 'v1': v1, 'v2': v2}
