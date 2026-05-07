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
    PurchaseOrderViewSet, RecipeViewSet,
    SalesImportViewSet, SupplierImportViewSet,
    InventoryAIViewSet, InventoryReportViewSet,
    StockTakeViewSet, LocationStockViewSet, LocationItemPricingViewSet,
)

app_name = 'inventory'

router = DefaultRouter()
router.register(r'categories', InventoryCategoryViewSet, basename='inventory-category')
router.register(r'suppliers', SupplierViewSet, basename='inventory-supplier')
router.register(r'items', InventoryItemViewSet, basename='inventory-item')
router.register(r'movements', StockMovementViewSet, basename='inventory-movement')
router.register(r'alerts', StockAlertViewSet, basename='inventory-alert')
router.register(r'audit-log', InventoryAuditLogViewSet, basename='inventory-audit-log')
router.register(r'purchase-orders', PurchaseOrderViewSet, basename='inventory-purchase-order')
router.register(r'recipes', RecipeViewSet, basename='inventory-recipe')
router.register(r'imports/sales', SalesImportViewSet, basename='inventory-sales-import')
router.register(r'imports/purchases', SupplierImportViewSet, basename='inventory-purchase-import')
router.register(r'ai', InventoryAIViewSet, basename='inventory-ai')
router.register(r'reports', InventoryReportViewSet, basename='inventory-report')
router.register(r'stock-takes', StockTakeViewSet, basename='inventory-stock-take')
router.register(r'location-stocks', LocationStockViewSet, basename='inventory-location-stock')
router.register(r'location-pricing', LocationItemPricingViewSet, basename='inventory-location-pricing')

urlpatterns = [
    path('', include(router.urls)),
]
