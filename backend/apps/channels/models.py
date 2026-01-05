"""
Channel configuration models.
Stores API credentials and settings for WhatsApp and Instagram.
"""
import uuid
from django.db import models
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
