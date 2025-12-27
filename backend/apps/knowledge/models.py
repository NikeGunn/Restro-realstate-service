"""
Knowledge Base models - Business profile, FAQs, location overrides.
"""
import uuid
from django.db import models
from apps.accounts.models import Organization, Location


class KnowledgeBase(models.Model):
    """
    Main knowledge base for an organization/location.
    Location-specific knowledge overrides organization-level.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='knowledge_bases'
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='knowledge_bases',
        help_text='If set, this knowledge overrides org-level for this location'
    )

    # Business Profile
    business_description = models.TextField(
        blank=True,
        help_text='Description of the business for AI context'
    )

    # Opening Hours (JSON: {"monday": {"open": "09:00", "close": "17:00"}, ...})
    opening_hours = models.JSONField(
        default=dict,
        blank=True,
        help_text='Opening hours for each day of the week'
    )

    # Contact Information
    contact_info = models.JSONField(
        default=dict,
        blank=True,
        help_text='Contact details (phone, email, address, etc.)'
    )

    # Services/Offerings
    services = models.JSONField(
        default=list,
        blank=True,
        help_text='List of services offered'
    )

    # Additional free-text info
    additional_info = models.TextField(
        blank=True,
        help_text='Any additional information for AI context'
    )

    # Policies
    policies = models.JSONField(
        default=dict,
        blank=True,
        help_text='Business policies (cancellation, refund, etc.)'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'knowledge_bases'
        unique_together = ['organization', 'location']
        ordering = ['organization', 'location']

    def __str__(self):
        if self.location:
            return f"Knowledge: {self.organization.name} - {self.location.name}"
        return f"Knowledge: {self.organization.name} (Organization Level)"


class FAQ(models.Model):
    """
    Frequently Asked Questions.
    Linked to a KnowledgeBase for organization.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    knowledge_base = models.ForeignKey(
        KnowledgeBase,
        on_delete=models.CASCADE,
        related_name='faqs'
    )

    question = models.TextField()
    answer = models.TextField()

    # Ordering and status
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'faqs'
        ordering = ['order', '-created_at']
        verbose_name = 'FAQ'
        verbose_name_plural = 'FAQs'

    def __str__(self):
        return f"FAQ: {self.question[:50]}..."
    
    @property
    def organization(self):
        """Get organization from knowledge base."""
        return self.knowledge_base.organization
    
    @property
    def location(self):
        """Get location from knowledge base."""
        return self.knowledge_base.location
