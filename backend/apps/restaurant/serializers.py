"""
Restaurant Vertical Serializers.
"""
from rest_framework import serializers
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta

from .models import (
    MenuCategory, MenuItem, OpeningHours, DailySpecial,
    Booking, BookingSettings
)


class MenuItemSerializer(serializers.ModelSerializer):
    """Serializer for MenuItem."""
    category_name = serializers.CharField(source='category.name', read_only=True)
    
    class Meta:
        model = MenuItem
        fields = [
            'id', 'category', 'category_name', 'name', 'description',
            'price', 'dietary_info', 'prep_time_minutes', 'image_url',
            'display_order', 'is_available', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class MenuItemCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating menu items."""
    
    class Meta:
        model = MenuItem
        fields = [
            'id', 'category', 'name', 'description', 'price',
            'dietary_info', 'prep_time_minutes', 'image_url',
            'display_order', 'is_available', 'is_active'
        ]
        read_only_fields = ['id']
    
    def validate_price(self, value):
        if value < Decimal('0.00'):
            raise serializers.ValidationError("Price cannot be negative.")
        return value


class MenuCategorySerializer(serializers.ModelSerializer):
    """Serializer for MenuCategory with nested items."""
    items = MenuItemSerializer(many=True, read_only=True)
    items_count = serializers.SerializerMethodField()
    
    class Meta:
        model = MenuCategory
        fields = [
            'id', 'organization', 'location', 'name', 'description',
            'display_order', 'is_active', 'items', 'items_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_items_count(self, obj):
        return obj.items.filter(is_active=True).count()


class MenuCategoryListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing categories."""
    items_count = serializers.SerializerMethodField()
    location_name = serializers.CharField(source='location.name', read_only=True, allow_null=True)
    
    class Meta:
        model = MenuCategory
        fields = [
            'id', 'organization', 'location', 'location_name',
            'name', 'description', 'display_order', 'is_active',
            'items_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_items_count(self, obj):
        return obj.items.filter(is_active=True).count()


class MenuCategoryCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating menu categories."""
    
    class Meta:
        model = MenuCategory
        fields = [
            'id', 'organization', 'location', 'name', 'description',
            'display_order', 'is_active'
        ]
        read_only_fields = ['id']


class OpeningHoursSerializer(serializers.ModelSerializer):
    """Serializer for OpeningHours."""
    day_name = serializers.CharField(source='get_day_of_week_display', read_only=True)
    
    class Meta:
        model = OpeningHours
        fields = [
            'id', 'location', 'day_of_week', 'day_name',
            'open_time', 'close_time', 'open_time_2', 'close_time_2',
            'is_closed', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class OpeningHoursCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating opening hours."""
    
    class Meta:
        model = OpeningHours
        fields = [
            'id', 'location', 'day_of_week', 'open_time', 'close_time',
            'open_time_2', 'close_time_2', 'is_closed'
        ]
        read_only_fields = ['id']
    
    def validate(self, data):
        if not data.get('is_closed'):
            if not data.get('open_time') or not data.get('close_time'):
                raise serializers.ValidationError(
                    "Open time and close time are required when not closed."
                )
            if data['open_time'] >= data['close_time']:
                raise serializers.ValidationError(
                    "Close time must be after open time."
                )
        return data


class DailySpecialSerializer(serializers.ModelSerializer):
    """Serializer for DailySpecial."""
    is_available_today = serializers.BooleanField(read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True, allow_null=True)
    discount_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = DailySpecial
        fields = [
            'id', 'organization', 'location', 'location_name',
            'name', 'description', 'price', 'original_price',
            'discount_percentage', 'start_date', 'end_date',
            'recurring_days', 'is_active', 'is_available_today',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_discount_percentage(self, obj):
        if obj.original_price and obj.original_price > obj.price:
            discount = ((obj.original_price - obj.price) / obj.original_price) * 100
            return round(discount, 0)
        return None


class DailySpecialCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating daily specials."""
    
    class Meta:
        model = DailySpecial
        fields = [
            'id', 'organization', 'location', 'name', 'description',
            'price', 'original_price', 'start_date', 'end_date',
            'recurring_days', 'is_active'
        ]
        read_only_fields = ['id']
    
    def validate(self, data):
        if data.get('end_date') and data.get('start_date'):
            if data['end_date'] < data['start_date']:
                raise serializers.ValidationError(
                    "End date must be after or equal to start date."
                )
        return data


class BookingSerializer(serializers.ModelSerializer):
    """Serializer for Booking."""
    location_name = serializers.CharField(source='location.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    source_display = serializers.CharField(source='get_source_display', read_only=True)
    confirmed_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Booking
        fields = [
            'id', 'organization', 'location', 'location_name', 'conversation',
            'booking_date', 'booking_time', 'party_size',
            'customer_name', 'customer_email', 'customer_phone',
            'special_requests', 'status', 'status_display',
            'source', 'source_display', 'confirmation_code',
            'confirmed_at', 'confirmed_by', 'confirmed_by_name',
            'cancelled_at', 'cancellation_reason', 'internal_notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'confirmation_code', 'confirmed_at', 'confirmed_by',
            'cancelled_at', 'created_at', 'updated_at'
        ]
    
    def get_confirmed_by_name(self, obj):
        if obj.confirmed_by:
            return f"{obj.confirmed_by.first_name} {obj.confirmed_by.last_name}".strip() or obj.confirmed_by.email
        return None


class BookingCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating bookings."""
    
    class Meta:
        model = Booking
        fields = [
            'id', 'organization', 'location', 'conversation',
            'booking_date', 'booking_time', 'party_size',
            'customer_name', 'customer_email', 'customer_phone',
            'special_requests', 'source', 'confirmation_code'
        ]
        read_only_fields = ['id', 'confirmation_code']
    
    def validate(self, data):
        # Get booking settings if available
        location = data.get('location')
        booking_date = data.get('booking_date')
        booking_time = data.get('booking_time')
        party_size = data.get('party_size')
        
        if location:
            try:
                settings = location.booking_settings
                
                # Validate party size
                if party_size > settings.max_party_size:
                    raise serializers.ValidationError({
                        'party_size': f"Maximum party size is {settings.max_party_size}."
                    })
                
                # Validate advance booking
                if booking_date and booking_time:
                    from datetime import datetime
                    booking_datetime = datetime.combine(booking_date, booking_time)
                    booking_datetime = timezone.make_aware(booking_datetime)
                    
                    min_booking_time = timezone.now() + timedelta(hours=settings.min_advance_hours)
                    if booking_datetime < min_booking_time:
                        raise serializers.ValidationError({
                            'booking_time': f"Bookings must be made at least {settings.min_advance_hours} hours in advance."
                        })
                    
                    max_booking_date = timezone.now().date() + timedelta(days=settings.max_advance_days)
                    if booking_date > max_booking_date:
                        raise serializers.ValidationError({
                            'booking_date': f"Bookings can only be made up to {settings.max_advance_days} days in advance."
                        })
                        
            except BookingSettings.DoesNotExist:
                pass  # No settings configured, allow booking
        
        return data
    
    def create(self, validated_data):
        booking = super().create(validated_data)
        
        # Auto-confirm if setting is enabled
        try:
            settings = booking.location.booking_settings
            if settings.auto_confirm:
                booking.confirm()
        except BookingSettings.DoesNotExist:
            # Default: auto-confirm
            booking.confirm()
        
        return booking


class BookingUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating bookings."""
    
    class Meta:
        model = Booking
        fields = [
            'booking_date', 'booking_time', 'party_size',
            'customer_name', 'customer_email', 'customer_phone',
            'special_requests', 'status', 'internal_notes'
        ]


class BookingSettingsSerializer(serializers.ModelSerializer):
    """Serializer for BookingSettings."""
    location_name = serializers.CharField(source='location.name', read_only=True)
    
    class Meta:
        model = BookingSettings
        fields = [
            'id', 'location', 'location_name',
            'max_party_size', 'max_bookings_per_slot', 'total_capacity',
            'slot_duration_minutes', 'booking_buffer_minutes',
            'min_advance_hours', 'max_advance_days',
            'auto_confirm', 'cancellation_hours',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class BookingSettingsCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating booking settings."""
    
    class Meta:
        model = BookingSettings
        fields = [
            'id', 'location', 'max_party_size', 'max_bookings_per_slot',
            'total_capacity', 'slot_duration_minutes', 'booking_buffer_minutes',
            'min_advance_hours', 'max_advance_days',
            'auto_confirm', 'cancellation_hours'
        ]
        read_only_fields = ['id']


# Widget-facing serializers (public, limited data)
class PublicMenuCategorySerializer(serializers.ModelSerializer):
    """Public serializer for menu categories (widget use)."""
    items = serializers.SerializerMethodField()
    
    class Meta:
        model = MenuCategory
        fields = ['id', 'name', 'description', 'items']
    
    def get_items(self, obj):
        items = obj.items.filter(is_active=True, is_available=True)
        return PublicMenuItemSerializer(items, many=True).data


class PublicMenuItemSerializer(serializers.ModelSerializer):
    """Public serializer for menu items (widget use)."""
    
    class Meta:
        model = MenuItem
        fields = [
            'id', 'name', 'description', 'price',
            'dietary_info', 'image_url'
        ]


class PublicDailySpecialSerializer(serializers.ModelSerializer):
    """Public serializer for daily specials (widget use)."""
    
    class Meta:
        model = DailySpecial
        fields = [
            'id', 'name', 'description', 'price', 'original_price'
        ]


class PublicOpeningHoursSerializer(serializers.ModelSerializer):
    """Public serializer for opening hours (widget use)."""
    day_name = serializers.CharField(source='get_day_of_week_display', read_only=True)
    
    class Meta:
        model = OpeningHours
        fields = [
            'day_of_week', 'day_name', 'open_time', 'close_time',
            'open_time_2', 'close_time_2', 'is_closed'
        ]


class BookingAvailabilitySerializer(serializers.Serializer):
    """Serializer for checking booking availability."""
    location_id = serializers.UUIDField()
    date = serializers.DateField()
    party_size = serializers.IntegerField(min_value=1)


class BookingSlotSerializer(serializers.Serializer):
    """Serializer for available booking slots."""
    time = serializers.TimeField()
    available = serializers.BooleanField()
    remaining_capacity = serializers.IntegerField()
