"""
Inventory views — Plane B.

ALL routes in this module require IsInventoryAdmin (owner) for writes
and authenticated org membership for reads. There is NO public surface here.
"""
import os
from decimal import Decimal

from django.conf import settings
from django.core.files.storage import default_storage
from django.db.models import Q, Sum, Count, F
from django.utils import timezone

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from apps.accounts.models import OrganizationMembership

from .mixins import InventoryOrgScopeMixin
from .models import (
    InventoryCategory, Supplier, InventoryItem, StockMovement,
    StockAlert, InventoryAuditLog,
    PurchaseOrder, PurchaseOrderItem,
    Recipe, RecipeIngredient, RecipeVersion,
    SalesImport, SupplierImport,
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
)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────
def _client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _model_to_dict(instance, exclude=('updated_at',)):
    """Lightweight snapshot for audit-log diffs."""
    data = {}
    for f in instance._meta.fields:
        if f.name in exclude:
            continue
        val = getattr(instance, f.attname, None)
        if hasattr(val, 'isoformat'):
            val = val.isoformat()
        elif isinstance(val, Decimal):
            val = str(val)
        else:
            val = str(val) if val is not None else None
        data[f.name] = val
    return data


def _diff(before: dict, after: dict) -> dict:
    out = {}
    for k in set(before) | set(after):
        b, a = before.get(k), after.get(k)
        if b != a:
            out[k] = {'before': b, 'after': a}
    return out


class AuditLoggedMixin:
    """
    Auto-log create/update/destroy on inventory ViewSets to InventoryAuditLog.

    Reads `audit_model_name` from the ViewSet (defaults to model class name).
    Skips logging when the writer is None or the request is read-only.
    """
    audit_model_name = None

    def _audit(self, action: str, instance, before=None, after=None):
        try:
            InventoryAuditLog.objects.create(
                organization=instance.organization,
                location=getattr(instance, 'location', None),
                action=action,
                model_name=self.audit_model_name or type(instance).__name__,
                object_id=instance.id,
                object_repr=str(instance)[:200],
                before=before,
                after=after,
                diff=_diff(before, after) if (before and after) else None,
                performed_by=self.request.user if self.request.user.is_authenticated else None,
                ip_address=_client_ip(self.request),
            )
        except Exception:
            # Never let audit failure break the request.
            import logging
            logging.getLogger(__name__).exception('Audit log write failed')

    def perform_create(self, serializer):
        super().perform_create(serializer)
        instance = serializer.instance
        self._audit('create', instance, after=_model_to_dict(instance))

    def perform_update(self, serializer):
        before_instance = self.get_object()
        before = _model_to_dict(before_instance)
        super().perform_update(serializer)
        instance = serializer.instance
        self._audit('update', instance, before=before, after=_model_to_dict(instance))

    def perform_destroy(self, instance):
        before = _model_to_dict(instance)
        org = instance.organization
        loc = getattr(instance, 'location', None)
        model_name = self.audit_model_name or type(instance).__name__
        instance_id = instance.id
        instance_repr = str(instance)[:200]
        super().perform_destroy(instance)
        try:
            InventoryAuditLog.objects.create(
                organization=org, location=loc,
                action='delete', model_name=model_name,
                object_id=instance_id, object_repr=instance_repr,
                before=before,
                performed_by=self.request.user if self.request.user.is_authenticated else None,
                ip_address=_client_ip(self.request),
            )
        except Exception:
            pass


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


# ──────────────────────────────────────────────────────────────────────
# Recipes
# ──────────────────────────────────────────────────────────────────────
class RecipeViewSet(AuditLoggedMixin, InventoryOrgScopeMixin, viewsets.ModelViewSet):
    queryset = Recipe.objects.select_related('output_item', 'category').prefetch_related('ingredients__item').all()
    serializer_class = RecipeSerializer
    permission_classes = [IsAuthenticated, IsInventoryAdmin]
    audit_model_name = 'Recipe'

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get('is_active') is not None:
            qs = qs.filter(
                is_active=self.request.query_params['is_active'].lower() == 'true'
            )
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
        from .services.stock_engine import StockEngine
        engine = StockEngine(
            organization=recipe.organization, location=recipe.location, performed_by=request.user,
        )
        try:
            result = engine.consume_recipe(recipe, ser.validated_data['batches'])
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
