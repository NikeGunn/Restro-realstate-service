"""
Messaging models - Conversations, Messages, Channels
Implements unified inbox and conversation state machine.
"""
import uuid
from django.db import models
from django.conf import settings
from apps.accounts.models import Organization, Location


class Channel(models.TextChoices):
    """Supported messaging channels."""
    WEBSITE = 'website', 'Website Widget'
    WHATSAPP = 'whatsapp', 'WhatsApp'
    INSTAGRAM = 'instagram', 'Instagram'


class ConversationState(models.TextChoices):
    """
    Conversation state machine (FSM).
    
    States:
    - NEW: Fresh conversation, no messages yet
    - AI_HANDLING: AI is actively responding
    - AWAITING_USER: Waiting for user response
    - HUMAN_HANDOFF: Transferred to human agent
    - RESOLVED: Conversation completed
    - ARCHIVED: Old/inactive conversation
    """
    NEW = 'new', 'New'
    AI_HANDLING = 'ai_handling', 'AI Handling'
    AWAITING_USER = 'awaiting_user', 'Awaiting User'
    HUMAN_HANDOFF = 'human_handoff', 'Human Handoff'
    RESOLVED = 'resolved', 'Resolved'
    ARCHIVED = 'archived', 'Archived'


class Conversation(models.Model):
    """
    Unified conversation model across all channels.
    Channel-agnostic design for omnichannel support.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='conversations'
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='conversations'
    )
    
    # Channel information
    channel = models.CharField(
        max_length=20,
        choices=Channel.choices,
        default=Channel.WEBSITE
    )
    channel_conversation_id = models.CharField(
        max_length=255,
        blank=True,
        help_text='External conversation ID from the channel (e.g., WhatsApp thread ID)'
    )
    
    # Customer information
    customer_name = models.CharField(max_length=255, blank=True)
    customer_email = models.EmailField(blank=True)
    customer_phone = models.CharField(max_length=20, blank=True)
    customer_metadata = models.JSONField(default=dict, blank=True)
    
    # State machine
    state = models.CharField(
        max_length=20,
        choices=ConversationState.choices,
        default=ConversationState.NEW
    )
    
    # Assignment (for human handoff)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_conversations'
    )
    
    # AI context
    intent = models.CharField(max_length=100, blank=True)
    sentiment = models.CharField(max_length=50, blank=True)
    tags = models.JSONField(default=list, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_message_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    # Locking (for human handoff)
    is_locked = models.BooleanField(default=False)
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='locked_conversations'
    )
    locked_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'conversations'
        ordering = ['-last_message_at', '-created_at']
        indexes = [
            models.Index(fields=['organization', 'state']),
            models.Index(fields=['channel', 'channel_conversation_id']),
            models.Index(fields=['-last_message_at']),
        ]
    
    def __str__(self):
        return f"{self.channel} - {self.customer_name or 'Anonymous'} ({self.state})"
    
    def transition_state(self, new_state: ConversationState):
        """
        Transition conversation to a new state.
        Implements basic FSM validation.
        """
        valid_transitions = {
            ConversationState.NEW: [ConversationState.AI_HANDLING, ConversationState.HUMAN_HANDOFF],
            ConversationState.AI_HANDLING: [ConversationState.AWAITING_USER, ConversationState.HUMAN_HANDOFF, ConversationState.RESOLVED],
            ConversationState.AWAITING_USER: [ConversationState.AI_HANDLING, ConversationState.HUMAN_HANDOFF, ConversationState.ARCHIVED],
            ConversationState.HUMAN_HANDOFF: [ConversationState.AI_HANDLING, ConversationState.RESOLVED],
            ConversationState.RESOLVED: [ConversationState.ARCHIVED, ConversationState.AI_HANDLING],
            ConversationState.ARCHIVED: [ConversationState.AI_HANDLING],
        }
        
        if new_state in valid_transitions.get(self.state, []):
            self.state = new_state
            if new_state == ConversationState.RESOLVED:
                from django.utils import timezone
                self.resolved_at = timezone.now()
            self.save(update_fields=['state', 'resolved_at', 'updated_at'])
            return True
        return False
    
    def lock(self, user):
        """Lock conversation for human handling."""
        from django.utils import timezone
        self.is_locked = True
        self.locked_by = user
        self.locked_at = timezone.now()
        self.assigned_to = user
        self.transition_state(ConversationState.HUMAN_HANDOFF)
        self.save()
    
    def unlock(self):
        """Unlock conversation, return to AI handling."""
        self.is_locked = False
        self.locked_by = None
        self.locked_at = None
        self.save(update_fields=['is_locked', 'locked_by', 'locked_at', 'updated_at'])


class MessageSender(models.TextChoices):
    """Who sent the message."""
    CUSTOMER = 'customer', 'Customer'
    AI = 'ai', 'AI Assistant'
    HUMAN = 'human', 'Human Agent'
    SYSTEM = 'system', 'System'


class Message(models.Model):
    """
    Individual message within a conversation.
    Supports deduplication via message_id.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    
    # Message content
    content = models.TextField()
    sender = models.CharField(
        max_length=20,
        choices=MessageSender.choices,
        default=MessageSender.CUSTOMER
    )
    
    # For human messages, track who sent it
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_messages'
    )
    
    # Channel-specific message ID (for deduplication)
    channel_message_id = models.CharField(
        max_length=255,
        blank=True,
        help_text='External message ID from the channel'
    )
    
    # AI metadata
    confidence_score = models.FloatField(null=True, blank=True)
    intent = models.CharField(max_length=100, blank=True)
    ai_metadata = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Read status
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'messages'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['conversation', 'created_at']),
            models.Index(fields=['channel_message_id']),
        ]
    
    def __str__(self):
        return f"{self.sender}: {self.content[:50]}..."
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update conversation's last_message_at
        from django.utils import timezone
        self.conversation.last_message_at = timezone.now()
        self.conversation.save(update_fields=['last_message_at', 'updated_at'])


class WidgetSession(models.Model):
    """
    Track website widget sessions.
    Links anonymous visitors to conversations.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='widget_sessions'
    )
    conversation = models.OneToOneField(
        Conversation,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='widget_session'
    )
    
    # Session token for the widget
    session_token = models.UUIDField(default=uuid.uuid4, unique=True)
    
    # Visitor info
    visitor_id = models.CharField(max_length=255, blank=True)
    user_agent = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    referrer = models.URLField(blank=True)
    page_url = models.URLField(blank=True)
    
    # Location detection/selection
    location = models.ForeignKey(
        Location,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'widget_sessions'
        ordering = ['-last_activity_at']
    
    def __str__(self):
        return f"Session {self.session_token} - {self.organization.name}"
