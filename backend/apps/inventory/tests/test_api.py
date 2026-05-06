"""End-to-end API tests for inventory ViewSets — POs, Recipes, Imports, AI."""
import io
import csv
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.inventory.models import (
    PurchaseOrder, Recipe, StockMovement, SalesImport, SupplierImport,
    InventoryAuditLog,
)


# ──────────────────────────────────────────────────────────────────────
# Items: immutability
# ──────────────────────────────────────────────────────────────────────
def test_item_unit_change_rejected(auth_owner_client, item):
    res = auth_owner_client.patch(
        f'/api/v1/inventory/items/{item.id}/',
        {'unit': 'g'}, format='json',
    )
    item.refresh_from_db()
    assert item.unit == 'kg'  # unchanged regardless of response code


def test_item_serializer_exposes_locked_fields(auth_owner_client, item):
    res = auth_owner_client.get(f'/api/v1/inventory/items/{item.id}/')
    assert res.status_code == 200
    data = res.json()
    assert 'sku' in data['locked_fields']
    assert 'unit' in data['locked_fields']


def test_item_effective_stock_endpoint(auth_owner_client, item):
    StockMovement.objects.create(
        organization=item.organization, item=item,
        movement_type=StockMovement.MovementType.PURCHASE,
        quantity=Decimal('100'),
    )
    res = auth_owner_client.get(f'/api/v1/inventory/items/{item.id}/effective-stock/')
    assert res.status_code == 200
    body = res.json()
    for k in ('raw', 'reported', 'lower_bound', 'upper_bound', 'tolerance_percent'):
        assert k in body


def test_item_adjust_writes_movement_and_audit_log(auth_owner_client, item):
    res = auth_owner_client.post(
        f'/api/v1/inventory/items/{item.id}/adjust/',
        {'quantity': '15', 'reason': 'Initial physical count'},
        format='json',
    )
    assert res.status_code == 200, res.content
    item.refresh_from_db()
    assert item.current_stock == Decimal('15')
    assert InventoryAuditLog.objects.filter(
        action='adjust', object_id=item.id,
    ).exists()


# ──────────────────────────────────────────────────────────────────────
# Suppliers
# ──────────────────────────────────────────────────────────────────────
def test_supplier_tax_id_immutable_after_po(auth_owner_client, supplier, purchase_order):
    res = auth_owner_client.patch(
        f'/api/v1/inventory/suppliers/{supplier.id}/',
        {'tax_id': 'TAX-CHANGED'}, format='json',
    )
    assert res.status_code == 400


# ──────────────────────────────────────────────────────────────────────
# Purchase Orders
# ──────────────────────────────────────────────────────────────────────
def test_create_purchase_order(auth_owner_client, org, supplier, item):
    res = auth_owner_client.post('/api/v1/inventory/purchase-orders/', {
        'organization': str(org.id),
        'supplier': str(supplier.id),
        'items': [{
            'item': str(item.id),
            'quantity_ordered': '20',
            'unit_cost': '2.5',
        }],
    }, format='json')
    assert res.status_code in (200, 201), res.content
    body = res.json()
    assert body['order_number'].startswith('PO-')
    assert Decimal(body['total_amount']) == Decimal('50.00')


def test_receive_purchase_order_creates_stock(auth_owner_client, purchase_order):
    line = purchase_order.items.first()
    res = auth_owner_client.post(
        f'/api/v1/inventory/purchase-orders/{purchase_order.id}/receive/',
        {'line_id': str(line.id), 'quantity_received': '20'},
        format='json',
    )
    assert res.status_code == 200, res.content
    purchase_order.refresh_from_db()
    assert purchase_order.status == PurchaseOrder.Status.RECEIVED


def test_cancel_purchase_order(auth_owner_client, purchase_order):
    res = auth_owner_client.post(
        f'/api/v1/inventory/purchase-orders/{purchase_order.id}/cancel/'
    )
    assert res.status_code == 200
    purchase_order.refresh_from_db()
    assert purchase_order.status == PurchaseOrder.Status.CANCELLED


# ──────────────────────────────────────────────────────────────────────
# Recipes
# ──────────────────────────────────────────────────────────────────────
def test_create_recipe(auth_owner_client, org, item, output_item):
    res = auth_owner_client.post('/api/v1/inventory/recipes/', {
        'organization': str(org.id),
        'name': 'Salad',
        'output_item': str(output_item.id),
        'output_quantity': '1',
        'yield_percent': '100',
        'ingredients': [{
            'item': str(item.id),
            'quantity': '0.5',
            'unit': item.unit,
        }],
    }, format='json')
    assert res.status_code in (200, 201), res.content
    body = res.json()
    assert body['name'] == 'Salad'
    assert len(body['ingredients']) == 1


def test_recipe_calculate_returns_feasibility(auth_owner_client, recipe):
    res = auth_owner_client.post(
        f'/api/v1/inventory/recipes/{recipe.id}/calculate/',
        {'batches': '5'}, format='json',
    )
    assert res.status_code == 200
    body = res.json()
    assert 'feasible' in body
    assert 'shortfalls' in body
    assert 'ingredients' in body


def test_recipe_consume_blocked_when_short(auth_owner_client, recipe):
    res = auth_owner_client.post(
        f'/api/v1/inventory/recipes/{recipe.id}/consume/',
        {'batches': '100'}, format='json',
    )
    assert res.status_code == 422


def test_recipe_versions_endpoint(auth_owner_client, recipe):
    res = auth_owner_client.get(f'/api/v1/inventory/recipes/{recipe.id}/versions/')
    assert res.status_code == 200
    assert isinstance(res.json(), list)


# ──────────────────────────────────────────────────────────────────────
# Movements: reverse
# ──────────────────────────────────────────────────────────────────────
def test_reverse_movement_endpoint(auth_owner_client, org, item, owner):
    mv = StockMovement.objects.create(
        organization=org, item=item,
        movement_type=StockMovement.MovementType.PURCHASE,
        quantity=Decimal('25'),
    )
    res = auth_owner_client.post(
        f'/api/v1/inventory/movements/{mv.id}/reverse/',
        {'reason': 'Mistakenly entered receipt'}, format='json',
    )
    assert res.status_code == 200, res.content
    mv.refresh_from_db()
    assert mv.is_reversed is True


def test_reverse_movement_short_reason_rejected(auth_owner_client, org, item):
    mv = StockMovement.objects.create(
        organization=org, item=item,
        movement_type=StockMovement.MovementType.PURCHASE,
        quantity=Decimal('25'),
    )
    res = auth_owner_client.post(
        f'/api/v1/inventory/movements/{mv.id}/reverse/',
        {'reason': 'no'}, format='json',
    )
    assert res.status_code == 400


# ──────────────────────────────────────────────────────────────────────
# Imports
# ──────────────────────────────────────────────────────────────────────
def _make_csv(rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    for row in rows:
        w.writerow(row)
    data = buf.getvalue().encode('utf-8')
    return data


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_sales_import_upload_creates_pending(auth_owner_client, org, item):
    from django.core.files.uploadedfile import SimpleUploadedFile
    csv_bytes = _make_csv([
        ['Item', 'Qty', 'Date'],
        [item.name, '5', '2026-05-01'],
    ])
    f = SimpleUploadedFile('sales.csv', csv_bytes, content_type='text/csv')
    res = auth_owner_client.post(
        '/api/v1/inventory/imports/sales/',
        {'import_file': f}, format='multipart',
    )
    assert res.status_code in (200, 201), res.content
    body = res.json()
    assert body['status'] == 'pending'
    assert body['row_count'] == 1


def test_import_rejects_unsupported_extension(auth_owner_client):
    from django.core.files.uploadedfile import SimpleUploadedFile
    f = SimpleUploadedFile('x.txt', b'hello', content_type='text/plain')
    res = auth_owner_client.post(
        '/api/v1/inventory/imports/sales/',
        {'import_file': f}, format='multipart',
    )
    assert res.status_code == 400


# ──────────────────────────────────────────────────────────────────────
# Reports
# ──────────────────────────────────────────────────────────────────────
def test_stock_health_report(auth_owner_client, item):
    StockMovement.objects.create(
        organization=item.organization, item=item,
        movement_type=StockMovement.MovementType.PURCHASE,
        quantity=Decimal('50'),
    )
    res = auth_owner_client.get('/api/v1/inventory/reports/stock-health/')
    assert res.status_code == 200
    body = res.json()
    assert 'totals' in body
    assert 'item_count' in body


def test_movement_timeline_report(auth_owner_client, item):
    StockMovement.objects.create(
        organization=item.organization, item=item,
        movement_type=StockMovement.MovementType.PURCHASE,
        quantity=Decimal('10'),
    )
    res = auth_owner_client.get('/api/v1/inventory/reports/movement-timeline/?days=14')
    assert res.status_code == 200
    body = res.json()
    assert 'series' in body


# ──────────────────────────────────────────────────────────────────────
# AI endpoint
# ──────────────────────────────────────────────────────────────────────
def test_ai_query_without_openai_key_degrades_gracefully(auth_owner_client, org, item, settings):
    settings.OPENAI_API_KEY = ''
    # Power plan required for AI endpoint.
    org.plan = 'power'
    org.save(update_fields=['plan'])
    res = auth_owner_client.post(
        '/api/v1/inventory/ai/query/',
        {'question': 'How much tomato do we have?'}, format='json',
    )
    assert res.status_code == 200, res.content
    body = res.json()
    assert 'answer' in body
    assert body['confidence'] == 0.0


def test_ai_query_blocked_for_basic_plan(auth_owner_client, org):
    org.plan = 'basic'
    org.save(update_fields=['plan'])
    res = auth_owner_client.post(
        '/api/v1/inventory/ai/query/',
        {'question': 'anything'}, format='json',
    )
    assert res.status_code == 403


# ──────────────────────────────────────────────────────────────────────
# Cross-org isolation
# ──────────────────────────────────────────────────────────────────────
def test_cross_org_item_access_returns_404(api_client, owner_b, item):
    api_client.force_authenticate(user=owner_b)
    res = api_client.get(f'/api/v1/inventory/items/{item.id}/')
    # not 403 — should 404 to avoid leaking existence
    assert res.status_code == 404
