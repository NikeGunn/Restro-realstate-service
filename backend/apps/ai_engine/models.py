"""
AI Engine models.
"""
import uuid
from django.db import models
from apps.accounts.models import Organization


class AIPromptTemplate(models.Model):
    """
    Store prompt templates for different scenarios.
    Templates can be customized per the organization.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    # Template content (uses {variable} placeholders)
    system_prompt = models.TextField()

    # Which business types this applies to
    business_types = models.JSONField(
        default=list,
        help_text='List of business types this template applies to'
    )

    # Whether this is the default template
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_prompt_templates'
        ordering = ['name']

    def __str__(self):
        return self.name


class AILog(models.Model):
    """
    Log all AI interactions for debugging and analytics.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='ai_logs'
    )
    conversation = models.ForeignKey(
        'messaging.Conversation',
        on_delete=models.CASCADE,
        related_name='ai_logs'
    )

    # Request
    prompt = models.TextField()
    context = models.JSONField(default=dict, blank=True)

    # Response
    response = models.TextField()
    confidence_score = models.FloatField(null=True, blank=True)
    intent = models.CharField(max_length=100, blank=True)

    # Metadata
    model = models.CharField(max_length=50, default='gpt-4o-mini')
    tokens_used = models.IntegerField(default=0)
    processing_time = models.FloatField(null=True, blank=True)

    # Error tracking
    error = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ai_logs'
        ordering = ['-created_at']
        verbose_name = 'AI log'
        verbose_name_plural = 'AI logs'
        indexes = [
            models.Index(fields=['organization', '-created_at']),
            models.Index(fields=['conversation']),
        ]

    def __str__(self):
        return f"AI Log {self.id} - {self.organization.name}"


class AgentMemory(models.Model):
    """
    Durable memory for the customer-facing agent.

    One row per (organization, subject). The OWNER row holds the owner's
    standing instructions (the playbook the agent must follow); CUSTOMER rows
    hold facts the agent learned about a customer, keyed by phone (or by
    conversation id for anonymous widget visitors). Facts survive across
    conversations, so a returning customer is recognised.
    """
    class SubjectType(models.TextChoices):
        OWNER = 'owner', 'Owner playbook'
        CUSTOMER = 'customer', 'Customer'

    OWNER_KEY = 'owner'
    MAX_FACTS = 40

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='agent_memories'
    )
    subject_type = models.CharField(max_length=20, choices=SubjectType.choices)
    subject_key = models.CharField(max_length=100)
    display_name = models.CharField(max_length=255, blank=True)
    # List of {"fact": str, "at": iso8601, "source": "agent"|"owner"}
    facts = models.JSONField(default=list, blank=True)
    # Rolling narrative of every conversation with this subject, refreshed daily
    # (and early when a chat outgrows the context window). Raw messages are kept
    # forever in messaging.Message; this is the compressed, always-in-prompt view.
    summary = models.TextField(blank=True)
    summarized_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_agent_memories'
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'subject_type', 'subject_key'],
                name='uniq_agent_memory_subject',
            ),
        ]

    def __str__(self):
        return f"{self.organization} · {self.subject_type}:{self.subject_key}"


class AgentSettings(models.Model):
    """
    Owner-controlled switches for the customer-facing agent — edited in the dashboard
    (Settings → AI agent), read by the agent every turn. No code change, no deploy.
    Plan gating for a future subscription hooks in at agent/capabilities.py.
    """
    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name='agent_settings')
    bookings_enabled = models.BooleanField(default=True, help_text='Agent may book viewings')
    viewings_need_staff_approval = models.BooleanField(
        default=False, help_text='Bookings are requests until staff confirm them in Appointments')
    viewing_start_hour = models.PositiveSmallIntegerField(default=10)
    viewing_end_hour = models.PositiveSmallIntegerField(default=18, help_text='Last slot start hour')
    slot_minutes = models.PositiveSmallIntegerField(default=60)
    max_days_ahead = models.PositiveSmallIntegerField(default=60)
    daily_ai_reply_cap = models.PositiveIntegerField(
        default=0, help_text='Max AI replies per day for this org (0 = unlimited)')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_agent_settings'

    @classmethod
    def for_org(cls, organization) -> 'AgentSettings':
        obj = cls.objects.filter(organization=organization).first()
        return obj or cls(organization=organization)  # unsaved defaults until the owner edits


class AgentAction(models.Model):
    """
    Ledger for every side-effect the agent proposes (preview) and performs (receipt).

    A write happens only by executing a PREVIEWED row from an EARLIER turn, after the
    customer's own message confirmed it. The row is locked while executing, so a
    duplicate "yes" or a retried webhook returns the stored receipt instead of a second
    booking. Receipts — not model prose — are what the customer is told.
    """
    class Kind(models.TextChoices):
        BOOK_VIEWING = 'book_viewing', 'Book viewing'
        CANCEL_APPOINTMENT = 'cancel_appointment', 'Cancel appointment'
        RESCHEDULE_APPOINTMENT = 'reschedule_appointment', 'Reschedule appointment'

    class Status(models.TextChoices):
        PREVIEWED = 'previewed', 'Awaiting customer confirmation'
        EXECUTED = 'executed', 'Done'
        FAILED = 'failed', 'Failed'
        SUPERSEDED = 'superseded', 'Replaced by a newer preview'
        DECLINED = 'declined', 'Customer declined'
        EXPIRED = 'expired', 'Expired'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='agent_actions')
    conversation = models.ForeignKey('messaging.Conversation', on_delete=models.CASCADE, related_name='agent_actions')
    kind = models.CharField(max_length=40, choices=Kind.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PREVIEWED)
    payload = models.JSONField(default=dict)
    payload_hash = models.CharField(max_length=64)
    receipt = models.JSONField(default=dict, blank=True)
    error = models.CharField(max_length=300, blank=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    executed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'ai_agent_actions'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['conversation', 'status', '-created_at'])]

    def __str__(self):
        return f"{self.kind} {self.status} {self.payload_hash[:8]}"
