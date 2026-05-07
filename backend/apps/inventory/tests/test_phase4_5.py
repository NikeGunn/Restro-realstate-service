"""
Phase 4 + 5 API and service tests.

Covers:
  - Movement CSV export
  - Bulk item edit (whitelist + audit-log per item)
  - Stock-take create / commit (variance → adjustment movements)
  - Per-location pricing CRUD
  - PO send (DRAFT → SENT, email persisted)
  - PO PDF endpoint
  - Phase 5 reports: reorder-forecast, supplier-scorecards,
    recipe-profitability, waste-analysis, weekly-insights
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Location
from apps.inventory.models import (
    InventoryItem, InventoryAuditLog, LocationItemPricing,
    PurchaseOrder, PurchaseOrderItem, StockMovement, StockTake, StockTakeLine,
)


@pytest.fixture
def location_a(db, org):
    return Location.objects.create(organization=org, name='Branch A')


# ──────────────────────────────────────────────────────────────────────
# Movement export
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestMovementExport:
    def test_csv_export_includes_header_and_rows(
        self, auth_owner_client, org, item, owner,
    ):
        from apps.inventory.services.stock_engine import StockEngine
        engine = StockEngine(organization=org, performed_by=owner)
        engine._create_movement(
            item=item, movement_type=StockMovement.MovementType.PURCHASE,
            quantity=Decimal('25'),
        )
        url = '/api/v1/inventory/movements/export/'
        resp = auth_owner_client.get(url)
        assert resp.status_code == 200
        assert resp['Content-Type'].startswith('text/csv')
        body = resp.content.decode('utf-8')
        assert 'item_sku' in body
        assert item.name in body


# ──────────────────────────────────────────────────────────────────────
# Bulk edit
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestBulkItemEdit:
    def test_bulk_update_changes_fields_and_audits(
        self, auth_owner_client, org, item, item_b, owner,
    ):
        url = '/api/v1/inventory/items/bulk-update/'
        resp = auth_owner_client.post(url, {
            'ids': [str(item.id), str(item_b.id)],
            'patch': {'reorder_level': '99', 'is_active': False},
        }, format='json')
        assert resp.status_code == 200, resp.content
        assert resp.data['updated'] == 2

        item.refresh_from_db()
        item_b.refresh_from_db()
        assert item.reorder_level == Decimal('99')
        assert item.is_active is False

        # One audit-log row per item.
        bulk_logs = InventoryAuditLog.objects.filter(
            action='bulk_update', model_name='InventoryItem',
        )
        assert bulk_logs.count() == 2

    def test_bulk_update_rejects_non_whitelisted_field(
        self, auth_owner_client, item,
    ):
        url = '/api/v1/inventory/items/bulk-update/'
        resp = auth_owner_client.post(url, {
            'ids': [str(item.id)],
            'patch': {'unit': 'liter'},
        }, format='json')
        assert resp.status_code == 400


# ──────────────────────────────────────────────────────────────────────
# Stock-take
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestStockTake:
    def test_commit_emits_adjustment_movements_for_variances(
        self, auth_owner_client, org, item, item_b, owner, location_a,
    ):
        # Seed initial stock so system_count != 0.
        from apps.inventory.services.stock_engine import StockEngine
        engine = StockEngine(organization=org, location=location_a, performed_by=owner)
        engine._create_movement(
            item=item, movement_type=StockMovement.MovementType.PURCHASE,
            quantity=Decimal('10'),
        )
        engine._create_movement(
            item=item_b, movement_type=StockMovement.MovementType.PURCHASE,
            quantity=Decimal('5'),
        )

        # Create stock-take.
        st = StockTake.objects.create(
            organization=org, location=location_a, created_by=owner,
        )
        StockTakeLine.objects.create(
            stock_take=st, item=item, system_count=Decimal('10'),
            counted=Decimal('8'),  # variance -2
        )
        StockTakeLine.objects.create(
            stock_take=st, item=item_b, system_count=Decimal('5'),
            counted=Decimal('5'),  # no variance
        )

        url = f'/api/v1/inventory/stock-takes/{st.id}/commit/'
        resp = auth_owner_client.post(url, {}, format='json')
        assert resp.status_code == 200, resp.content
        assert resp.data['result']['adjustments_created'] == 1

        st.refresh_from_db()
        assert st.status == StockTake.Status.COMMITTED

        # Item stock should now be 8 (10 + (-2) adjustment).
        item.refresh_from_db()
        assert item.current_stock == Decimal('8')
        item_b.refresh_from_db()
        assert item_b.current_stock == Decimal('5')


# ──────────────────────────────────────────────────────────────────────
# Per-location pricing
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestLocationItemPricing:
    def test_create_and_list(self, auth_owner_client, item, location_a):
        url = '/api/v1/inventory/location-pricing/'
        resp = auth_owner_client.post(url, {
            'item': str(item.id), 'location': str(location_a.id),
            'unit_cost': '3.5', 'selling_price': '7.0',
        }, format='json')
        assert resp.status_code == 201, resp.content
        assert LocationItemPricing.objects.count() == 1

        list_resp = auth_owner_client.get(url)
        assert list_resp.status_code == 200
        results = list_resp.data['results'] if 'results' in list_resp.data else list_resp.data
        assert len(results) == 1


# ──────────────────────────────────────────────────────────────────────
# Purchase order send + PDF
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestPurchaseOrderSend:
    def test_send_moves_status_to_sent_and_records_email(
        self, auth_owner_client, purchase_order, supplier, settings,
    ):
        # Use locmem email backend so it doesn't actually send.
        settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
        supplier.email = 'supplier@test.test'
        supplier.save()
        url = f'/api/v1/inventory/purchase-orders/{purchase_order.id}/send/'
        resp = auth_owner_client.post(url, {}, format='json')
        assert resp.status_code == 200, resp.content
        po = resp.data['po']
        assert po['status'] == PurchaseOrder.Status.SENT
        assert po['sent_to_email'] == 'supplier@test.test'
        assert resp.data['email']['sent_at'] is not None

    def test_send_rejects_when_no_email(
        self, auth_owner_client, purchase_order, supplier,
    ):
        supplier.email = ''
        supplier.save()
        url = f'/api/v1/inventory/purchase-orders/{purchase_order.id}/send/'
        resp = auth_owner_client.post(url, {}, format='json')
        assert resp.status_code == 400

    def test_pdf_endpoint_returns_attachment(self, auth_owner_client, purchase_order):
        url = f'/api/v1/inventory/purchase-orders/{purchase_order.id}/pdf/'
        resp = auth_owner_client.get(url)
        assert resp.status_code == 200
        assert 'attachment' in resp['Content-Disposition']
        assert len(resp.content) > 0


# ──────────────────────────────────────────────────────────────────────
# Phase 5 reports
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestPhase5Reports:
    def test_reorder_forecast(self, auth_owner_client, org, item, owner):
        from apps.inventory.services.stock_engine import StockEngine
        engine = StockEngine(organization=org, performed_by=owner)
        # Seed in + recent consumption.
        engine._create_movement(
            item=item, movement_type=StockMovement.MovementType.PURCHASE,
            quantity=Decimal('50'),
        )
        engine._create_movement(
            item=item, movement_type=StockMovement.MovementType.SALE,
            quantity=Decimal('-7'),
        )
        url = '/api/v1/inventory/reports/reorder-forecast/?days=30'
        resp = auth_owner_client.get(url)
        assert resp.status_code == 200
        rows = resp.data['rows']
        assert any(r['item_id'] == str(item.id) for r in rows)
        row = next(r for r in rows if r['item_id'] == str(item.id))
        assert Decimal(row['avg_daily_consumption']) > 0

    def test_supplier_scorecards(self, auth_owner_client, supplier, purchase_order):
        url = '/api/v1/inventory/reports/supplier-scorecards/'
        resp = auth_owner_client.get(url)
        assert resp.status_code == 200
        rows = resp.data
        assert any(r['supplier_id'] == str(supplier.id) for r in rows)

    def test_recipe_profitability(self, auth_owner_client, recipe, output_item):
        # output_item has selling_price=None by default; set it.
        output_item.selling_price = Decimal('10.0')
        output_item.save()
        url = '/api/v1/inventory/reports/recipe-profitability/'
        resp = auth_owner_client.get(url)
        assert resp.status_code == 200
        assert any(r['recipe_id'] == str(recipe.id) for r in resp.data)

    def test_waste_analysis(self, auth_owner_client, org, item, owner):
        from apps.inventory.services.stock_engine import StockEngine
        engine = StockEngine(organization=org, performed_by=owner)
        engine._create_movement(
            item=item, movement_type=StockMovement.MovementType.PURCHASE,
            quantity=Decimal('20'),
        )
        engine._create_movement(
            item=item, movement_type=StockMovement.MovementType.WASTE,
            quantity=Decimal('-3'),
        )
        url = '/api/v1/inventory/reports/waste-analysis/?days=30'
        resp = auth_owner_client.get(url)
        assert resp.status_code == 200
        assert any(t['item_id'] == str(item.id) for t in resp.data['top_items'])

    def test_weekly_insights_falls_back_without_openai(
        self, auth_owner_client, org, item, owner, settings,
    ):
        settings.OPENAI_API_KEY = ''
        url = '/api/v1/inventory/reports/weekly-insights/'
        resp = auth_owner_client.get(url)
        assert resp.status_code == 200
        # Without OpenAI we still get a deterministic digest, conf=1.0.
        assert resp.data['confidence'] == 1.0
        assert 'Reorder candidates' in resp.data['answer']
