"""
Restaurant Vertical Admin Configuration.
"""
from django.contrib import admin
from .models import (
    MenuCategory, MenuItem, OpeningHours, DailySpecial,
    Booking, BookingSettings, MenuPromoRule
)


@admin.register(MenuCategory)
class MenuCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'organization', 'location', 'display_order', 'is_active']
    list_filter = ['organization', 'is_active']
    search_fields = ['name', 'organization__name']
    ordering = ['organization', 'display_order', 'name']


class MenuPromoRuleInline(admin.StackedInline):
    model = MenuPromoRule
    extra = 0
    autocomplete_fields = ['linked_menu_items']
    readonly_fields = ['organization', 'created_at']


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'category', 'price', 'item_type', 'is_alcohol',
        'sold_out', 'is_available', 'is_active'
    ]
    list_filter = [
        'category__organization', 'category', 'item_type', 'is_alcohol',
        'sold_out', 'is_available', 'is_active'
    ]
    search_fields = ['name', 'description', 'alcohol_brand']
    ordering = ['category', 'display_order', 'name']
    inlines = [MenuPromoRuleInline]


@admin.register(MenuPromoRule)
class MenuPromoRuleAdmin(admin.ModelAdmin):
    list_display = [
        'menu_item', 'organization', 'promo_type',
        'sales_quantity_multiplier', 'revenue_multiplier',
        'inventory_deduction_multiplier'
    ]
    list_filter = ['organization', 'promo_type']
    search_fields = ['menu_item__name', 'notes']
    autocomplete_fields = ['linked_menu_items']
    readonly_fields = ['organization', 'created_at']


@admin.register(OpeningHours)
class OpeningHoursAdmin(admin.ModelAdmin):
    list_display = ['location', 'day_of_week', 'open_time', 'close_time', 'is_closed']
    list_filter = ['location__organization', 'location', 'day_of_week', 'is_closed']
    ordering = ['location', 'day_of_week']


@admin.register(DailySpecial)
class DailySpecialAdmin(admin.ModelAdmin):
    list_display = ['name', 'organization', 'price', 'start_date', 'end_date', 'is_active']
    list_filter = ['organization', 'is_active', 'start_date']
    search_fields = ['name', 'description']
    ordering = ['-start_date', 'name']


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = [
        'confirmation_code', 'customer_name', 'location',
        'booking_date', 'booking_time', 'party_size', 'status'
    ]
    list_filter = ['organization', 'location', 'status', 'source', 'booking_date']
    search_fields = ['customer_name', 'customer_email', 'customer_phone', 'confirmation_code']
    ordering = ['-booking_date', '-booking_time']
    readonly_fields = ['confirmation_code', 'confirmed_at', 'cancelled_at', 'created_at']
    
    fieldsets = (
        ('Booking Details', {
            'fields': (
                'confirmation_code', 'organization', 'location',
                'booking_date', 'booking_time', 'party_size'
            )
        }),
        ('Customer Information', {
            'fields': ('customer_name', 'customer_email', 'customer_phone')
        }),
        ('Requests & Notes', {
            'fields': ('special_requests', 'internal_notes')
        }),
        ('Status', {
            'fields': (
                'status', 'source', 'conversation',
                'confirmed_at', 'confirmed_by', 'cancelled_at', 'cancellation_reason'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )


@admin.register(BookingSettings)
class BookingSettingsAdmin(admin.ModelAdmin):
    list_display = ['location', 'max_party_size', 'total_capacity', 'auto_confirm']
    list_filter = ['location__organization', 'auto_confirm']
