"""
Restaurant Vertical Models.

Models for restaurant-specific features:
- MenuCategory: Categories for menu items (e.g., Appetizers, Mains, Desserts)
- MenuItem: Individual menu items with prices and descriptions
- OpeningHours: Operating hours for each day of the week
- DailySpecial: Special menu items for specific dates
- Booking: Restaurant reservations
"""
import uuid
from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from apps.accounts.models import Organization, Location


class MenuCategory(models.Model):
    """
    Menu category for organizing menu items.
    Examples: Appetizers, Main Courses, Desserts, Beverages
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='menu_categories'
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='menu_categories',
        help_text='If set, this category is specific to this location only'
    )
    
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    # Ordering
    display_order = models.PositiveIntegerField(default=0)
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'restaurant_menu_categories'
        ordering = ['display_order', 'name']
        verbose_name = 'Menu Category'
        verbose_name_plural = 'Menu Categories'
        indexes = [
            models.Index(fields=['organization', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.organization.name}"


class MenuItem(models.Model):
    """
    Individual menu item with price and details.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.ForeignKey(
        MenuCategory,
        on_delete=models.CASCADE,
        related_name='items'
    )
    
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    # Pricing
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    # Dietary information (stored as JSON for flexibility)
    dietary_info = models.JSONField(
        default=dict,
        blank=True,
        help_text='Dietary flags: vegetarian, vegan, gluten_free, contains_nuts, etc.'
    )
    
    # Preparation time in minutes (optional)
    prep_time_minutes = models.PositiveIntegerField(null=True, blank=True)
    
    # Image (optional)
    image_url = models.URLField(blank=True)
    
    # Ordering
    display_order = models.PositiveIntegerField(default=0)
    
    # Availability
    is_available = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'restaurant_menu_items'
        ordering = ['display_order', 'name']
        verbose_name = 'Menu Item'
        verbose_name_plural = 'Menu Items'
        indexes = [
            models.Index(fields=['category', 'is_active', 'is_available']),
        ]
    
    def __str__(self):
        return f"{self.name} - ${self.price}"
    
    @property
    def organization(self):
        return self.category.organization


class OpeningHours(models.Model):
    """
    Operating hours for a location.
    Supports different hours for each day of the week.
    """
    class DayOfWeek(models.IntegerChoices):
        MONDAY = 0, 'Monday'
        TUESDAY = 1, 'Tuesday'
        WEDNESDAY = 2, 'Wednesday'
        THURSDAY = 3, 'Thursday'
        FRIDAY = 4, 'Friday'
        SATURDAY = 5, 'Saturday'
        SUNDAY = 6, 'Sunday'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        related_name='opening_hours'
    )
    
    day_of_week = models.IntegerField(choices=DayOfWeek.choices)
    
    # Opening time (null = closed)
    open_time = models.TimeField(null=True, blank=True)
    close_time = models.TimeField(null=True, blank=True)
    
    # For split hours (e.g., closed 3-5pm)
    open_time_2 = models.TimeField(null=True, blank=True)
    close_time_2 = models.TimeField(null=True, blank=True)
    
    # Status
    is_closed = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'restaurant_opening_hours'
        ordering = ['location', 'day_of_week']
        unique_together = ['location', 'day_of_week']
        verbose_name = 'Opening Hours'
        verbose_name_plural = 'Opening Hours'
    
    def __str__(self):
        day_name = self.get_day_of_week_display()
        if self.is_closed:
            return f"{self.location.name} - {day_name}: Closed"
        return f"{self.location.name} - {day_name}: {self.open_time} - {self.close_time}"


class DailySpecial(models.Model):
    """
    Daily specials or promotional items.
    Can be scheduled for specific dates or recurring days.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='daily_specials'
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='daily_specials',
        help_text='If set, this special is for this location only'
    )
    
    name = models.CharField(max_length=200)
    description = models.TextField()
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    # Original price for showing discount
    original_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    # Date range for the special
    start_date = models.DateField()
    end_date = models.DateField()
    
    # Optional: recurring on specific days (stored as JSON: [0, 1, 2] for Mon, Tue, Wed)
    recurring_days = models.JSONField(
        default=list,
        blank=True,
        help_text='Days of week (0=Monday, 6=Sunday). Empty = all days in range.'
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'restaurant_daily_specials'
        ordering = ['-start_date', 'name']
        verbose_name = 'Daily Special'
        verbose_name_plural = 'Daily Specials'
    
    def __str__(self):
        return f"{self.name} ({self.start_date} - {self.end_date})"
    
    @property
    def is_available_today(self):
        """Check if special is available today."""
        today = timezone.now().date()
        if not (self.start_date <= today <= self.end_date):
            return False
        if not self.is_active:
            return False
        if self.recurring_days:
            return today.weekday() in self.recurring_days
        return True


class Booking(models.Model):
    """
    Restaurant table booking/reservation.
    """
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONFIRMED = 'confirmed', 'Confirmed'
        CANCELLED = 'cancelled', 'Cancelled'
        COMPLETED = 'completed', 'Completed'
        NO_SHOW = 'no_show', 'No Show'
    
    class Source(models.TextChoices):
        WEBSITE = 'website', 'Website Widget'
        WHATSAPP = 'whatsapp', 'WhatsApp'
        PHONE = 'phone', 'Phone'
        WALK_IN = 'walk_in', 'Walk-in'
        OTHER = 'other', 'Other'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='restaurant_bookings'
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        related_name='restaurant_bookings'
    )
    
    # Link to conversation (if booking was made via chat)
    conversation = models.ForeignKey(
        'messaging.Conversation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='restaurant_bookings'
    )
    
    # Booking details
    booking_date = models.DateField()
    booking_time = models.TimeField()
    party_size = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(50)]
    )
    
    # Customer information
    customer_name = models.CharField(max_length=255)
    customer_email = models.EmailField(blank=True)
    customer_phone = models.CharField(max_length=20)
    
    # Special requests
    special_requests = models.TextField(blank=True)
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    
    # Source tracking
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.WEBSITE
    )
    
    # Confirmation
    confirmation_code = models.CharField(max_length=20, unique=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='confirmed_bookings'
    )
    
    # Cancellation
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    
    # Notes (staff only)
    internal_notes = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'restaurant_bookings'
        ordering = ['booking_date', 'booking_time']
        verbose_name = 'Booking'
        verbose_name_plural = 'Bookings'
        indexes = [
            models.Index(fields=['organization', 'booking_date', 'status']),
            models.Index(fields=['location', 'booking_date']),
            models.Index(fields=['confirmation_code']),
            models.Index(fields=['customer_phone']),
        ]
    
    def __str__(self):
        return f"{self.customer_name} - {self.booking_date} {self.booking_time} ({self.party_size} guests)"
    
    def save(self, *args, **kwargs):
        # Generate confirmation code if not set
        if not self.confirmation_code:
            self.confirmation_code = self._generate_confirmation_code()
        super().save(*args, **kwargs)
    
    def _generate_confirmation_code(self):
        """Generate a unique confirmation code."""
        import random
        import string
        prefix = 'RES'
        while True:
            code = prefix + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if not Booking.objects.filter(confirmation_code=code).exists():
                return code
    
    def confirm(self, user=None):
        """Confirm the booking."""
        self.status = self.Status.CONFIRMED
        self.confirmed_at = timezone.now()
        self.confirmed_by = user
        self.save(update_fields=['status', 'confirmed_at', 'confirmed_by', 'updated_at'])
    
    def cancel(self, reason=''):
        """Cancel the booking."""
        self.status = self.Status.CANCELLED
        self.cancelled_at = timezone.now()
        self.cancellation_reason = reason
        self.save(update_fields=['status', 'cancelled_at', 'cancellation_reason', 'updated_at'])
    
    def complete(self):
        """Mark booking as completed (guest showed up)."""
        self.status = self.Status.COMPLETED
        self.save(update_fields=['status', 'updated_at'])
    
    def no_show(self):
        """Mark booking as no-show."""
        self.status = self.Status.NO_SHOW
        self.save(update_fields=['status', 'updated_at'])


class BookingSettings(models.Model):
    """
    Booking configuration for a location.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.OneToOneField(
        Location,
        on_delete=models.CASCADE,
        related_name='booking_settings'
    )
    
    # Capacity
    max_party_size = models.PositiveIntegerField(default=10)
    max_bookings_per_slot = models.PositiveIntegerField(
        default=5,
        help_text='Maximum number of bookings per time slot'
    )
    total_capacity = models.PositiveIntegerField(
        default=50,
        help_text='Total restaurant seating capacity'
    )
    
    # Time slots
    slot_duration_minutes = models.PositiveIntegerField(
        default=30,
        help_text='Duration of each booking slot in minutes'
    )
    booking_buffer_minutes = models.PositiveIntegerField(
        default=15,
        help_text='Buffer time between bookings'
    )
    
    # Advance booking
    min_advance_hours = models.PositiveIntegerField(
        default=2,
        help_text='Minimum hours in advance for booking'
    )
    max_advance_days = models.PositiveIntegerField(
        default=30,
        help_text='Maximum days in advance for booking'
    )
    
    # Auto-confirmation
    auto_confirm = models.BooleanField(
        default=True,
        help_text='Automatically confirm bookings'
    )
    
    # Cancellation policy
    cancellation_hours = models.PositiveIntegerField(
        default=24,
        help_text='Hours before booking that cancellation is allowed'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'restaurant_booking_settings'
        verbose_name = 'Booking Settings'
        verbose_name_plural = 'Booking Settings'
    
    def __str__(self):
        return f"Booking Settings - {self.location.name}"
