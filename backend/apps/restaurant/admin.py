"""
Restaurant Vertical Admin Configuration.
"""
from django.contrib import admin
from .models import (
    MenuCategory, MenuItem, OpeningHours, DailySpecial,
    Booking, BookingSettings
)


@admin.register(MenuCategory)
class MenuCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'organization', 'location', 'display_order', 'is_active']
    list_filter = ['organization', 'is_active']
    search_fields = ['name', 'organization__name']
    ordering = ['organization', 'display_order', 'name']


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'price', 'is_available', 'is_active']
    list_filter = ['category__organization', 'category', 'is_available', 'is_active']
    search_fields = ['name', 'description']
    ordering = ['category', 'display_order', 'name']


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
