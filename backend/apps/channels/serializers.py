"""
Channel serializers.
"""
from rest_framework import serializers
from .models import WhatsAppConfig, InstagramConfig, WebhookLog, ManagerNumber, TemporaryOverride, ManagerQuery


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


class ManagerNumberSerializer(serializers.ModelSerializer):
    """Serializer for Manager WhatsApp Numbers."""
    user_email = serializers.EmailField(source='user.email', read_only=True)
    
    class Meta:
        model = ManagerNumber
        fields = [
            'id', 'organization', 'phone_number', 'name', 'role',
            'user', 'user_email',
            'can_update_hours', 'can_respond_queries', 'can_view_bookings',
            'is_active', 'created_at', 'updated_at', 'last_message_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'last_message_at', 'user_email']
    
    def validate_phone_number(self, value):
        """Normalize and validate phone number."""
        # Remove any non-digit characters except +
        normalized = ''.join(c for c in value if c.isdigit() or c == '+')
        if not normalized:
            raise serializers.ValidationError("Phone number must contain digits.")
        # Remove leading + if present and ensure it's just digits
        if normalized.startswith('+'):
            normalized = normalized[1:]
        if len(normalized) < 10:
            raise serializers.ValidationError("Phone number must be at least 10 digits.")
        return normalized


class ManagerNumberCreateSerializer(serializers.ModelSerializer):
    """Simplified serializer for creating manager numbers."""
    
    class Meta:
        model = ManagerNumber
        fields = [
            'organization', 'phone_number', 'name', 'role',
            'can_update_hours', 'can_respond_queries', 'can_view_bookings'
        ]
    
    def validate_phone_number(self, value):
        """Normalize and validate phone number."""
        normalized = ''.join(c for c in value if c.isdigit() or c == '+')
        if normalized.startswith('+'):
            normalized = normalized[1:]
        if len(normalized) < 10:
            raise serializers.ValidationError("Phone number must be at least 10 digits with country code.")
        return normalized
    
    def validate(self, attrs):
        """Check that WhatsApp is configured for this organization."""
        organization = attrs.get('organization')
        
        # Check if WhatsApp config exists and is active
        if not hasattr(organization, 'whatsapp_config'):
            raise serializers.ValidationError({
                'organization': 'WhatsApp must be configured before adding manager numbers.'
            })
        
        whatsapp_config = organization.whatsapp_config
        if not whatsapp_config.is_active:
            raise serializers.ValidationError({
                'organization': 'WhatsApp configuration must be active before adding manager numbers.'
            })
        
        return attrs


class TemporaryOverrideSerializer(serializers.ModelSerializer):
    """Serializer for Temporary Overrides."""
    created_by_manager_name = serializers.CharField(source='created_by_manager.name', read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = TemporaryOverride
        fields = [
            'id', 'organization', 'override_type', 'priority',
            'original_message', 'processed_content', 'trigger_keywords',
            'created_by_manager', 'created_by_manager_name',
            'starts_at', 'expires_at', 'auto_expire_on_next_open',
            'is_active', 'is_expired', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_expired', 'created_by_manager_name']


class ManagerQuerySerializer(serializers.ModelSerializer):
    """Serializer for Manager Queries."""
    manager_name = serializers.CharField(source='manager.name', read_only=True)
    customer_name = serializers.CharField(source='conversation.customer_name', read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = ManagerQuery
        fields = [
            'id', 'organization', 'conversation', 'manager', 'manager_name',
            'customer_query', 'query_summary', 'customer_name',
            'manager_response', 'response_received_at',
            'status', 'expires_at', 'is_expired',
            'customer_response', 'customer_response_sent',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'is_expired',
            'manager_name', 'customer_name', 'response_received_at'
        ]
