"""
Restaurant Vertical URLs.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    MenuCategoryViewSet, MenuItemViewSet, OpeningHoursViewSet,
    DailySpecialViewSet, BookingViewSet, BookingSettingsViewSet,
    MenuPromoRuleViewSet,
    BookingAvailabilityView, PublicMenuView, PublicSpecialsView, PublicHoursView
)

app_name = 'restaurant'

router = DefaultRouter()
router.register(r'categories', MenuCategoryViewSet, basename='menu-category')
router.register(r'items', MenuItemViewSet, basename='menu-item')
router.register(r'hours', OpeningHoursViewSet, basename='opening-hours')
router.register(r'specials', DailySpecialViewSet, basename='daily-special')
router.register(r'bookings', BookingViewSet, basename='booking')
router.register(r'booking-settings', BookingSettingsViewSet, basename='booking-settings')
router.register(r'promo-rules', MenuPromoRuleViewSet, basename='menu-promo-rule')

# Nested promo-rule under a menu item: /items/{menu_item_pk}/promo-rule/
promo_rule_list = MenuPromoRuleViewSet.as_view({'get': 'list', 'post': 'create'})
promo_rule_detail = MenuPromoRuleViewSet.as_view({
    'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'
})

urlpatterns = [
    path('', include(router.urls)),
    path('items/<uuid:menu_item_pk>/promo-rule/', promo_rule_list, name='menu-item-promo-rule'),
    path('items/<uuid:menu_item_pk>/promo-rule/<uuid:pk>/', promo_rule_detail,
         name='menu-item-promo-rule-detail'),
    path('availability/', BookingAvailabilityView.as_view(), name='booking-availability'),
    # Public endpoints (for widget)
    path('public/menu/', PublicMenuView.as_view(), name='public-menu'),
    path('public/specials/', PublicSpecialsView.as_view(), name='public-specials'),
    path('public/hours/', PublicHoursView.as_view(), name='public-hours'),
]
