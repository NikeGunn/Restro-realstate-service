"""
Handoff models - Alerts and escalations.
"""
import uuid
from django.db import models
from django.conf import settings
from apps.messaging.models import Conversation


class HandoffAlert(models.Model):
    """
    Alert for conversations requiring human attention.
    """
    class Priority(models.TextChoices):
        LOW = 'low', 'Low'
        MEDIUM = 'medium', 'Medium'
        HIGH = 'high', 'High'
        URGENT = 'urgent', 'Urgent'

    class AlertType(models.TextChoices):
        LOW_CONFIDENCE = 'low_confidence', 'Low Confidence'
        ESCALATION_REQUEST = 'escalation_request', 'Escalation Request'
        HIGH_INTENT = 'high_intent', 'High Intent Lead'
        BOOKING_FAILURE = 'booking_failure', 'Booking Failure'
        CONFUSED_USER = 'confused_user', 'Confused User'
        COMPLAINT = 'complaint', 'Complaint'
        OTHER = 'other', 'Other'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='alerts'
    )

    alert_type = models.CharField(
        max_length=30,
        choices=AlertType.choices,
        default=AlertType.OTHER
    )
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.MEDIUM
    )
    reason = models.TextField()

    # Status
    is_acknowledged = models.BooleanField(default=False)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='acknowledged_alerts'
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    is_resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_alerts'
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'handoff_alerts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['conversation', '-created_at']),
            models.Index(fields=['priority', 'is_acknowledged']),
        ]

    def __str__(self):
        return f"{self.alert_type} - {self.conversation}"

    def acknowledge(self, user):
        """Mark alert as acknowledged."""
        from django.utils import timezone
        self.is_acknowledged = True
        self.acknowledged_by = user
        self.acknowledged_at = timezone.now()
        self.save()

    def resolve(self, user, notes: str = ""):
        """Mark alert as resolved."""
        from django.utils import timezone
        self.is_resolved = True
        self.resolved_by = user
        self.resolved_at = timezone.now()
        self.resolution_notes = notes
        if not self.is_acknowledged:
            self.acknowledge(user)
        self.save()


class EscalationRule(models.Model):
    """
    Rules for automatic escalation (Power plan feature).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization',
        on_delete=models.CASCADE,
        related_name='escalation_rules'
    )

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    # Trigger conditions
    trigger_type = models.CharField(max_length=50)  # e.g., 'keyword', 'intent', 'sentiment'
    trigger_value = models.JSONField()  # e.g., {"keywords": ["urgent", "manager"]}

    # Actions
    priority = models.CharField(
        max_length=20,
        choices=HandoffAlert.Priority.choices,
        default=HandoffAlert.Priority.HIGH
    )
    auto_assign_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'escalation_rules'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} - {self.organization.name}"
