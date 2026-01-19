"""
Channel configuration models.
Stores API credentials and settings for WhatsApp and Instagram.
Includes Manager Number tracking for priority manager messages.
"""
import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.accounts.models import Organization


class WhatsAppConfig(models.Model):
    """
    WhatsApp Business API configuration.
    Uses Meta's Cloud API or on-premise API.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name='whatsapp_config'
    )
    
    # Meta WhatsApp Business API credentials
    phone_number_id = models.CharField(max_length=50, blank=True)
    business_account_id = models.CharField(max_length=50, blank=True)
    access_token = models.TextField(blank=True, help_text="Meta API access token")
    
    # Webhook verification
    verify_token = models.CharField(
        max_length=100, 
        default=uuid.uuid4,
        help_text="Token for webhook verification"
    )
    webhook_url = models.URLField(blank=True, help_text="Auto-generated webhook URL")
    
    # Status
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'channel_whatsapp_config'
        verbose_name = 'WhatsApp Configuration'
    
    def __str__(self):
        return f"WhatsApp - {self.organization.name}"


class InstagramConfig(models.Model):
    """
    Instagram Messaging API configuration.
    Uses Meta's Instagram Graph API.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name='instagram_config'
    )
    
    # Instagram credentials
    instagram_business_id = models.CharField(max_length=50, blank=True)
    page_id = models.CharField(max_length=50, blank=True, help_text="Linked Facebook page ID")
    access_token = models.TextField(blank=True, help_text="Instagram Graph API token")
    
    # Webhook verification
    verify_token = models.CharField(
        max_length=100,
        default=uuid.uuid4,
        help_text="Token for webhook verification"
    )
    webhook_url = models.URLField(blank=True)
    
    # Status
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'channel_instagram_config'
        verbose_name = 'Instagram Configuration'
    
    def __str__(self):
        return f"Instagram - {self.organization.name}"


class WebhookLog(models.Model):
    """
    Log of incoming webhook events for debugging.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    class Source(models.TextChoices):
        WHATSAPP = 'whatsapp', 'WhatsApp'
        INSTAGRAM = 'instagram', 'Instagram'
    
    source = models.CharField(max_length=20, choices=Source.choices)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    
    # Payload
    headers = models.JSONField(default=dict)
    body = models.JSONField(default=dict)
    
    # Processing status
    is_processed = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'channel_webhook_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['source', 'created_at']),
        ]


class ManagerNumber(models.Model):
    """
    Manager WhatsApp numbers for priority messaging.
    Managers can send commands via WhatsApp that the chatbot will execute.
    Uses the organization's existing WhatsApp config credentials automatically.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='manager_numbers'
    )
    
    # Manager phone number (WhatsApp format: country code + number, e.g., 919876543210)
    phone_number = models.CharField(
        max_length=20,
        help_text="Manager's WhatsApp number with country code (e.g., 919876543210)"
    )
    
    # Manager details
    name = models.CharField(max_length=100, help_text="Manager's name for identification")
    role = models.CharField(
        max_length=50,
        default='manager',
        help_text="Role: manager, owner, supervisor, etc."
    )
    
    # Optional: Link to user account if manager has panel access
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='manager_numbers'
    )
    
    # Permissions - what can this manager do via WhatsApp
    can_update_hours = models.BooleanField(
        default=True,
        help_text="Can update business hours/closing status"
    )
    can_respond_queries = models.BooleanField(
        default=True,
        help_text="Can respond to customer query escalations"
    )
    can_view_bookings = models.BooleanField(
        default=True,
        help_text="Can view and manage bookings"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_message_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'channel_manager_numbers'
        unique_together = ['organization', 'phone_number']
        ordering = ['-is_active', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.phone_number}) - {self.organization.name}"
    
    @classmethod
    def get_by_phone(cls, phone_number: str, organization=None):
        """
        Find manager by phone number.
        Strips formatting and matches with/without country code.
        """
        # Normalize phone number (remove +, spaces, dashes)
        normalized = ''.join(filter(str.isdigit, phone_number))
        
        # Try exact match first
        query = cls.objects.filter(is_active=True)
        if organization:
            query = query.filter(organization=organization)
        
        # Try different formats
        for phone in [normalized, phone_number, f"+{normalized}"]:
            result = query.filter(phone_number__icontains=phone[-10:]).first()
            if result:
                return result
        
        return None


class TemporaryOverride(models.Model):
    """
    Temporary knowledge base overrides from manager messages.
    These take priority over the main knowledge base and auto-expire.
    Examples: "We are closed early today", "No tables available tonight"
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='temporary_overrides'
    )
    
    class OverrideType(models.TextChoices):
        HOURS = 'hours', 'Business Hours'
        AVAILABILITY = 'availability', 'Availability'
        SPECIAL_MESSAGE = 'special_message', 'Special Message'
        MENU = 'menu', 'Menu Update'
        BOOKING = 'booking', 'Booking Status'
        GENERAL = 'general', 'General Info'
    
    class Priority(models.TextChoices):
        LOW = 'low', 'Low'
        MEDIUM = 'medium', 'Medium'
        HIGH = 'high', 'High'
        URGENT = 'urgent', 'Urgent - Show First'
    
    # Override details
    override_type = models.CharField(
        max_length=30,
        choices=OverrideType.choices,
        default=OverrideType.GENERAL
    )
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.HIGH
    )
    
    # The instruction/content
    original_message = models.TextField(
        help_text="Original message from manager"
    )
    processed_content = models.TextField(
        help_text="AI-processed content for customer responses"
    )
    
    # Keywords that trigger this override (e.g., ["hours", "open", "closed"])
    trigger_keywords = models.JSONField(
        default=list,
        help_text="Keywords that activate this override"
    )
    
    # Created by which manager
    created_by_manager = models.ForeignKey(
        ManagerNumber,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='overrides'
    )
    
    # Expiration
    starts_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(
        help_text="When this override expires and normal knowledge resumes"
    )
    auto_expire_on_next_open = models.BooleanField(
        default=True,
        help_text="Auto-expire when business opens next (based on opening hours)"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'channel_temporary_overrides'
        ordering = ['-priority', '-created_at']
        indexes = [
            models.Index(fields=['organization', 'is_active', 'expires_at']),
        ]
    
    def __str__(self):
        return f"{self.override_type}: {self.original_message[:50]}..."
    
    @property
    def is_expired(self) -> bool:
        """Check if this override has expired."""
        return timezone.now() > self.expires_at
    
    @classmethod
    def get_active_overrides(cls, organization, override_type=None):
        """Get all active, non-expired overrides for an organization."""
        query = cls.objects.filter(
            organization=organization,
            is_active=True,
            starts_at__lte=timezone.now(),
            expires_at__gt=timezone.now()
        )
        if override_type:
            query = query.filter(override_type=override_type)
        return query.order_by('-priority', '-created_at')


class ManagerQuery(models.Model):
    """
    Tracks queries that are escalated to managers via WhatsApp.
    When chatbot doesn't know how to respond, it can ask the manager.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='manager_queries'
    )
    
    class Status(models.TextChoices):
        PENDING = 'pending', 'Waiting for Manager'
        ANSWERED = 'answered', 'Manager Responded'
        EXPIRED = 'expired', 'No Response (Expired)'
        CANCELLED = 'cancelled', 'Cancelled'
    
    # Link to the conversation
    conversation = models.ForeignKey(
        'messaging.Conversation',
        on_delete=models.CASCADE,
        related_name='manager_queries'
    )
    
    # Which manager was asked
    manager = models.ForeignKey(
        ManagerNumber,
        on_delete=models.CASCADE,
        related_name='queries'
    )
    
    # The customer's original question
    customer_query = models.TextField()
    
    # Summary sent to manager
    query_summary = models.TextField(
        help_text="Summarized query sent to manager"
    )
    
    # WhatsApp message ID for tracking
    whatsapp_message_id = models.CharField(max_length=255, blank=True)
    
    # Manager's response
    manager_response = models.TextField(blank=True)
    response_received_at = models.DateTimeField(null=True, blank=True)
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    
    # Expiration - how long to wait for manager response
    expires_at = models.DateTimeField()
    
    # Response sent to customer
    customer_response = models.TextField(
        blank=True,
        help_text="Final response sent to customer based on manager's input"
    )
    customer_response_sent = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'channel_manager_queries'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['conversation', 'status']),
            models.Index(fields=['manager', 'status']),
        ]
    
    def __str__(self):
        return f"Query to {self.manager.name}: {self.customer_query[:50]}..."
    
    @property
    def is_expired(self) -> bool:
        """Check if this query has expired without response."""
        return self.status == self.Status.PENDING and timezone.now() > self.expires_at
    
    def mark_answered(self, response: str):
        """Mark query as answered by manager."""
        self.status = self.Status.ANSWERED
        self.manager_response = response
        self.response_received_at = timezone.now()
        self.save()
    
    def mark_expired(self):
        """Mark query as expired (no response received)."""
        self.status = self.Status.EXPIRED
        self.save()


class PendingManagerAction(models.Model):
    """
    Tracks pending manager actions that require confirmation.
    For example: closing when there are confirmed reservations.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='pending_manager_actions'
    )
    manager = models.ForeignKey(
        ManagerNumber,
        on_delete=models.CASCADE,
        related_name='pending_actions'
    )
    
    class ActionType(models.TextChoices):
        CLOSE_WITH_BOOKINGS = 'close_with_bookings', 'Close with active bookings'
        CANCEL_ALL_BOOKINGS = 'cancel_all_bookings', 'Cancel all bookings'
    
    class Status(models.TextChoices):
        PENDING = 'pending', 'Waiting for Confirmation'
        CONFIRMED = 'confirmed', 'Confirmed'
        CANCELLED = 'cancelled', 'Cancelled'
        EXPIRED = 'expired', 'Expired'
    
    action_type = models.CharField(max_length=30, choices=ActionType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    
    # Original message and context
    original_message = models.TextField()
    context_data = models.JSONField(default=dict, help_text="Booking details, counts, etc.")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    confirmed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'channel_pending_manager_actions'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.action_type} by {self.manager.name} ({self.status})"
    
    @property
    def is_expired(self) -> bool:
        return self.status == self.Status.PENDING and timezone.now() > self.expires_at
    
    def confirm(self):
        """Confirm the pending action."""
        self.status = self.Status.CONFIRMED
        self.confirmed_at = timezone.now()
        self.save()
    
    def cancel(self):
        """Cancel the pending action."""
        self.status = self.Status.CANCELLED
        self.save()
    
    @classmethod
    def get_pending_for_manager(cls, manager):
        """Get pending action for a manager."""
        return cls.objects.filter(
            manager=manager,
            status=cls.Status.PENDING,
            expires_at__gt=timezone.now()
        ).first()