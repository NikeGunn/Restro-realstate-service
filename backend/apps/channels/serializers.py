"""
Channel serializers.
"""
from rest_framework import serializers
from .models import WhatsAppConfig, InstagramConfig, WebhookLog


class WhatsAppConfigSerializer(serializers.ModelSerializer):
    """Serializer for WhatsApp configuration."""
    webhook_url = serializers.SerializerMethodField()
    
    class Meta:
        model = WhatsAppConfig
        fields = [
            'id', 'organization', 'phone_number_id', 'business_account_id',
            'access_token', 'verify_token', 'webhook_url',
            'is_verified', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'verify_token', 'webhook_url', 'is_verified', 'created_at', 'updated_at']
        extra_kwargs = {
            'access_token': {'write_only': True}  # Don't expose token in responses
        }
    
    def get_webhook_url(self, obj):
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri('/api/webhooks/whatsapp/')
        return '/api/webhooks/whatsapp/'


class InstagramConfigSerializer(serializers.ModelSerializer):
    """Serializer for Instagram configuration."""
    webhook_url = serializers.SerializerMethodField()
    
    class Meta:
        model = InstagramConfig
        fields = [
            'id', 'organization', 'instagram_business_id', 'page_id',
            'access_token', 'verify_token', 'webhook_url',
            'is_verified', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'verify_token', 'webhook_url', 'is_verified', 'created_at', 'updated_at']
        extra_kwargs = {
            'access_token': {'write_only': True}
        }
    
    def get_webhook_url(self, obj):
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri('/api/webhooks/instagram/')
        return '/api/webhooks/instagram/'


class WebhookLogSerializer(serializers.ModelSerializer):
    """Serializer for webhook logs."""
    
    class Meta:
        model = WebhookLog
        fields = [
            'id', 'source', 'organization', 'headers', 'body',
            'is_processed', 'error_message', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
