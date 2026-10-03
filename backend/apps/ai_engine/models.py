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
