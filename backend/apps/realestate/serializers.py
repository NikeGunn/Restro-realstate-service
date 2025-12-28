"""
Real Estate Vertical Serializers.
"""
from rest_framework import serializers
from decimal import Decimal
from django.utils import timezone

from .models import PropertyListing, Lead, Appointment


class PropertyListingSerializer(serializers.ModelSerializer):
    """Serializer for PropertyListing."""
    full_address = serializers.CharField(read_only=True)
    listing_type_display = serializers.CharField(source='get_listing_type_display', read_only=True)
    property_type_display = serializers.CharField(source='get_property_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True, allow_null=True)
    leads_count = serializers.SerializerMethodField()
    
    class Meta:
        model = PropertyListing
        fields = [
            'id', 'organization', 'location', 'location_name',
            'title', 'description', 'listing_type', 'listing_type_display',
            'property_type', 'property_type_display', 'reference_number',
            'price', 'price_per_sqft', 'rent_period',
            'address_line1', 'address_line2', 'city', 'state',
            'postal_code', 'country', 'neighborhood', 'full_address',
            'latitude', 'longitude',
            'bedrooms', 'bathrooms', 'square_feet', 'lot_size',
            'year_built', 'parking_spaces',
            'features', 'amenities', 'images', 'virtual_tour_url',
            'agent_name', 'agent_phone', 'agent_email',
            'status', 'status_display', 'is_featured', 'is_published',
            'listed_date', 'sold_date', 'leads_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'reference_number', 'created_at', 'updated_at']
    
    def get_leads_count(self, obj):
        return obj.leads.count()


class PropertyListingCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating property listings."""
    
    class Meta:
        model = PropertyListing
        fields = [
            'id', 'organization', 'location', 'title', 'description',
            'listing_type', 'property_type', 'price', 'price_per_sqft',
            'rent_period', 'address_line1', 'address_line2', 'city',
            'state', 'postal_code', 'country', 'neighborhood',
            'latitude', 'longitude', 'bedrooms', 'bathrooms',
            'square_feet', 'lot_size', 'year_built', 'parking_spaces',
            'features', 'amenities', 'images', 'virtual_tour_url',
            'agent_name', 'agent_phone', 'agent_email',
            'status', 'is_featured', 'is_published', 'listed_date', 'sold_date'
        ]
        read_only_fields = ['id']
    
    def validate_price(self, value):
        if value < Decimal('0.00'):
            raise serializers.ValidationError("Price cannot be negative.")
        return value


class PropertyListingListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing properties."""
    listing_type_display = serializers.CharField(source='get_listing_type_display', read_only=True)
    property_type_display = serializers.CharField(source='get_property_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    primary_image = serializers.SerializerMethodField()
    
    class Meta:
        model = PropertyListing
        fields = [
            'id', 'title', 'listing_type', 'listing_type_display',
            'property_type', 'property_type_display', 'reference_number',
            'price', 'city', 'state', 'neighborhood',
            'bedrooms', 'bathrooms', 'square_feet',
            'status', 'status_display', 'is_featured', 'primary_image',
            'created_at'
        ]
    
    def get_primary_image(self, obj):
        if obj.images and len(obj.images) > 0:
            return obj.images[0]
        return None


class LeadSerializer(serializers.ModelSerializer):
    """Serializer for Lead."""
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    intent_display = serializers.CharField(source='get_intent_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    source_display = serializers.CharField(source='get_source_display', read_only=True)
    assigned_to_name = serializers.SerializerMethodField()
    property_title = serializers.SerializerMethodField()
    location_name = serializers.CharField(source='location.name', read_only=True, allow_null=True)
    appointments_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Lead
        fields = [
            'id', 'organization', 'location', 'location_name',
            'conversation', 'property_listing', 'property_title',
            'name', 'email', 'phone',
            'intent', 'intent_display', 'status', 'status_display',
            'priority', 'priority_display', 'source', 'source_display',
            'budget_min', 'budget_max',
            'preferred_areas', 'preferred_property_types',
            'bedrooms_min', 'bedrooms_max', 'timeline',
            'assigned_to', 'assigned_to_name', 'notes',
            'qualification_data', 'lead_score',
            'appointments_count',
            'created_at', 'updated_at', 'contacted_at', 'converted_at'
        ]
        read_only_fields = [
            'id', 'lead_score', 'created_at', 'updated_at',
            'contacted_at', 'converted_at'
        ]
    
    def get_assigned_to_name(self, obj):
        if obj.assigned_to:
            return f"{obj.assigned_to.first_name} {obj.assigned_to.last_name}".strip() or obj.assigned_to.email
        return None
    
    def get_property_title(self, obj):
        if obj.property_listing:
            return obj.property_listing.title
        return None
    
    def get_appointments_count(self, obj):
        return obj.appointments.count()


class LeadCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating leads."""
    
    class Meta:
        model = Lead
        fields = [
            'id', 'organization', 'location', 'conversation', 'property_listing',
            'name', 'email', 'phone', 'intent', 'source',
            'budget_min', 'budget_max',
            'preferred_areas', 'preferred_property_types',
            'bedrooms_min', 'bedrooms_max', 'timeline', 'notes'
        ]
        read_only_fields = ['id']
    
    def validate_phone(self, value):
        if not value:
            raise serializers.ValidationError("Phone number is required.")
        return value
    
    def create(self, validated_data):
        lead = super().create(validated_data)
        lead.calculate_score()  # Calculate initial lead score
        return lead


class LeadUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating leads."""
    
    class Meta:
        model = Lead
        fields = [
            'location', 'property_listing', 'name', 'email', 'phone',
            'intent', 'status', 'priority', 'source',
            'budget_min', 'budget_max',
            'preferred_areas', 'preferred_property_types',
            'bedrooms_min', 'bedrooms_max', 'timeline',
            'assigned_to', 'notes', 'qualification_data'
        ]


class LeadListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing leads."""
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    intent_display = serializers.CharField(source='get_intent_display', read_only=True)
    assigned_to_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Lead
        fields = [
            'id', 'name', 'email', 'phone',
            'intent', 'intent_display', 'status', 'status_display',
            'priority', 'priority_display', 'lead_score',
            'assigned_to', 'assigned_to_name',
            'created_at', 'contacted_at'
        ]
    
    def get_assigned_to_name(self, obj):
        if obj.assigned_to:
            return f"{obj.assigned_to.first_name} {obj.assigned_to.last_name}".strip() or obj.assigned_to.email
        return None


class AppointmentSerializer(serializers.ModelSerializer):
    """Serializer for Appointment."""
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    appointment_type_display = serializers.CharField(source='get_appointment_type_display', read_only=True)
    lead_name = serializers.CharField(source='lead.name', read_only=True)
    lead_phone = serializers.CharField(source='lead.phone', read_only=True)
    property_title = serializers.SerializerMethodField()
    property_address = serializers.SerializerMethodField()
    assigned_agent_name = serializers.SerializerMethodField()
    location_name = serializers.CharField(source='location.name', read_only=True, allow_null=True)
    
    class Meta:
        model = Appointment
        fields = [
            'id', 'organization', 'location', 'location_name',
            'lead', 'lead_name', 'lead_phone',
            'property_listing', 'property_title', 'property_address',
            'conversation',
            'appointment_type', 'appointment_type_display',
            'appointment_date', 'appointment_time', 'duration_minutes',
            'meeting_location', 'virtual_meeting_url',
            'status', 'status_display',
            'assigned_agent', 'assigned_agent_name',
            'notes', 'outcome', 'confirmation_code',
            'confirmed_at', 'reminder_sent',
            'created_at', 'updated_at', 'cancelled_at', 'cancellation_reason'
        ]
        read_only_fields = [
            'id', 'confirmation_code', 'confirmed_at',
            'reminder_sent', 'reminder_sent_at',
            'created_at', 'updated_at', 'cancelled_at'
        ]
    
    def get_property_title(self, obj):
        if obj.property_listing:
            return obj.property_listing.title
        return None
    
    def get_property_address(self, obj):
        if obj.property_listing:
            return obj.property_listing.full_address
        return None
    
    def get_assigned_agent_name(self, obj):
        if obj.assigned_agent:
            return f"{obj.assigned_agent.first_name} {obj.assigned_agent.last_name}".strip() or obj.assigned_agent.email
        return None


class AppointmentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating appointments."""
    
    class Meta:
        model = Appointment
        fields = [
            'id', 'organization', 'location', 'lead', 'property_listing',
            'conversation', 'appointment_type',
            'appointment_date', 'appointment_time', 'duration_minutes',
            'meeting_location', 'virtual_meeting_url',
            'assigned_agent', 'notes'
        ]
        read_only_fields = ['id']
    
    def validate(self, data):
        appointment_date = data.get('appointment_date')
        appointment_time = data.get('appointment_time')
        
        if appointment_date and appointment_time:
            from datetime import datetime
            appointment_datetime = datetime.combine(appointment_date, appointment_time)
            appointment_datetime = timezone.make_aware(appointment_datetime)
            
            if appointment_datetime < timezone.now():
                raise serializers.ValidationError({
                    'appointment_date': "Appointment cannot be in the past."
                })
        
        return data


class AppointmentUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating appointments."""
    
    class Meta:
        model = Appointment
        fields = [
            'property_listing', 'appointment_type',
            'appointment_date', 'appointment_time', 'duration_minutes',
            'meeting_location', 'virtual_meeting_url',
            'assigned_agent', 'notes', 'outcome', 'status'
        ]


# Public Widget Serializers
class PublicPropertyListingSerializer(serializers.ModelSerializer):
    """Public serializer for property listings (widget use)."""
    listing_type_display = serializers.CharField(source='get_listing_type_display', read_only=True)
    property_type_display = serializers.CharField(source='get_property_type_display', read_only=True)
    primary_image = serializers.SerializerMethodField()
    
    class Meta:
        model = PropertyListing
        fields = [
            'id', 'title', 'description',
            'listing_type', 'listing_type_display',
            'property_type', 'property_type_display',
            'price', 'rent_period',
            'city', 'state', 'neighborhood',
            'bedrooms', 'bathrooms', 'square_feet',
            'features', 'primary_image', 'images',
            'is_featured'
        ]
    
    def get_primary_image(self, obj):
        if obj.images and len(obj.images) > 0:
            return obj.images[0]
        return None


class LeadCaptureSerializer(serializers.Serializer):
    """Serializer for capturing leads from widget."""
    widget_key = serializers.UUIDField()
    name = serializers.CharField(max_length=255)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20)
    intent = serializers.ChoiceField(
        choices=Lead.IntentType.choices,
        default=Lead.IntentType.GENERAL
    )
    property_id = serializers.UUIDField(required=False, allow_null=True)
    budget_min = serializers.DecimalField(
        max_digits=15, decimal_places=2, required=False, allow_null=True
    )
    budget_max = serializers.DecimalField(
        max_digits=15, decimal_places=2, required=False, allow_null=True
    )
    preferred_areas = serializers.ListField(
        child=serializers.CharField(), required=False
    )
    timeline = serializers.CharField(max_length=100, required=False, allow_blank=True)
    message = serializers.CharField(required=False, allow_blank=True)
