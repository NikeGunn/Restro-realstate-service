"""Pure-arithmetic tests for ToleranceEngine — no DB required."""
from decimal import Decimal

from apps.inventory.services.tolerance_engine import ToleranceEngine


def test_effective_stock_basic():
    es = ToleranceEngine.effective_stock(
        Decimal('100'), Decimal('20'), Decimal('0.5'),
    )
    assert es.raw == Decimal('100')
    assert es.reported == Decimal('100.00')
    assert es.lower_bound == Decimal('99.5000')
    assert es.upper_bound == Decimal('100.5000')
    assert es.is_critical is False
    assert es.is_negative is False


def test_effective_stock_marks_critical():
    es = ToleranceEngine.effective_stock(
        Decimal('5'), Decimal('10'), Decimal('0.5'),
    )
    assert es.is_critical is True


def test_effective_stock_marks_negative():
    es = ToleranceEngine.effective_stock(
        Decimal('-3'), Decimal('5'), Decimal('0.5'),
    )
    assert es.is_negative is True
    assert es.is_critical is True


def test_recipe_feasibility_passes_when_tolerance_covers_small_shortfall():
    """1% tolerance on 100 → lower_bound=99 → required 98.5 is feasible."""
    fs = ToleranceEngine.check_recipe_feasibility([{
        'item_id': 'x', 'item_name': 'X',
        'raw_stock': Decimal('100'), 'reorder_level': Decimal('5'),
        'tolerance_percent': Decimal('1.0'),
        'quantity_required': Decimal('98.5'), 'unit_cost': Decimal('1'),
    }])
    assert fs.feasible is True
    assert fs.shortfalls == []


def test_recipe_feasibility_flags_shortfall():
    fs = ToleranceEngine.check_recipe_feasibility([{
        'item_id': 'x', 'item_name': 'X',
        'raw_stock': Decimal('5'), 'reorder_level': Decimal('1'),
        'tolerance_percent': Decimal('0.5'),
        'quantity_required': Decimal('10'), 'unit_cost': Decimal('1'),
    }])
    assert fs.feasible is False
    assert len(fs.shortfalls) == 1
    assert fs.shortfalls[0]['item_id'] == 'x'


def test_recipe_feasibility_warns_on_post_deduction_below_reorder():
    fs = ToleranceEngine.check_recipe_feasibility([{
        'item_id': 'x', 'item_name': 'X',
        'raw_stock': Decimal('15'), 'reorder_level': Decimal('10'),
        'tolerance_percent': Decimal('0.5'),
        'quantity_required': Decimal('8'), 'unit_cost': Decimal('1'),
    }])
    assert fs.feasible is True
    assert len(fs.warnings) == 1


def test_recipe_feasibility_total_cost():
    fs = ToleranceEngine.check_recipe_feasibility([
        {'item_id': 'a', 'item_name': 'A', 'raw_stock': Decimal('100'),
         'reorder_level': Decimal('1'), 'tolerance_percent': Decimal('0'),
         'quantity_required': Decimal('2'), 'unit_cost': Decimal('3')},
        {'item_id': 'b', 'item_name': 'B', 'raw_stock': Decimal('100'),
         'reorder_level': Decimal('1'), 'tolerance_percent': Decimal('0'),
         'quantity_required': Decimal('5'), 'unit_cost': Decimal('1')},
    ])
    assert fs.total_cost == Decimal('11.0000')
