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
