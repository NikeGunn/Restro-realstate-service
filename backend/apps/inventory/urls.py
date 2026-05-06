"""
Inventory URLs — Plane B (admin-only).

ALL routes here require IsInventoryAdmin. There is NO public surface in this
app. If you add a new route, you MUST include permission_classes.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    InventoryCategoryViewSet, SupplierViewSet, InventoryItemViewSet,
    StockMovementViewSet, StockAlertViewSet, InventoryAuditLogViewSet,
)

app_name = 'inventory'

router = DefaultRouter()
router.register(r'categories', InventoryCategoryViewSet, basename='inventory-category')
router.register(r'suppliers', SupplierViewSet, basename='inventory-supplier')
router.register(r'items', InventoryItemViewSet, basename='inventory-item')
router.register(r'movements', StockMovementViewSet, basename='inventory-movement')
router.register(r'alerts', StockAlertViewSet, basename='inventory-alert')
router.register(r'audit-log', InventoryAuditLogViewSet, basename='inventory-audit-log')

urlpatterns = [
    path('', include(router.urls)),
]
