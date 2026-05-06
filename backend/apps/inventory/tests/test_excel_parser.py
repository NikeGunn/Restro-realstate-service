"""ExcelParser tests — column detection, validation, item resolution."""
import csv
import os
import tempfile
from decimal import Decimal

import pytest

from apps.inventory.services.excel_parser import (
    ExcelParser, COLUMN_SYNONYMS, _to_decimal, _parse_date,
)


def _csv(rows):
    f = tempfile.NamedTemporaryFile(
        suffix='.csv', delete=False, mode='w', newline='', encoding='utf-8',
    )
    w = csv.writer(f)
    for row in rows:
        w.writerow(row)
    f.close()
    return f.name


def test_detect_columns_with_synonyms(org):
    p = ExcelParser('/dev/null', 'sales', org)
    cols = p.detect_columns(['Item Name', 'Qty', 'Date', 'Price'])
    assert 'name' in cols
    assert 'quantity' in cols
    assert 'movement_date' in cols
    assert 'unit_cost' in cols


def test_detect_columns_fuzzy_match(org):
    p = ExcelParser('/dev/null', 'sales', org)
    cols = p.detect_columns(['products', 'amounts', 'transaction_dates'])
    assert 'name' in cols
    assert 'quantity' in cols
    assert 'movement_date' in cols


def test_to_decimal_handles_commas():
    assert _to_decimal('1,234.50') == Decimal('1234.50')
    assert _to_decimal('') == Decimal('0')
    assert _to_decimal(None) == Decimal('0')
    assert _to_decimal('not-a-number') == Decimal('0')


def test_parse_date_multiple_formats():
    assert _parse_date('2026-05-07') is not None
    assert _parse_date('07/05/2026') is not None
    assert _parse_date('5/7/2026') is not None
    assert _parse_date('not-a-date') is None


def test_parse_sales_csv_classifies_valid_and_error_rows(org, item):
    path = _csv([
        ['Item', 'Qty', 'Date'],
        [item.name, '5', '2026-05-01'],   # valid
        ['Unknown thing', '0', '2026-05-02'],  # invalid: qty
        [item.name, '3', ''],              # invalid: missing date
    ])
    try:
        p = ExcelParser(path, 'sales', org)
        out = p.parse()
        assert out['total_rows'] == 3
        assert out['valid_rows'] == 1
        assert out['error_rows'] == 2
    finally:
        os.unlink(path)


def test_parse_purchase_requires_unit_cost(org):
    path = _csv([
        ['Item', 'Qty', 'Unit Cost'],
        ['Tomato', '5', '2.0'],   # valid
        ['Tomato', '5', ''],       # invalid: missing cost
    ])
    try:
        p = ExcelParser(path, 'purchase', org)
        out = p.parse()
        assert out['valid_rows'] == 1
        assert out['error_rows'] == 1
    finally:
        os.unlink(path)


def test_resolve_item_by_sku(org, item):
    p = ExcelParser('/dev/null', 'sales', org)
    resolved = p.resolve_item({'sku': item.sku, 'name': ''})
    assert resolved is not None
    assert resolved.id == item.id


def test_resolve_item_by_fuzzy_name(org, item):
    p = ExcelParser('/dev/null', 'sales', org)
    resolved = p.resolve_item({'sku': '', 'name': 'Tomato'})
    assert resolved is not None
    assert resolved.id == item.id


def test_resolve_item_returns_none_when_no_match(org):
    p = ExcelParser('/dev/null', 'sales', org)
    assert p.resolve_item({'sku': '', 'name': 'No such item'}) is None


def test_unsupported_extension_raises(org):
    f = tempfile.NamedTemporaryFile(suffix='.txt', delete=False)
    f.close()
    try:
        with pytest.raises(ValueError):
            ExcelParser(f.name, 'sales', org).parse()
    finally:
        os.unlink(f.name)
