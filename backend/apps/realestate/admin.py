"""
Real Estate Vertical Admin Configuration.
"""
import json

from django import forms
from django.contrib import admin, messages
from django.utils.html import format_html

from .admin_photos import MultipleImageField, PhotoManagerWidget, apply_photo_changes, validate_uploads
from .models import PropertyListing, Lead, Appointment


class PropertyListingAdminForm(forms.ModelForm):
    photo_order = forms.CharField(required=False, widget=PhotoManagerWidget, label='Photos')
    new_photos = MultipleImageField(required=False, label='Add photos')

    class Meta:
        model = PropertyListing
        exclude = ['images']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['photo_order'].initial = json.dumps(list(self.instance.images or []) if self.instance.pk else [])
        for name in ('state', 'postal_code', 'address_line2', 'neighborhood'):
            if name in self.fields:
                self.fields[name].required = False
        if 'country' in self.fields and not self.instance.pk:
            self.fields['country'].initial = 'Nepal'
        if 'description' in self.fields:
            self.fields['description'].help_text = 'Shown on kribaat.com and used by the AI agent. Plain text.'

    def clean_photo_order(self):
        raw = self.cleaned_data.get('photo_order') or '[]'
        try:
            urls = json.loads(raw)
        except ValueError:
            raise forms.ValidationError('Photo list was corrupted; reload the page.')
        if not isinstance(urls, list) or not all(isinstance(u, str) for u in urls):
            raise forms.ValidationError('Photo list was corrupted; reload the page.')
        current = set(self.instance.images or []) if self.instance.pk else set()
        return [u for u in urls if u in current]   # never let the form inject foreign URLs

    def clean(self):
        data = super().clean()
        files = data.get('new_photos') or []
        if files:
            try:
                validate_uploads(files, len(data.get('photo_order') or []))
            except forms.ValidationError as e:
                self.add_error('photo_order', e)
        return data


@admin.register(PropertyListing)
class PropertyListingAdmin(admin.ModelAdmin):
    """Owner-facing listing management: everything the website and the AI agent show comes from here."""
    form = PropertyListingAdminForm
    list_display = [
        'thumb', 'reference_number', 'title', 'property_type', 'listing_type', 'price_display', 'city',
        'status', 'is_published', 'is_featured', 'photos', 'view_count', 'whatsapp_clicks', 'public_link',
    ]
    list_display_links = ['thumb', 'reference_number', 'title']
    list_editable = ['status', 'is_published', 'is_featured']
    list_filter = ['organization', 'status', 'listing_type', 'property_type', 'is_featured', 'is_published', 'city']
    search_fields = ['title', 'reference_number', 'address_line1', 'city', 'neighborhood', 'description']
    ordering = ['-created_at']
    list_per_page = 40
    save_on_top = True
    readonly_fields = ['reference_number', 'view_count', 'whatsapp_clicks', 'public_link', 'created_at', 'updated_at']
    actions = ['publish', 'unpublish', 'mark_active', 'mark_rented', 'mark_sold', 'feature', 'unfeature']

    fieldsets = (
        ('Listing', {'fields': ('organization', 'location', 'reference_number', 'public_link', 'title',
                                'description', ('property_type', 'listing_type'), ('status', 'is_published', 'is_featured'))}),
        ('Photos', {'fields': ('photo_order', 'new_photos'),
                    'description': 'Drag & drop to upload and reorder. The first photo is the cover.'}),
        ('Price', {'fields': (('price', 'rent_period'), 'price_per_sqft')}),
        ('Where', {'fields': ('address_line1', 'address_line2', ('neighborhood', 'city'), ('state', 'postal_code', 'country'),
                              ('latitude', 'longitude'))}),
        ('Details', {'fields': (('bedrooms', 'bathrooms', 'parking_spaces'), ('square_feet', 'lot_size', 'year_built'),
                                'features', 'amenities', 'virtual_tour_url')}),
        ('Agent', {'fields': (('agent_name', 'agent_phone', 'agent_email'),), 'classes': ('collapse',)}),
        ('Engagement & dates', {'fields': (('view_count', 'whatsapp_clicks'), ('listed_date', 'sold_date'),
                                           ('created_at', 'updated_at')), 'classes': ('collapse',)}),
    )

    # ---- columns
    @admin.display(description='')
    def thumb(self, obj):
        url = (obj.images or [None])[0]
        if not url:
            return format_html('<span style="display:inline-block;width:64px;height:48px;border-radius:6px;'
                               'background:#eee;text-align:center;line-height:48px;color:#999">-</span>')
        return format_html('<img src="{}" alt="" loading="lazy" style="width:64px;height:48px;object-fit:cover;'
                           'border-radius:6px">', url)

    @admin.display(description='Price', ordering='price')
    def price_display(self, obj):
        from .public_site import price_text
        return price_text(obj)

    @admin.display(description='Photos')
    def photos(self, obj):
        return len(obj.images or [])

    @admin.display(description='Public page')
    def public_link(self, obj):
        if not obj.pk or not obj.reference_number:
            return '-'
        from .public_site import canonical_path
        label = 'View on website ↗' if obj.is_published and obj.status in ('active', 'coming_soon') else 'Preview ↗'
        return format_html('<a href="{}" target="_blank" rel="noopener">{}</a>', canonical_path(obj), label)

    # ---- save: model first (new listings need an id for photo paths), then photos
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        added, failed = apply_photo_changes(obj, form.cleaned_data.get('photo_order') or [],
                                            form.cleaned_data.get('new_photos') or [])
        if added:
            self.message_user(request, f'{added} photo(s) uploaded.', messages.SUCCESS)
        for msg in failed:
            self.message_user(request, f'Photo not uploaded: {msg}', messages.ERROR)

    # ---- bulk actions
    def _bulk(self, request, queryset, label, **fields):
        n = queryset.update(**fields)
        self.message_user(request, f'{n} listing(s) {label}.', messages.SUCCESS)

    @admin.action(description='Publish on website')
    def publish(self, request, qs):
        self._bulk(request, qs, 'published', is_published=True)

    @admin.action(description='Hide from website')
    def unpublish(self, request, qs):
        self._bulk(request, qs, 'hidden', is_published=False)

    @admin.action(description='Mark active (available)')
    def mark_active(self, request, qs):
        self._bulk(request, qs, 'marked active', status=PropertyListing.Status.ACTIVE)

    @admin.action(description='Mark rented')
    def mark_rented(self, request, qs):
        self._bulk(request, qs, 'marked rented', status=PropertyListing.Status.RENTED)

    @admin.action(description='Mark sold')
    def mark_sold(self, request, qs):
        self._bulk(request, qs, 'marked sold', status=PropertyListing.Status.SOLD)

    @admin.action(description='Feature')
    def feature(self, request, qs):
        self._bulk(request, qs, 'featured', is_featured=True)

    @admin.action(description='Remove feature')
    def unfeature(self, request, qs):
        self._bulk(request, qs, 'unfeatured', is_featured=False)


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
    readonly_fields = ['confirmation_code', 'confirmed_at', 'reminder_sent_at', 'followup_sent_at',
                       'created_at', 'updated_at', 'cancelled_at']
    
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
            'fields': ('confirmed_at', 'reminder_sent', 'reminder_sent_at', 'followup_sent_at')
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
