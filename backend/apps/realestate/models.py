"""
Real Estate Vertical Models.

Models for real estate-specific features:
- PropertyListing: Property listings with details
- Lead: Captured leads from chat interactions  
- Appointment: Property viewing appointments
"""
import uuid
from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from apps.accounts.models import Organization, Location


class PropertyListing(models.Model):
    """
    Real estate property listing.
    """
    class ListingType(models.TextChoices):
        SALE = 'sale', 'For Sale'
        RENT = 'rent', 'For Rent'
        LEASE = 'lease', 'For Lease'
    
    class PropertyType(models.TextChoices):
        HOUSE = 'house', 'House'
        APARTMENT = 'apartment', 'Apartment'
        CONDO = 'condo', 'Condo'
        TOWNHOUSE = 'townhouse', 'Townhouse'
        LAND = 'land', 'Land'
        COMMERCIAL = 'commercial', 'Commercial'
        OFFICE = 'office', 'Office'
        RETAIL = 'retail', 'Retail'
        INDUSTRIAL = 'industrial', 'Industrial'
        OTHER = 'other', 'Other'
    
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        PENDING = 'pending', 'Pending'
        SOLD = 'sold', 'Sold'
        RENTED = 'rented', 'Rented'
        OFF_MARKET = 'off_market', 'Off Market'
        COMING_SOON = 'coming_soon', 'Coming Soon'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='property_listings'
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='property_listings',
        help_text='Office/branch handling this listing'
    )
    
    # Basic Info
    title = models.CharField(max_length=255)
    description = models.TextField()
    listing_type = models.CharField(
        max_length=20,
        choices=ListingType.choices,
        default=ListingType.SALE
    )
    property_type = models.CharField(
        max_length=20,
        choices=PropertyType.choices,
        default=PropertyType.HOUSE
    )
    
    # Reference number (internal)
    reference_number = models.CharField(max_length=50, unique=True)
    
    # Pricing
    price = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    price_per_sqft = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    # For rentals
    rent_period = models.CharField(
        max_length=20,
        blank=True,
        help_text='monthly, weekly, yearly'
    )
    
    # Location/Address
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100, default='USA')
    neighborhood = models.CharField(max_length=100, blank=True)
    
    # Coordinates (optional, for map display)
    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=8,
        null=True,
        blank=True
    )
    longitude = models.DecimalField(
        max_digits=11,
        decimal_places=8,
        null=True,
        blank=True
    )
    
    # Property Details
    bedrooms = models.PositiveIntegerField(null=True, blank=True)
    bathrooms = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        null=True,
        blank=True
    )
    square_feet = models.PositiveIntegerField(null=True, blank=True)
    lot_size = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Lot size in square feet'
    )
    year_built = models.PositiveIntegerField(null=True, blank=True)
    parking_spaces = models.PositiveIntegerField(null=True, blank=True)
    
    # Features (stored as JSON for flexibility)
    features = models.JSONField(
        default=list,
        blank=True,
        help_text='List of features: pool, garage, garden, etc.'
    )
    amenities = models.JSONField(
        default=list,
        blank=True,
        help_text='List of amenities'
    )
    
    # Images (stored as list of URLs)
    images = models.JSONField(
        default=list,
        blank=True,
        help_text='List of image URLs'
    )
    virtual_tour_url = models.URLField(blank=True)
    
    # Agent Info
    agent_name = models.CharField(max_length=255, blank=True)
    agent_phone = models.CharField(max_length=20, blank=True)
    agent_email = models.EmailField(blank=True)
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )
    
    # Visibility
    is_featured = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)
    
    # Dates
    listed_date = models.DateField(null=True, blank=True)
    sold_date = models.DateField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'realestate_property_listings'
        ordering = ['-created_at']
        verbose_name = 'Property Listing'
        verbose_name_plural = 'Property Listings'
        indexes = [
            models.Index(fields=['organization', 'status', 'listing_type']),
            models.Index(fields=['city', 'property_type']),
            models.Index(fields=['price']),
            models.Index(fields=['reference_number']),
        ]
    
    def __str__(self):
        return f"{self.title} - ${self.price:,.0f}"
    
    def save(self, *args, **kwargs):
        if not self.reference_number:
            self.reference_number = self._generate_reference()
        super().save(*args, **kwargs)
    
    def _generate_reference(self):
        """Generate unique reference number."""
        import random
        import string
        prefix = 'PROP'
        while True:
            ref = prefix + ''.join(random.choices(string.digits, k=6))
            if not PropertyListing.objects.filter(reference_number=ref).exists():
                return ref
    
    @property
    def full_address(self):
        parts = [self.address_line1]
        if self.address_line2:
            parts.append(self.address_line2)
        parts.append(f"{self.city}, {self.state} {self.postal_code}")
        return ', '.join(parts)


class Lead(models.Model):
    """
    Captured lead from chat or other sources.
    """
    class Status(models.TextChoices):
        NEW = 'new', 'New'
        CONTACTED = 'contacted', 'Contacted'
        QUALIFIED = 'qualified', 'Qualified'
        UNQUALIFIED = 'unqualified', 'Unqualified'
        CONVERTED = 'converted', 'Converted'
        LOST = 'lost', 'Lost'
    
    class IntentType(models.TextChoices):
        BUY = 'buy', 'Buy'
        RENT = 'rent', 'Rent'
        SELL = 'sell', 'Sell'
        INVEST = 'invest', 'Invest'
        GENERAL = 'general', 'General Inquiry'
    
    class Priority(models.TextChoices):
        LOW = 'low', 'Low'
        MEDIUM = 'medium', 'Medium'
        HIGH = 'high', 'High'
        HOT = 'hot', 'Hot'
    
    class Source(models.TextChoices):
        WEBSITE = 'website', 'Website Widget'
        WHATSAPP = 'whatsapp', 'WhatsApp'
        PHONE = 'phone', 'Phone'
        EMAIL = 'email', 'Email'
        REFERRAL = 'referral', 'Referral'
        WALK_IN = 'walk_in', 'Walk-in'
        OTHER = 'other', 'Other'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='leads'
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='leads',
        help_text='Office handling this lead'
    )
    
    # Link to conversation (if captured via chat)
    conversation = models.ForeignKey(
        'messaging.Conversation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='leads'
    )
    
    # Interested property (if applicable)
    property_listing = models.ForeignKey(
        PropertyListing,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='leads'
    )
    
    # Contact Information
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20)
    
    # Lead Qualification
    intent = models.CharField(
        max_length=20,
        choices=IntentType.choices,
        default=IntentType.GENERAL
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW
    )
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.MEDIUM
    )
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.WEBSITE
    )
    
    # Budget
    budget_min = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True
    )
    budget_max = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    # Property Preferences (from qualification)
    preferred_areas = models.JSONField(
        default=list,
        blank=True,
        help_text='List of preferred neighborhoods/areas'
    )
    preferred_property_types = models.JSONField(
        default=list,
        blank=True,
        help_text='List of preferred property types'
    )
    bedrooms_min = models.PositiveIntegerField(null=True, blank=True)
    bedrooms_max = models.PositiveIntegerField(null=True, blank=True)
    
    # Timeline
    timeline = models.CharField(
        max_length=100,
        blank=True,
        help_text='e.g., "Immediately", "1-3 months", "6+ months"'
    )
    
    # Assignment
    assigned_to = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_leads'
    )
    
    # Notes
    notes = models.TextField(blank=True)
    
    # AI-extracted qualification data
    qualification_data = models.JSONField(
        default=dict,
        blank=True,
        help_text='AI-extracted qualification info from conversation'
    )
    
    # Score (0-100, calculated from qualification)
    lead_score = models.PositiveIntegerField(
        default=0,
        help_text='Lead quality score 0-100'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    contacted_at = models.DateTimeField(null=True, blank=True)
    converted_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'realestate_leads'
        ordering = ['-created_at']
        verbose_name = 'Lead'
        verbose_name_plural = 'Leads'
        indexes = [
            models.Index(fields=['organization', 'status', 'priority']),
            models.Index(fields=['assigned_to', 'status']),
            models.Index(fields=['phone']),
            models.Index(fields=['email']),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.intent} ({self.status})"
    
    def mark_contacted(self):
        """Mark lead as contacted."""
        self.status = self.Status.CONTACTED
        self.contacted_at = timezone.now()
        self.save(update_fields=['status', 'contacted_at', 'updated_at'])
    
    def qualify(self):
        """Mark lead as qualified."""
        self.status = self.Status.QUALIFIED
        self.save(update_fields=['status', 'updated_at'])
    
    def convert(self):
        """Mark lead as converted."""
        self.status = self.Status.CONVERTED
        self.converted_at = timezone.now()
        self.save(update_fields=['status', 'converted_at', 'updated_at'])
    
    def calculate_score(self):
        """Calculate lead score based on qualification data."""
        score = 0
        
        # Has phone (+20)
        if self.phone:
            score += 20
        
        # Has email (+10)
        if self.email:
            score += 10
        
        # Has budget (+15)
        if self.budget_min or self.budget_max:
            score += 15
        
        # Has timeline (+15)
        if self.timeline:
            score += 15
            # Urgent timeline bonus
            if 'immediate' in self.timeline.lower() or 'asap' in self.timeline.lower():
                score += 10
        
        # Has preferred areas (+10)
        if self.preferred_areas:
            score += 10
        
        # Specific property interest (+10)
        if self.property_listing:
            score += 10
        
        # High intent (+10)
        if self.intent in [self.IntentType.BUY, self.IntentType.RENT]:
            score += 10
        
        self.lead_score = min(score, 100)
        self.save(update_fields=['lead_score', 'updated_at'])
        
        # Auto-set priority based on score
        if self.lead_score >= 70:
            self.priority = self.Priority.HOT
        elif self.lead_score >= 50:
            self.priority = self.Priority.HIGH
        elif self.lead_score >= 30:
            self.priority = self.Priority.MEDIUM
        else:
            self.priority = self.Priority.LOW
        self.save(update_fields=['priority', 'updated_at'])


class Appointment(models.Model):
    """
    Property viewing/meeting appointment.
    """
    class Status(models.TextChoices):
        SCHEDULED = 'scheduled', 'Scheduled'
        CONFIRMED = 'confirmed', 'Confirmed'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'
        NO_SHOW = 'no_show', 'No Show'
        RESCHEDULED = 'rescheduled', 'Rescheduled'
    
    class AppointmentType(models.TextChoices):
        VIEWING = 'viewing', 'Property Viewing'
        CONSULTATION = 'consultation', 'Consultation'
        VIRTUAL_TOUR = 'virtual_tour', 'Virtual Tour'
        MEETING = 'meeting', 'Meeting'
        FOLLOW_UP = 'follow_up', 'Follow Up'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='appointments'
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='appointments'
    )
    
    # Related entities
    lead = models.ForeignKey(
        Lead,
        on_delete=models.CASCADE,
        related_name='appointments'
    )
    property_listing = models.ForeignKey(
        PropertyListing,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='appointments'
    )
    conversation = models.ForeignKey(
        'messaging.Conversation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='appointments'
    )
    
    # Appointment Details
    appointment_type = models.CharField(
        max_length=20,
        choices=AppointmentType.choices,
        default=AppointmentType.VIEWING
    )
    appointment_date = models.DateField()
    appointment_time = models.TimeField()
    duration_minutes = models.PositiveIntegerField(default=60)
    
    # Meeting Location (if different from property)
    meeting_location = models.TextField(
        blank=True,
        help_text='Meeting location if different from property address'
    )
    
    # Virtual meeting link (for virtual tours)
    virtual_meeting_url = models.URLField(blank=True)
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SCHEDULED
    )
    
    # Assignment
    assigned_agent = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_appointments'
    )
    
    # Notes
    notes = models.TextField(blank=True)
    outcome = models.TextField(
        blank=True,
        help_text='Notes about the appointment outcome'
    )
    
    # Confirmation
    confirmation_code = models.CharField(max_length=20, unique=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    
    # Reminders
    reminder_sent = models.BooleanField(default=False)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    
    class Meta:
        db_table = 'realestate_appointments'
        ordering = ['appointment_date', 'appointment_time']
        verbose_name = 'Appointment'
        verbose_name_plural = 'Appointments'
        indexes = [
            models.Index(fields=['organization', 'appointment_date', 'status']),
            models.Index(fields=['lead', 'status']),
            models.Index(fields=['assigned_agent', 'appointment_date']),
            models.Index(fields=['confirmation_code']),
        ]
    
    def __str__(self):
        return f"{self.lead.name} - {self.appointment_type} on {self.appointment_date}"
    
    def save(self, *args, **kwargs):
        if not self.confirmation_code:
            self.confirmation_code = self._generate_confirmation_code()
        super().save(*args, **kwargs)
    
    def _generate_confirmation_code(self):
        """Generate unique confirmation code."""
        import random
        import string
        prefix = 'APT'
        while True:
            code = prefix + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if not Appointment.objects.filter(confirmation_code=code).exists():
                return code
    
    def confirm(self):
        """Confirm the appointment."""
        self.status = self.Status.CONFIRMED
        self.confirmed_at = timezone.now()
        self.save(update_fields=['status', 'confirmed_at', 'updated_at'])
    
    def cancel(self, reason=''):
        """Cancel the appointment."""
        self.status = self.Status.CANCELLED
        self.cancelled_at = timezone.now()
        self.cancellation_reason = reason
        self.save(update_fields=['status', 'cancelled_at', 'cancellation_reason', 'updated_at'])
    
    def complete(self, outcome=''):
        """Mark appointment as completed."""
        self.status = self.Status.COMPLETED
        self.outcome = outcome
        self.save(update_fields=['status', 'outcome', 'updated_at'])
    
    def mark_no_show(self):
        """Mark as no-show."""
        self.status = self.Status.NO_SHOW
        self.save(update_fields=['status', 'updated_at'])
    
    @property
    def datetime(self):
        """Get combined datetime."""
        from datetime import datetime
        return datetime.combine(self.appointment_date, self.appointment_time)
