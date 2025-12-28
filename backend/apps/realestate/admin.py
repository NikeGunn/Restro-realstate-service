"""
Real Estate Vertical Admin Configuration.
"""
from django.contrib import admin
from .models import PropertyListing, Lead, Appointment


@admin.register(PropertyListing)
class PropertyListingAdmin(admin.ModelAdmin):
    list_display = [
        'reference_number', 'title', 'listing_type', 'property_type',
        'price', 'city', 'status', 'is_featured'
    ]
    list_filter = [
        'organization', 'status', 'listing_type', 'property_type',
        'is_featured', 'is_published'
    ]
    search_fields = ['title', 'reference_number', 'address_line1', 'city']
    ordering = ['-created_at']
    readonly_fields = ['reference_number', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Info', {
            'fields': (
                'organization', 'location', 'reference_number',
                'title', 'description', 'listing_type', 'property_type'
            )
        }),
        ('Pricing', {
            'fields': ('price', 'price_per_sqft', 'rent_period')
        }),
        ('Location', {
            'fields': (
                'address_line1', 'address_line2', 'city', 'state',
                'postal_code', 'country', 'neighborhood',
                'latitude', 'longitude'
            )
        }),
        ('Property Details', {
            'fields': (
                'bedrooms', 'bathrooms', 'square_feet', 'lot_size',
                'year_built', 'parking_spaces'
            )
        }),
        ('Features', {
            'fields': ('features', 'amenities', 'images', 'virtual_tour_url')
        }),
        ('Agent Info', {
            'fields': ('agent_name', 'agent_phone', 'agent_email')
        }),
        ('Status', {
            'fields': (
                'status', 'is_featured', 'is_published',
                'listed_date', 'sold_date'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'phone', 'intent', 'status', 'priority',
        'lead_score', 'assigned_to', 'created_at'
    ]
    list_filter = [
        'organization', 'status', 'priority', 'intent', 'source'
    ]
    search_fields = ['name', 'email', 'phone']
    ordering = ['-created_at']
    readonly_fields = ['lead_score', 'created_at', 'updated_at', 'contacted_at', 'converted_at']
    
    fieldsets = (
        ('Contact Info', {
            'fields': ('organization', 'location', 'name', 'email', 'phone')
        }),
        ('Lead Details', {
            'fields': (
                'intent', 'status', 'priority', 'source',
                'conversation', 'property_listing'
            )
        }),
        ('Preferences', {
            'fields': (
                'budget_min', 'budget_max',
                'preferred_areas', 'preferred_property_types',
                'bedrooms_min', 'bedrooms_max', 'timeline'
            )
        }),
        ('Assignment & Notes', {
            'fields': ('assigned_to', 'notes', 'qualification_data')
        }),
        ('Scoring', {
            'fields': ('lead_score',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'contacted_at', 'converted_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = [
        'confirmation_code', 'lead', 'appointment_type',
        'appointment_date', 'appointment_time', 'status', 'assigned_agent'
    ]
    list_filter = [
        'organization', 'status', 'appointment_type', 'appointment_date'
    ]
    search_fields = ['confirmation_code', 'lead__name', 'lead__phone']
    ordering = ['appointment_date', 'appointment_time']
    readonly_fields = ['confirmation_code', 'confirmed_at', 'created_at', 'updated_at', 'cancelled_at']
    
    fieldsets = (
        ('Appointment Details', {
            'fields': (
                'organization', 'location', 'confirmation_code',
                'lead', 'property_listing', 'conversation'
            )
        }),
        ('Schedule', {
            'fields': (
                'appointment_type', 'appointment_date', 'appointment_time',
                'duration_minutes', 'meeting_location', 'virtual_meeting_url'
            )
        }),
        ('Assignment', {
            'fields': ('assigned_agent', 'status')
        }),
        ('Notes', {
            'fields': ('notes', 'outcome')
        }),
        ('Confirmation', {
            'fields': ('confirmed_at', 'reminder_sent')
        }),
        ('Cancellation', {
            'fields': ('cancelled_at', 'cancellation_reason'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
