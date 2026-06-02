"""
Inventory views — Plane B.

ALL routes in this module require IsInventoryAdmin (owner) for writes
and authenticated org membership for reads. There is NO public surface here.
"""
import csv
import io
import os
from decimal import Decimal

from django.conf import settings
from django.core.files.storage import default_storage
from django.db.models import Q, Sum, Count, F
from django.http import HttpResponse
from django.utils import timezone

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from apps.accounts.models import OrganizationMembership
from apps.common.utils import (
    client_ip as _client_ip,
    model_to_dict as _model_to_dict,
    diff as _diff,
)
from apps.common.mixins import AuditLoggedMixin as _CommonAuditLoggedMixin

from .mixins import InventoryOrgScopeMixin
from .models import (
    InventoryCategory, Supplier, InventoryItem, StockMovement,
    StockAlert, InventoryAuditLog,
    PurchaseOrder, PurchaseOrderItem,
    Recipe, RecipeIngredient, RecipeVersion,
    SalesImport, SupplierImport,
    LocationStock, LocationItemPricing, StockTake, StockTakeLine,
    PurchaseOrderEmail,
    RecipeBookingLink,
    ConsumptionLog,
)
from .permissions import IsInventoryAdmin
from .serializers import (
    InventoryCategorySerializer, SupplierSerializer, InventoryItemSerializer,
    StockMovementSerializer, StockAlertSerializer, InventoryAuditLogSerializer,
    StockAdjustmentSerializer,
    PurchaseOrderSerializer, PurchaseOrderItemSerializer,
    PurchaseOrderReceiveSerializer,
    RecipeSerializer, RecipeIngredientSerializer, RecipeVersionSerializer,
    RecipeBatchSerializer,
    SalesImportSerializer, SupplierImportSerializer, ImportColumnMapSerializer,
    InventoryAIQuerySerializer,
    LocationStockSerializer, StockTakeSerializer,
    LocationItemPricingSerializer,
    PurchaseOrderSendSerializer, PurchaseOrderEmailSerializer,
    BulkItemEditSerializer,
    RecipeBookingLinkSerializer,
    ConsumptionLogSerializer,
)


# ──────────────────────────────────────────────────────────────────────
# Audit logging
#
# As of Phase 0 the helpers (_client_ip / _model_to_dict / _diff) and the
# create/update/destroy audit logic were promoted to apps.common (imported at
# the top of this module under their original names). This subclass just points
# the shared mixin at the inventory audit model — behavior is unchanged.
# ──────────────────────────────────────────────────────────────────────
class AuditLoggedMixin(_CommonAuditLoggedMixin):
    """
    Inventory audit logging — writes to InventoryAuditLog. The create/update/
    destroy logic lives in the shared common mixin (Phase 0); this subclass
    just points it at the inventory audit model, so behavior is unchanged.
    """
    audit_log_model = InventoryAuditLog


# ──────────────────────────────────────────────────────────────────────
# Categories / Suppliers / Items
# ──────────────────────────────────────────────────────────────────────
class InventoryCategoryViewSet(AuditLoggedMixin, InventoryOrgScopeMixin, viewsets.ModelViewSet):
    queryset = InventoryCategory.objects.all()
    serializer_class = InventoryCategorySerializer
    permission_classes = [IsAuthenticated, IsInventoryAdmin]
    audit_model_name = 'InventoryCategory'


class SupplierViewSet(AuditLoggedMixin, InventoryOrgScopeMixin, viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [IsAuthenticated, IsInventoryAdmin]
    audit_model_name = 'Supplier'


class InventoryItemViewSet(AuditLoggedMixin, InventoryOrgScopeMixin, viewsets.ModelViewSet):
    queryset = InventoryItem.objects.select_related('category', 'supplier').all()
    serializer_class = InventoryItemSerializer
    permission_classes = [IsAuthenticated, IsInventoryAdmin]
    audit_model_name = 'InventoryItem'

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get('category'):
            qs = qs.filter(category_id=params['category'])
        if params.get('supplier'):
            qs = qs.filter(supplier_id=params['supplier'])
        if params.get('is_active') is not None:
            qs = qs.filter(is_active=params['is_active'].lower() == 'true')
        if params.get('search'):
            term = params['search']
            qs = qs.filter(
                Q(name__icontains=term) | Q(sku__icontains=term) | Q(barcode__icontains=term)
            )
        if params.get('status') == 'critical':
            qs = qs.filter(reorder_level__gt=0, current_stock__lte=F('reorder_level'))
        elif params.get('status') == 'negative':
            qs = qs.filter(current_stock__lt=0)
        return qs

    @action(detail=True, methods=['post'], url_path='adjust')
    def adjust(self, request, pk=None):
        item = self.get_object()
        ser = StockAdjustmentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        membership = OrganizationMembership.objects.filter(
            user=request.user, organization=item.organization,
            role=OrganizationMembership.Role.OWNER,
        ).first()
        if not membership:
            return Response(
                {'detail': 'Only owners can adjust stock.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        from .services.stock_engine import StockEngine
        engine = StockEngine(
            organization=item.organization,
            location=item.location,
            performed_by=request.user,
        )
        movement = engine.manual_adjustment(
            item=item,
            quantity=ser.validated_data['quantity'],
            reason=ser.validated_data['reason'],
            movement_date=ser.validated_data.get('movement_date'),
        )
        InventoryAuditLog.objects.create(
            organization=item.organization,
            location=item.location,
            action='adjust',
            model_name='InventoryItem',
            object_id=item.id,
            object_repr=str(item),
            after={
                'movement_id': str(movement.id),
                'quantity': str(movement.quantity),
                'reason': movement.notes,
            },
            performed_by=request.user,
            ip_address=_client_ip(request),
        )
        item.refresh_from_db()
        return Response(InventoryItemSerializer(item).data)

    @action(detail=True, methods=['get'], url_path='effective-stock')
    def effective_stock(self, request, pk=None):
        from .services.tolerance_engine import ToleranceEngine
        item = self.get_object()
        es = ToleranceEngine.effective_stock(
            item.current_stock, item.reorder_level, item.tolerance_percent,
        )
        return Response(es.to_dict())

    @action(detail=True, methods=['get'])
    def movements(self, request, pk=None):
        item = self.get_object()
        qs = item.movements.all().order_by('-movement_date', '-created_at')[:200]
        return Response(StockMovementSerializer(qs, many=True).data)

    @action(detail=False, methods=['post'], url_path='bulk-update')
    def bulk_update(self, request):
        """
        Bulk-update reorder/category/supplier/is_active across many items.
        One audit-log row per item changed. Owner-only.
        """
        ser = BulkItemEditSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ids = ser.validated_data['ids']
        patch = ser.validated_data['patch']

        qs = self.get_queryset().filter(pk__in=ids)
        # Ownership: every targeted item must belong to an org the user owns.
        owned_org_ids = set(OrganizationMembership.objects.filter(
            user=request.user, role=OrganizationMembership.Role.OWNER,
        ).values_list('organization_id', flat=True))
        forbidden = [
            str(it.pk) for it in qs if it.organization_id not in owned_org_ids
        ]
        if forbidden:
            return Response(
                {'detail': 'You are not the owner of every targeted item.',
                 'forbidden_ids': forbidden},
                status=status.HTTP_403_FORBIDDEN,
            )

        updated_count = 0
        for it in qs:
            before = _model_to_dict(it)
            for field, value in patch.items():
                # Use the FK id form for category/supplier so we don't need to fetch.
                if field in ('category', 'supplier'):
                    setattr(it, f'{field}_id', value)
                else:
                    setattr(it, field, value)
            it.save()
            after = _model_to_dict(it)
            InventoryAuditLog.objects.create(
                organization=it.organization,
                location=it.location,
                action='bulk_update',
                model_name='InventoryItem',
                object_id=it.id,
                object_repr=str(it),
                before=before, after=after, diff=_diff(before, after),
                performed_by=request.user,
                ip_address=_client_ip(request),
            )
            updated_count += 1
        return Response({'updated': updated_count, 'requested': len(ids)})

    @action(detail=True, methods=['get'], url_path='location-stocks')
    def location_stocks(self, request, pk=None):
        item = self.get_object()
        rows = item.location_stocks.select_related('location').all()
        return Response(LocationStockSerializer(rows, many=True).data)

    @action(detail=False, methods=['get'], url_path='dashboard')
    def dashboard(self, request):
        qs = self.get_queryset()
        active = qs.filter(is_active=True)
        items = list(active.values('id', 'current_stock', 'reorder_level', 'unit_cost'))
        critical_count = sum(
            1 for i in items
            if i['reorder_level'] > 0 and i['current_stock'] <= i['reorder_level']
        )
        negative_count = sum(1 for i in items if i['current_stock'] < 0)
        total_value = sum(
            ((i['current_stock'] or Decimal('0')) * (i['unit_cost'] or Decimal('0'))
             for i in items),
            Decimal('0'),
        )
        org_ids = list(qs.values_list('organization_id', flat=True).distinct())
        open_alerts = StockAlert.objects.filter(
            organization_id__in=org_ids, is_resolved=False,
        ).count()
        return Response({
            'total_items': len(items),
            'critical_count': critical_count,
            'negative_count': negative_count,
            'total_inventory_value': str(total_value.quantize(Decimal('0.01'))),
            'open_alerts': open_alerts,
        })


# ──────────────────────────────────────────────────────────────────────
# Movements (read + reverse)
# ──────────────────────────────────────────────────────────────────────
class StockMovementViewSet(InventoryOrgScopeMixin, viewsets.ReadOnlyModelViewSet):
    queryset = StockMovement.objects.select_related('item', 'created_by').all()
    serializer_class = StockMovementSerializer
    permission_classes = [IsAuthenticated, IsInventoryAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get('item'):
            qs = qs.filter(item_id=params['item'])
        if params.get('movement_type'):
            qs = qs.filter(movement_type=params['movement_type'])
        if params.get('start_date'):
            qs = qs.filter(movement_date__gte=params['start_date'])
        if params.get('end_date'):
            qs = qs.filter(movement_date__lte=params['end_date'])
        return qs

    @action(detail=False, methods=['get'], url_path='export')
    def export(self, request):
        """
        CSV export of the filtered movement list. Same filters as list().
        Mirrors the audit-log CSV pattern.
        """
        qs = self.get_queryset().select_related('item', 'created_by')[:50000]
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            'movement_date', 'item_sku', 'item_name', 'item_unit',
            'movement_type', 'quantity', 'unit_cost',
            'location', 'reference_id', 'reference_type', 'notes',
            'is_reversed', 'created_by', 'created_at',
        ])
        for m in qs:
            writer.writerow([
                m.movement_date.isoformat() if m.movement_date else '',
                m.item.sku, m.item.name, m.item.unit,
                m.movement_type, str(m.quantity),
                str(m.unit_cost) if m.unit_cost is not None else '',
                str(m.location_id) if m.location_id else '',
                m.reference_id, m.reference_type,
                (m.notes or '').replace('\n', ' ').replace('\r', ' '),
                m.is_reversed,
                getattr(m.created_by, 'email', '') if m.created_by_id else '',
                m.created_at.isoformat() if m.created_at else '',
            ])
        resp = HttpResponse(buf.getvalue(), content_type='text/csv')
        ts = timezone.now().strftime('%Y%m%d-%H%M%S')
        resp['Content-Disposition'] = f'attachment; filename="movements-{ts}.csv"'
        return resp

    @action(detail=True, methods=['post'])
    def reverse(self, request, pk=None):
        movement = self.get_object()
        membership = OrganizationMembership.objects.filter(
            user=request.user, organization=movement.organization,
            role=OrganizationMembership.Role.OWNER,
        ).first()
        if not membership:
            return Response(
                {'detail': 'Only owners can reverse movements.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        reason = (request.data.get('reason') or '').strip()
        if len(reason) < 5:
            return Response(
                {'reason': 'A reason of at least 5 characters is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from .services.stock_engine import StockEngine
        engine = StockEngine(
            organization=movement.organization,
            location=movement.location,
            performed_by=request.user,
        )
        try:
            reversal = engine.reverse_movement(str(movement.id), reason)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        InventoryAuditLog.objects.create(
            organization=movement.organization,
            location=movement.location,
            action='reverse',
            model_name='StockMovement',
            object_id=movement.id,
            object_repr=str(movement),
            after={'reversal_id': str(reversal.id), 'reason': reason},
            performed_by=request.user,
            ip_address=_client_ip(request),
        )
        return Response(StockMovementSerializer(reversal).data)


# ──────────────────────────────────────────────────────────────────────
# Alerts
# ──────────────────────────────────────────────────────────────────────
class StockAlertViewSet(InventoryOrgScopeMixin, viewsets.ReadOnlyModelViewSet):
    queryset = StockAlert.objects.select_related('item').all()
    serializer_class = StockAlertSerializer
    permission_classes = [IsAuthenticated, IsInventoryAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get('resolved') is not None:
            qs = qs.filter(
                is_resolved=self.request.query_params['resolved'].lower() == 'true'
            )
        return qs

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        alert = self.get_object()
        alert.is_resolved = True
        alert.resolved_at = timezone.now()
        alert.resolved_by = request.user
        alert.save(update_fields=['is_resolved', 'resolved_at', 'resolved_by'])
        return Response(StockAlertSerializer(alert).data)


# ──────────────────────────────────────────────────────────────────────
# Audit Log
# ──────────────────────────────────────────────────────────────────────
class InventoryAuditLogViewSet(InventoryOrgScopeMixin, viewsets.ReadOnlyModelViewSet):
    queryset = InventoryAuditLog.objects.all()
    serializer_class = InventoryAuditLogSerializer
    permission_classes = [IsAuthenticated, IsInventoryAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get('action'):
            qs = qs.filter(action=params['action'])
        if params.get('model_name'):
            qs = qs.filter(model_name=params['model_name'])
        if params.get('start'):
            qs = qs.filter(timestamp__gte=params['start'])
        if params.get('end'):
            qs = qs.filter(timestamp__lte=params['end'])
        return qs


# ──────────────────────────────────────────────────────────────────────
# Purchase Orders
# ──────────────────────────────────────────────────────────────────────
class PurchaseOrderViewSet(AuditLoggedMixin, InventoryOrgScopeMixin, viewsets.ModelViewSet):
    queryset = PurchaseOrder.objects.select_related('supplier').prefetch_related('items__item').all()
    serializer_class = PurchaseOrderSerializer
    permission_classes = [IsAuthenticated, IsInventoryAdmin]
    audit_model_name = 'PurchaseOrder'

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get('status'):
            qs = qs.filter(status=params['status'])
        if params.get('supplier'):
            qs = qs.filter(supplier_id=params['supplier'])
        return qs

    @action(detail=True, methods=['post'])
    def receive(self, request, pk=None):
        po = self.get_object()
        membership = OrganizationMembership.objects.filter(
            user=request.user, organization=po.organization,
            role=OrganizationMembership.Role.OWNER,
        ).first()
        if not membership:
            return Response(
                {'detail': 'Only owners can receive purchase orders.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if po.status == PurchaseOrder.Status.CANCELLED:
            return Response(
                {'detail': 'Cannot receive items on a cancelled PO.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ser = PurchaseOrderReceiveSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            line = po.items.get(pk=ser.validated_data['line_id'])
        except PurchaseOrderItem.DoesNotExist:
            return Response(
                {'detail': 'Line item not found on this PO.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        from .services.stock_engine import StockEngine
        engine = StockEngine(
            organization=po.organization, location=po.location, performed_by=request.user,
        )
        engine.receive_purchase_order_item(
            po_item=line,
            quantity_received=ser.validated_data['quantity_received'],
            unit_cost=ser.validated_data.get('unit_cost'),
        )
        po.refresh_from_db()
        return Response(PurchaseOrderSerializer(po).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        po = self.get_object()
        if po.status in (PurchaseOrder.Status.RECEIVED, PurchaseOrder.Status.CANCELLED):
            return Response(
                {'detail': f'Cannot cancel a PO in status {po.status}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        po.status = PurchaseOrder.Status.CANCELLED
        po.save(update_fields=['status', 'updated_at'])
        self._audit('cancel', po, after={'status': po.status})
        return Response(PurchaseOrderSerializer(po).data)

    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        from django.core.exceptions import ValidationError as DjangoValidationError
        po = self.get_object()
        ser = PurchaseOrderSendSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        from .services.po_send import send_po
        try:
            email = send_po(
                po,
                to_email=ser.validated_data.get('to_email') or None,
                performed_by=request.user,
            )
        except DjangoValidationError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        po.refresh_from_db()
        self._audit('send', po, after={
            'sent_at': po.sent_at.isoformat() if po.sent_at else None,
            'sent_to_email': po.sent_to_email,
            'email_id': str(email.id),
        })
        return Response({
            'po': PurchaseOrderSerializer(po).data,
            'email': PurchaseOrderEmailSerializer(email).data,
        })

    @action(detail=True, methods=['get'])
    def pdf(self, request, pk=None):
        po = self.get_object()
        from .services.po_send import render_po_pdf
        pdf_bytes = render_po_pdf(po)
        # If reportlab is missing it falls back to text — still serve as PDF
        # if it starts with %PDF, else as text/plain.
        if pdf_bytes[:4] == b'%PDF':
            content_type = 'application/pdf'
            ext = 'pdf'
        else:
            content_type = 'text/plain'
            ext = 'txt'
        resp = HttpResponse(pdf_bytes, content_type=content_type)
        resp['Content-Disposition'] = f'attachment; filename="{po.order_number}.{ext}"'
        return resp


# ──────────────────────────────────────────────────────────────────────
# Recipes
# ──────────────────────────────────────────────────────────────────────
class RecipeViewSet(AuditLoggedMixin, InventoryOrgScopeMixin, viewsets.ModelViewSet):
    queryset = Recipe.objects.select_related(
        'output_item', 'category',
        'linked_promo_rule', 'linked_promo_rule__menu_item',
    ).prefetch_related('ingredients__item').all()
    serializer_class = RecipeSerializer
    permission_classes = [IsAuthenticated, IsInventoryAdmin]
    audit_model_name = 'Recipe'

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get('is_active') is not None:
            qs = qs.filter(
                is_active=self.request.query_params['is_active'].lower() == 'true'
            )
        formula_type = self.request.query_params.get('formula_type')
        if formula_type:
            qs = qs.filter(formula_type=formula_type)
        return qs

    @action(detail=True, methods=['post'])
    def calculate(self, request, pk=None):
        recipe = self.get_object()
        ser = RecipeBatchSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        from .services.recipe_engine import RecipeEngine
        return Response(RecipeEngine.calculate_batch(recipe, ser.validated_data['batches']))

    @action(detail=True, methods=['get'])
    def suggest_batches(self, request, pk=None):
        recipe = self.get_object()
        from .services.recipe_engine import RecipeEngine
        return Response({'max_batches': str(RecipeEngine.suggest_batches(recipe))})

    @action(detail=True, methods=['post'])
    def consume(self, request, pk=None):
        recipe = self.get_object()
        membership = OrganizationMembership.objects.filter(
            user=request.user, organization=recipe.organization,
            role=OrganizationMembership.Role.OWNER,
        ).first()
        if not membership:
            return Response(
                {'detail': 'Only owners can consume recipes.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        ser = RecipeBatchSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        # Optional explicit classification; otherwise StockEngine infers it
        # (cocktail_serve / promo_sale / manual) from the recipe.
        consumption_type = request.data.get('consumption_type') or None
        valid_types = {c[0] for c in ConsumptionLog.ConsumptionType.choices}
        if consumption_type and consumption_type not in valid_types:
            return Response(
                {'consumption_type': f'Invalid value. One of: {sorted(valid_types)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from .services.stock_engine import StockEngine
        engine = StockEngine(
            organization=recipe.organization, location=recipe.location, performed_by=request.user,
        )
        try:
            result = engine.consume_recipe(
                recipe, ser.validated_data['batches'],
                consumption_type=consumption_type,
            )
        except Exception as e:
            payload = getattr(e, 'message_dict', None) or {'detail': str(e)}
            return Response(payload, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        InventoryAuditLog.objects.create(
            organization=recipe.organization,
            location=recipe.location,
            action='consume',
            model_name='Recipe',
            object_id=recipe.id,
            object_repr=str(recipe),
            after=result,
            performed_by=request.user,
            ip_address=_client_ip(request),
        )
        return Response(result)

    @action(detail=True, methods=['get'])
    def versions(self, request, pk=None):
        recipe = self.get_object()
        qs = recipe.versions.all()[:200]
        return Response(RecipeVersionSerializer(qs, many=True).data)

    @action(detail=True, methods=['get'], url_path='version-diff')
    def version_diff(self, request, pk=None):
        recipe = self.get_object()
        try:
            v1 = int(request.query_params.get('v1'))
            v2 = int(request.query_params.get('v2'))
        except (TypeError, ValueError):
            return Response(
                {'detail': 'Provide ?v1=&v2= as integers.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from .services.recipe_engine import RecipeEngine
        try:
            return Response(RecipeEngine.version_diff(recipe, v1, v2))
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_404_NOT_FOUND)


# ──────────────────────────────────────────────────────────────────────
# Imports — sales + purchases
# ──────────────────────────────────────────────────────────────────────
def _validate_upload(uploaded_file):
    max_mb = settings.INVENTORY_SETTINGS.get('EXCEL_MAX_FILE_SIZE_MB', 10)
    if uploaded_file.size > max_mb * 1024 * 1024:
        raise ValueError(f'File exceeds {max_mb} MB limit.')
    name = uploaded_file.name.lower()
    if not (name.endswith('.xlsx') or name.endswith('.xls') or name.endswith('.csv')):
        raise ValueError('Only .xlsx, .xls, .csv files are accepted.')


class _ImportViewSetBase(InventoryOrgScopeMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsInventoryAdmin]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ['get', 'post', 'head', 'options']
    import_type = None  # set in subclasses

    def create(self, request, *args, **kwargs):
        f = request.FILES.get('import_file')
        if not f:
            return Response({'detail': 'import_file is required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            _validate_upload(f)
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        membership = OrganizationMembership.objects.filter(
            user=request.user,
            role=OrganizationMembership.Role.OWNER,
        ).first()
        if not membership:
            return Response({'detail': 'Only owners can run imports.'},
                            status=status.HTTP_403_FORBIDDEN)

        org = membership.organization
        data = {
            'organization': org.id,
            'file_name': f.name,
            'import_file': f,
        }
        if 'location' in request.data and request.data.get('location'):
            data['location'] = request.data['location']
        if self.import_type == 'purchase' and request.data.get('supplier'):
            data['supplier'] = request.data.get('supplier')

        ser = self.get_serializer(data=data)
        ser.is_valid(raise_exception=True)
        instance = ser.save(created_by=request.user)

        # Synchronous preview to populate column_map + row_count immediately.
        from .services.excel_parser import ExcelParser
        try:
            file_path = instance.import_file.path
            parser = ExcelParser(
                file_path=file_path,
                import_type=self.import_type,
                organization=org,
                location=getattr(instance, 'location', None),
            )
            preview = parser.preview(max_rows=settings.INVENTORY_SETTINGS.get(
                'EXCEL_PREVIEW_ROWS', 10,
            ))
            instance.column_map = preview['column_map']
            instance.row_count = preview['total_rows']
            instance.error_count = preview['error_rows']
            instance.error_log = preview['errors']
            instance.save(update_fields=[
                'column_map', 'row_count', 'error_count', 'error_log', 'updated_at',
            ])
        except Exception as e:
            instance.status = instance.Status.FAILED
            instance.error_log = [{'row': 0, 'column': '', 'message': str(e)}]
            instance.save(update_fields=['status', 'error_log', 'updated_at'])

        return Response(self.get_serializer(instance).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def preview(self, request, pk=None):
        instance = self.get_object()
        from .services.excel_parser import ExcelParser
        parser = ExcelParser(
            file_path=instance.import_file.path,
            import_type=self.import_type,
            organization=instance.organization,
            location=getattr(instance, 'location', None),
        )
        try:
            preview = parser.preview(max_rows=settings.INVENTORY_SETTINGS.get(
                'EXCEL_PREVIEW_ROWS', 10,
            ))
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(preview)

    @action(detail=True, methods=['post'])
    def commit(self, request, pk=None):
        """Kick off Celery task that processes the import."""
        instance = self.get_object()
        if instance.status != instance.Status.PENDING:
            return Response(
                {'detail': f'Import is in status {instance.status}; cannot commit.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Optional column_map override
        override = ImportColumnMapSerializer(data=request.data)
        override.is_valid(raise_exception=True)
        if override.validated_data.get('column_map'):
            instance.column_map = override.validated_data['column_map']
            instance.save(update_fields=['column_map', 'updated_at'])

        from .tasks import process_excel_import_task
        async_result = process_excel_import_task.delay(
            str(instance.id), self.import_type,
        )
        instance.task_id = async_result.id
        instance.status = instance.Status.PROCESSING
        instance.save(update_fields=['task_id', 'status', 'updated_at'])
        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        instance = self.get_object()
        return Response(self.get_serializer(instance).data)


class SalesImportViewSet(_ImportViewSetBase):
    queryset = SalesImport.objects.all()
    serializer_class = SalesImportSerializer
    import_type = 'sales'


class SupplierImportViewSet(_ImportViewSetBase):
    queryset = SupplierImport.objects.all()
    serializer_class = SupplierImportSerializer
    import_type = 'purchase'


# ──────────────────────────────────────────────────────────────────────
# Inventory AI (admin-only)
# ──────────────────────────────────────────────────────────────────────
class InventoryAIViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsInventoryAdmin]

    @action(detail=False, methods=['post'])
    def query(self, request):
        ser = InventoryAIQuerySerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        # Pick organization the user owns.
        membership = OrganizationMembership.objects.filter(
            user=request.user,
        ).first()
        if not membership:
            return Response(
                {'detail': 'No organization membership found.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if ser.validated_data.get('organization'):
            membership = OrganizationMembership.objects.filter(
                user=request.user, organization_id=ser.validated_data['organization'],
            ).first()
            if not membership:
                return Response(
                    {'detail': 'Not a member of that organization.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

        # Require power plan if gating is enabled at org level.
        org = membership.organization
        plan = getattr(org, 'plan', None)
        if plan and plan != 'power':
            return Response(
                {'detail': 'Inventory AI is available on the power plan only.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        from .services.ai_engine import InventoryAIEngine
        engine = InventoryAIEngine()
        result = engine.query(
            question=ser.validated_data['question'],
            organization=org,
            user=request.user,
        )
        return Response(result)


# ──────────────────────────────────────────────────────────────────────
# Reports
# ──────────────────────────────────────────────────────────────────────
class InventoryReportViewSet(InventoryOrgScopeMixin, viewsets.GenericViewSet):
    """
    Read-only aggregation endpoints for the inventory dashboard.
    queryset is a sentinel — child actions roll their own.
    """
    queryset = InventoryItem.objects.all()
    permission_classes = [IsAuthenticated, IsInventoryAdmin]

    @action(detail=False, methods=['get'], url_path='stock-health')
    def stock_health(self, request):
        qs = self.get_queryset().filter(is_active=True)
        items = list(qs.values('id', 'name', 'sku', 'unit',
                               'current_stock', 'reorder_level',
                               'category__name', 'category_id'))
        buckets = {'critical': 0, 'low': 0, 'normal': 0, 'overstock': 0, 'negative': 0}
        per_category = {}
        for it in items:
            cat = it['category__name'] or 'Uncategorized'
            stat = 'normal'
            cs = it['current_stock'] or Decimal('0')
            r = it['reorder_level'] or Decimal('0')
            if cs < 0:
                stat = 'negative'
            elif r > 0 and cs <= r:
                stat = 'critical'
            elif r > 0 and cs <= r * 2:
                stat = 'low'
            elif r > 0 and cs > r * 5:
                stat = 'overstock'
            buckets[stat] = buckets.get(stat, 0) + 1
            cat_bucket = per_category.setdefault(
                cat, {'critical': 0, 'low': 0, 'normal': 0, 'overstock': 0, 'negative': 0}
            )
            cat_bucket[stat] += 1
        return Response({
            'totals': buckets,
            'per_category': [{'category': k, **v} for k, v in per_category.items()],
            'item_count': len(items),
        })

    @action(detail=False, methods=['get'], url_path='movement-timeline')
    def movement_timeline(self, request):
        from datetime import timedelta
        days = int(request.query_params.get('days', 14))
        cutoff = timezone.now().date() - timedelta(days=days)
        qs = StockMovement.objects.filter(
            organization_id__in=self._user_org_ids(),
            movement_date__gte=cutoff, is_reversed=False,
        )
        timeline = {}
        for mv in qs.values('movement_date', 'quantity'):
            d = mv['movement_date'].isoformat()
            entry = timeline.setdefault(d, {'in': Decimal('0'), 'out': Decimal('0')})
            if mv['quantity'] >= 0:
                entry['in'] += mv['quantity']
            else:
                entry['out'] += -mv['quantity']
        out = [
            {'date': d, 'in': str(v['in']), 'out': str(v['out'])}
            for d, v in sorted(timeline.items())
        ]
        return Response({'days': days, 'series': out})

    @action(detail=False, methods=['get'], url_path='top-consumed')
    def top_consumed(self, request):
        from datetime import timedelta
        days = int(request.query_params.get('days', 7))
        cutoff = timezone.now().date() - timedelta(days=days)
        qs = (
            StockMovement.objects.filter(
                organization_id__in=self._user_org_ids(),
                movement_date__gte=cutoff, is_reversed=False,
                quantity__lt=0,
            )
            .values('item_id', 'item__name', 'item__sku', 'item__unit')
            .annotate(total_out=Sum('quantity'))
            .order_by('total_out')[:10]
        )
        return Response([
            {
                'item_id': str(r['item_id']),
                'item_name': r['item__name'],
                'sku': r['item__sku'],
                'unit': r['item__unit'],
                'consumed': str(-(r['total_out'] or Decimal('0'))),
            }
            for r in qs
        ])

    @action(detail=False, methods=['get'], url_path='variance')
    def variance(self, request):
        """Items whose current stock is outside their tolerance band of reorder × 2."""
        qs = self.get_queryset().filter(is_active=True)
        rows = []
        for it in qs:
            from .services.tolerance_engine import ToleranceEngine
            es = ToleranceEngine.effective_stock(
                it.current_stock, it.reorder_level, it.tolerance_percent,
            )
            if es.is_critical or es.is_negative:
                rows.append({
                    'item_id': str(it.id),
                    'item_name': it.name,
                    'sku': it.sku,
                    'unit': it.unit,
                    'reported': str(es.reported),
                    'lower_bound': str(es.lower_bound),
                    'upper_bound': str(es.upper_bound),
                    'reorder_level': str(it.reorder_level),
                    'is_critical': es.is_critical,
                    'is_negative': es.is_negative,
                })
        return Response(rows)

    # ──────────────────────────────────────────────────────────────
    # Phase 5 reports
    # ──────────────────────────────────────────────────────────────
    @action(detail=False, methods=['get'], url_path='reorder-forecast')
    def reorder_forecast(self, request):
        from .services.analytics import reorder_forecast
        days = int(request.query_params.get('days', 30))
        return Response({'days': days,
                         'rows': reorder_forecast(self._user_org_ids(), days=days)})

    @action(detail=False, methods=['get'], url_path='supplier-scorecards')
    def supplier_scorecards(self, request):
        from .services.analytics import supplier_scorecards
        return Response(supplier_scorecards(self._user_org_ids()))

    @action(detail=False, methods=['get'], url_path='recipe-profitability')
    def recipe_profitability(self, request):
        from .services.analytics import recipe_profitability
        return Response(recipe_profitability(self._user_org_ids()))

    @action(detail=False, methods=['get'], url_path='waste-analysis')
    def waste_analysis(self, request):
        from .services.analytics import waste_analysis
        days = int(request.query_params.get('days', 30))
        return Response(waste_analysis(self._user_org_ids(), days=days))

    @action(detail=False, methods=['get'], url_path='weekly-insights')
    def weekly_insights(self, request):
        """On-demand version of the Monday Celery task — owner-only."""
        from .services.ai_engine import InventoryAIEngine
        org_id = request.query_params.get('organization')
        org_ids = self._user_org_ids()
        if not org_ids:
            return Response({'detail': 'No organizations.'},
                            status=status.HTTP_403_FORBIDDEN)
        from apps.accounts.models import Organization
        org = (
            Organization.objects.filter(pk=org_id, id__in=org_ids).first()
            if org_id else
            Organization.objects.filter(id__in=org_ids).first()
        )
        if not org:
            return Response({'detail': 'Org not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(InventoryAIEngine().insights(org))


# ──────────────────────────────────────────────────────────────────────
# Phase 4 — StockTake
# ──────────────────────────────────────────────────────────────────────
class StockTakeViewSet(AuditLoggedMixin, InventoryOrgScopeMixin, viewsets.ModelViewSet):
    queryset = StockTake.objects.prefetch_related('lines__item').all()
    serializer_class = StockTakeSerializer
    permission_classes = [IsAuthenticated, IsInventoryAdmin]
    audit_model_name = 'StockTake'

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get('status'):
            qs = qs.filter(status=self.request.query_params['status'])
        return qs

    @action(detail=True, methods=['post'])
    def commit(self, request, pk=None):
        st = self.get_object()
        membership = OrganizationMembership.objects.filter(
            user=request.user, organization=st.organization,
            role=OrganizationMembership.Role.OWNER,
        ).first()
        if not membership:
            return Response({'detail': 'Only owners can commit a stock-take.'},
                            status=status.HTTP_403_FORBIDDEN)
        from .services.stock_take_engine import StockTakeEngine
        from django.core.exceptions import ValidationError as DjangoValidationError
        try:
            result = StockTakeEngine.commit(st, performed_by=request.user)
        except DjangoValidationError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        st.refresh_from_db()
        self._audit('commit', st, after=result)
        return Response({
            'stock_take': StockTakeSerializer(st).data,
            'result': result,
        })

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        st = self.get_object()
        if st.status != StockTake.Status.IN_PROGRESS:
            return Response({'detail': f'Cannot cancel a stock-take in status {st.status}.'},
                            status=status.HTTP_400_BAD_REQUEST)
        st.status = StockTake.Status.CANCELLED
        st.save(update_fields=['status', 'updated_at'])
        self._audit('cancel', st, after={'status': st.status})
        return Response(StockTakeSerializer(st).data)


# ──────────────────────────────────────────────────────────────────────
# Phase 4 — LocationStock (read-only) + LocationItemPricing
# ──────────────────────────────────────────────────────────────────────
class LocationStockViewSet(InventoryOrgScopeMixin, viewsets.ReadOnlyModelViewSet):
    queryset = LocationStock.objects.select_related('item', 'location').all()
    serializer_class = LocationStockSerializer
    permission_classes = [IsAuthenticated, IsInventoryAdmin]

    def get_queryset(self):
        # The mixin scopes by `organization`, but LocationStock has none —
        # filter by item.organization instead.
        user = self.request.user
        if not user.is_authenticated:
            return self.queryset.none()
        org_ids = list(
            OrganizationMembership.objects.filter(user=user)
            .values_list('organization_id', flat=True)
        )
        qs = self.queryset.filter(item__organization_id__in=org_ids)
        params = self.request.query_params
        if params.get('item'):
            qs = qs.filter(item_id=params['item'])
        if params.get('location'):
            qs = qs.filter(location_id=params['location'])
        return qs


class LocationItemPricingViewSet(AuditLoggedMixin, InventoryOrgScopeMixin, viewsets.ModelViewSet):
    queryset = LocationItemPricing.objects.select_related('item', 'location').all()
    serializer_class = LocationItemPricingSerializer
    permission_classes = [IsAuthenticated, IsInventoryAdmin]
    audit_model_name = 'LocationItemPricing'


    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return self.queryset.none()
        org_ids = list(
            OrganizationMembership.objects.filter(user=user)
            .values_list('organization_id', flat=True)
        )
        qs = self.queryset.filter(item__organization_id__in=org_ids)
        if self.request.query_params.get('item'):
            qs = qs.filter(item_id=self.request.query_params['item'])
        if self.request.query_params.get('location'):
            qs = qs.filter(location_id=self.request.query_params['location'])
        return qs

    def perform_create(self, serializer):
        # Bypass the parent mixin's perform_create which expects organization
        # in the payload — pricing is scoped via item.
        instance = serializer.save()
        self._audit('create', instance, after=_model_to_dict(instance))


class ConsumptionLogViewSet(InventoryOrgScopeMixin, viewsets.ReadOnlyModelViewSet):
    """Phase 4 — read-only audit of recipe consumption (append-only model)."""
    queryset = ConsumptionLog.objects.select_related(
        'recipe', 'movement', 'movement__item',
    ).all()
    serializer_class = ConsumptionLogSerializer
    permission_classes = [IsAuthenticated, IsInventoryAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get('recipe'):
            qs = qs.filter(recipe_id=params['recipe'])
        if params.get('consumption_type'):
            qs = qs.filter(consumption_type=params['consumption_type'])
        return qs


# ──────────────────────────────────────────────────────────────────────
# Phase 6 — RecipeBookingLink (Plane A bridge)
# ──────────────────────────────────────────────────────────────────────
class RecipeBookingLinkViewSet(
    AuditLoggedMixin, InventoryOrgScopeMixin, viewsets.ModelViewSet,
):
    queryset = RecipeBookingLink.objects.select_related(
        'recipe', 'booking', 'organization',
    ).all()
    serializer_class = RecipeBookingLinkSerializer
    permission_classes = [IsAuthenticated, IsInventoryAdmin]
    audit_model_name = 'RecipeBookingLink'

    def get_queryset(self):
        qs = super().get_queryset()
        booking_id = self.request.query_params.get('booking')
        if booking_id:
            qs = qs.filter(booking_id=booking_id)
        return qs

    def perform_create(self, serializer):
        # The parent mixin enforces owner-of-org check, then injects
        # created_by. RecipeBookingLink has no created_by field, so we
        # do the owner check manually and save without it.
        from rest_framework.exceptions import PermissionDenied, ValidationError
        org_id = serializer.validated_data.get('organization')
        org_id = getattr(org_id, 'id', org_id)
        if not org_id:
            raise ValidationError({'organization': 'organization is required.'})
        membership = OrganizationMembership.objects.filter(
            user=self.request.user,
            organization_id=org_id,
            role=OrganizationMembership.Role.OWNER,
        ).first()
        if not membership:
            raise PermissionDenied(
                'Only the organization owner can create inventory records.'
            )
        instance = serializer.save()
        self._audit('create', instance, after=_model_to_dict(instance))
