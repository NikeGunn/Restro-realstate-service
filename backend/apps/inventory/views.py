"""
Inventory views — Plane B.

ALL routes in this module require IsInventoryAdmin (owner) for writes
and authenticated org membership for reads. There is NO public surface here.
"""
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import OrganizationMembership

from .mixins import InventoryOrgScopeMixin
from .models import (
    InventoryCategory, Supplier, InventoryItem, StockMovement,
    StockAlert, InventoryAuditLog,
)
from .permissions import IsInventoryAdmin
from .serializers import (
    InventoryCategorySerializer, SupplierSerializer, InventoryItemSerializer,
    StockMovementSerializer, StockAlertSerializer, InventoryAuditLogSerializer,
    StockAdjustmentSerializer,
)


class InventoryCategoryViewSet(InventoryOrgScopeMixin, viewsets.ModelViewSet):
    queryset = InventoryCategory.objects.all()
    serializer_class = InventoryCategorySerializer
    permission_classes = [IsAuthenticated, IsInventoryAdmin]


class SupplierViewSet(InventoryOrgScopeMixin, viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [IsAuthenticated, IsInventoryAdmin]


class InventoryItemViewSet(InventoryOrgScopeMixin, viewsets.ModelViewSet):
    queryset = InventoryItem.objects.select_related('category', 'supplier').all()
    serializer_class = InventoryItemSerializer
    permission_classes = [IsAuthenticated, IsInventoryAdmin]

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
            from django.db.models import F
            qs = qs.filter(reorder_level__gt=0, current_stock__lte=F('reorder_level'))
        elif params.get('status') == 'negative':
            qs = qs.filter(current_stock__lt=0)
        return qs

    @action(detail=True, methods=['post'], url_path='adjust')
    def adjust(self, request, pk=None):
        """Manual stock adjustment. Only owners. Creates a StockMovement."""
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
        movement = StockMovement.objects.create(
            organization=item.organization,
            location=item.location,
            item=item,
            movement_type=StockMovement.MovementType.ADJUSTMENT,
            quantity=ser.validated_data['quantity'],
            notes=ser.validated_data['reason'],
            movement_date=ser.validated_data.get('movement_date') or timezone.now().date(),
            created_by=request.user,
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

    @action(detail=False, methods=['get'], url_path='dashboard')
    def dashboard(self, request):
        """Summary cards for the inventory home page."""
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
        open_alerts = StockAlert.objects.filter(
            organization_id__in=qs.values_list('organization_id', flat=True),
            is_resolved=False,
        ).count()
        return Response({
            'total_items': len(items),
            'critical_count': critical_count,
            'negative_count': negative_count,
            'total_inventory_value': str(total_value.quantize(Decimal('0.01'))),
            'open_alerts': open_alerts,
        })


def _client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


class StockMovementViewSet(InventoryOrgScopeMixin, viewsets.ReadOnlyModelViewSet):
    """Movements are append-only — no create endpoint here. Use item.adjust or imports."""
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


class InventoryAuditLogViewSet(InventoryOrgScopeMixin, viewsets.ReadOnlyModelViewSet):
    queryset = InventoryAuditLog.objects.all()
    serializer_class = InventoryAuditLogSerializer
    permission_classes = [IsAuthenticated, IsInventoryAdmin]
