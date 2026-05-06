"""
ToleranceEngine
===============
Pure-arithmetic helper. Zero Django imports at module level so this is
unit-testable without a database. Every API response that surfaces stock
quantities should pass through this engine.
"""
from dataclasses import dataclass, asdict
from decimal import Decimal, ROUND_HALF_UP


@dataclass
class EffectiveStock:
    raw: Decimal
    reported: Decimal
    lower_bound: Decimal
    upper_bound: Decimal
    tolerance_percent: Decimal
    is_critical: bool
    is_negative: bool
    within_tolerance: bool

    def to_dict(self):
        d = asdict(self)
        # JSON-friendly stringification of Decimals.
        for k, v in d.items():
            if isinstance(v, Decimal):
                d[k] = str(v)
        return d


@dataclass
class RecipeFeasibility:
    feasible: bool
    shortfalls: list
    warnings: list
    total_cost: Decimal


def _q4(v: Decimal) -> Decimal:
    return v.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)


def _q2(v: Decimal) -> Decimal:
    return v.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class ToleranceEngine:

    @staticmethod
    def effective_stock(
        raw_stock: Decimal,
        reorder_level: Decimal,
        tolerance_percent: Decimal,
    ) -> EffectiveStock:
        raw_stock = Decimal(raw_stock)
        reorder_level = Decimal(reorder_level)
        tolerance_percent = Decimal(tolerance_percent)
        t = tolerance_percent / Decimal('100')
        return EffectiveStock(
            raw=raw_stock,
            reported=_q2(raw_stock),
            lower_bound=_q4(raw_stock * (Decimal('1') - t)),
            upper_bound=_q4(raw_stock * (Decimal('1') + t)),
            tolerance_percent=tolerance_percent,
            is_critical=raw_stock < reorder_level,
            is_negative=raw_stock < Decimal('0'),
            within_tolerance=True,
        )

    @staticmethod
    def check_recipe_feasibility(ingredients: list) -> RecipeFeasibility:
        """
        ingredients: list of dicts with keys
            item_id, item_name, raw_stock, reorder_level,
            tolerance_percent, quantity_required, unit_cost.
        """
        shortfalls = []
        warnings = []
        total_cost = Decimal('0')

        for ing in ingredients:
            raw = Decimal(ing['raw_stock'])
            tol = Decimal(ing['tolerance_percent']) / Decimal('100')
            required = Decimal(ing['quantity_required'])
            reorder = Decimal(ing.get('reorder_level', 0))
            unit_cost = Decimal(ing.get('unit_cost', 0))

            effective_lower = raw * (Decimal('1') - tol)
            if effective_lower < required:
                shortfalls.append({
                    'item_id': str(ing['item_id']),
                    'item_name': ing['item_name'],
                    'required': str(_q4(required)),
                    'available': str(_q4(raw)),
                    'shortfall': str(_q4(max(required - effective_lower, Decimal('0')))),
                })
            post_deduction = raw - required
            if Decimal('0') <= post_deduction < reorder:
                warnings.append({
                    'item_id': str(ing['item_id']),
                    'item_name': ing['item_name'],
                    'post_deduction_stock': str(_q4(post_deduction)),
                    'reorder_level': str(_q4(reorder)),
                    'message': 'Stock will drop below reorder level after this operation.',
                })
            total_cost += unit_cost * required

        return RecipeFeasibility(
            feasible=len(shortfalls) == 0,
            shortfalls=shortfalls,
            warnings=warnings,
            total_cost=_q4(total_cost),
        )
