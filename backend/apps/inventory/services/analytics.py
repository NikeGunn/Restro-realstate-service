"""
Phase 5 analytics services.

All read-only computations on top of the StockMovement ledger and PO/Recipe
data. No new mutating surfaces. Each function returns plain dicts/lists so
the views can return them without further serialization gymnastics.
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum, Count, F, Avg
from django.utils import timezone

from apps.inventory.models import (
    InventoryItem, StockMovement, PurchaseOrder, PurchaseOrderItem,
    Recipe, Supplier,
)


# ──────────────────────────────────────────────────────────────────────
# Reorder forecast
# ──────────────────────────────────────────────────────────────────────
def reorder_forecast(org_ids: list, *, days: int = 30) -> list:
    """
    For each active item: average daily consumption over the last `days`,
    project days-of-cover, flag when reorder is recommended.
    """
    cutoff = timezone.now().date() - timedelta(days=days)
    items = list(
        InventoryItem.objects.filter(
            organization_id__in=org_ids, is_active=True,
        ).values(
            'id', 'name', 'sku', 'unit', 'current_stock',
            'reorder_level', 'reorder_quantity',
        )
    )
    by_id = {str(it['id']): it for it in items}

    consumed = (
        StockMovement.objects
        .filter(
            organization_id__in=org_ids,
            movement_date__gte=cutoff,
            is_reversed=False,
            quantity__lt=0,
        )
        .values('item_id')
        .annotate(total_out=Sum('quantity'))
    )

    out = []
    for row in consumed:
        item = by_id.get(str(row['item_id']))
        if not item:
            continue
        total_out = -(row['total_out'] or Decimal('0'))
        avg_daily = (total_out / Decimal(days)).quantize(Decimal('0.0001'))
        cs = item['current_stock'] or Decimal('0')
        days_cover = (
            (cs / avg_daily).quantize(Decimal('0.1')) if avg_daily > 0 else None
        )
        recommend = (
            avg_daily > 0 and item['reorder_level'] > 0
            and cs <= item['reorder_level']
        )
        out.append({
            'item_id': str(item['id']),
            'item_name': item['name'],
            'sku': item['sku'],
            'unit': item['unit'],
            'current_stock': str(cs),
            'avg_daily_consumption': str(avg_daily),
            'days_of_cover': str(days_cover) if days_cover is not None else None,
            'reorder_level': str(item['reorder_level']),
            'reorder_quantity': str(item['reorder_quantity']),
            'recommended_to_reorder': recommend,
        })

    # Sort: items with non-null days_of_cover ascending (most urgent first),
    # then items without consumption history at the bottom.
    def _sort_key(r):
        d = r['days_of_cover']
        return (0 if d is not None else 1, Decimal(d) if d is not None else Decimal('0'))
    out.sort(key=_sort_key)
    return out


# ──────────────────────────────────────────────────────────────────────
# Supplier scorecards
# ──────────────────────────────────────────────────────────────────────
def supplier_scorecards(org_ids: list) -> list:
    """
    Per-supplier: avg lead time (days from order_date → received_date),
    receive accuracy (sum received / sum ordered across all PO lines),
    PO count, total spend.
    """
    out = []
    suppliers = Supplier.objects.filter(organization_id__in=org_ids, is_active=True)
    for sup in suppliers:
        pos = PurchaseOrder.objects.filter(supplier=sup)
        po_count = pos.count()

        # Lead time only for received POs.
        received = pos.filter(
            status=PurchaseOrder.Status.RECEIVED,
            received_date__isnull=False,
            order_date__isnull=False,
        )
        leads = [
            (po.received_date - po.order_date).days
            for po in received if po.received_date and po.order_date
        ]
        avg_lead = sum(leads) / len(leads) if leads else None

        # Accuracy.
        lines = PurchaseOrderItem.objects.filter(purchase_order__supplier=sup)
        ordered = lines.aggregate(s=Sum('quantity_ordered'))['s'] or Decimal('0')
        recvd = lines.aggregate(s=Sum('quantity_received'))['s'] or Decimal('0')
        accuracy = (
            float((recvd / ordered) * 100) if ordered > 0 else None
        )

        spend = pos.aggregate(s=Sum('total_amount'))['s'] or Decimal('0')

        out.append({
            'supplier_id': str(sup.id),
            'supplier_name': sup.name,
            'po_count': po_count,
            'avg_lead_time_days': round(avg_lead, 1) if avg_lead is not None else None,
            'receive_accuracy_percent': round(accuracy, 1) if accuracy is not None else None,
            'total_spend': str(spend),
        })

    out.sort(key=lambda r: r['po_count'], reverse=True)
    return out


# ──────────────────────────────────────────────────────────────────────
# Recipe profitability
# ──────────────────────────────────────────────────────────────────────
def recipe_profitability(org_ids: list) -> list:
    """
    For each active recipe with an output_item that has a selling_price,
    margin = selling_price - cost_per_output_unit.
    """
    from .recipe_engine import RecipeEngine

    recipes = (
        Recipe.objects.filter(organization_id__in=org_ids, is_active=True)
        .select_related('output_item')
        .prefetch_related('ingredients__item')
    )
    out = []
    for r in recipes:
        if not r.output_item or r.output_item.selling_price is None:
            continue
        cost_batch = RecipeEngine.cost_of_batch(r, batches=Decimal('1'))
        output_qty = r.output_quantity or Decimal('1')
        cost_per_unit = (
            cost_batch / output_qty if output_qty > 0 else cost_batch
        )
        sp = r.output_item.selling_price
        margin_per_unit = sp - cost_per_unit
        margin_pct = (
            float((margin_per_unit / sp) * 100) if sp > 0 else None
        )
        out.append({
            'recipe_id': str(r.id),
            'recipe_name': r.name,
            'output_item': r.output_item.name,
            'output_unit': r.output_item.unit,
            'selling_price': str(sp.quantize(Decimal('0.01'))),
            'cost_per_unit': str(cost_per_unit.quantize(Decimal('0.0001'))),
            'margin_per_unit': str(margin_per_unit.quantize(Decimal('0.0001'))),
            'margin_percent': round(margin_pct, 1) if margin_pct is not None else None,
        })
    out.sort(key=lambda r: r['margin_percent'] or -999, reverse=True)
    return out


# ──────────────────────────────────────────────────────────────────────
# Waste analysis
# ──────────────────────────────────────────────────────────────────────
def waste_analysis(org_ids: list, *, days: int = 30) -> dict:
    cutoff = timezone.now().date() - timedelta(days=days)
    qs = StockMovement.objects.filter(
        organization_id__in=org_ids,
        movement_type=StockMovement.MovementType.WASTE,
        movement_date__gte=cutoff,
        is_reversed=False,
    )
    by_item = (
        qs.values('item_id', 'item__name', 'item__sku', 'item__unit')
        .annotate(total=Sum('quantity'), count=Count('id'))
        .order_by('total')[:20]
    )
    by_week = {}
    for row in qs.values('movement_date', 'quantity'):
        # ISO week bucket (year-week).
        wk = row['movement_date'].isocalendar()
        key = f'{wk.year}-W{wk.week:02d}'
        by_week[key] = by_week.get(key, Decimal('0')) + (-row['quantity'])

    return {
        'days': days,
        'top_items': [
            {
                'item_id': str(r['item_id']),
                'item_name': r['item__name'],
                'sku': r['item__sku'],
                'unit': r['item__unit'],
                'wasted': str(-(r['total'] or Decimal('0'))),
                'event_count': r['count'],
            }
            for r in by_item
        ],
        'by_week': [
            {'week': k, 'wasted': str(v)}
            for k, v in sorted(by_week.items())
        ],
    }
