"""
Messaging serializers for API.
"""
from rest_framework import serializers
from .models import Conversation, Message, WidgetSession, ConversationState, MessageSender


class MessageSerializer(serializers.ModelSerializer):
    """Serializer for Message model."""
    sent_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Message
        fields = [
            'id', 'content', 'sender', 'sent_by', 'sent_by_name',
            'confidence_score', 'intent', 'ai_metadata',
            'is_read', 'read_at', 'created_at'
        ]
        read_only_fields = ['id', 'sent_by', 'sent_by_name', 'confidence_score', 'intent', 'ai_metadata', 'created_at']
    
    def get_sent_by_name(self, obj):
        if obj.sent_by:
            return f"{obj.sent_by.first_name} {obj.sent_by.last_name}".strip() or obj.sent_by.email
        return None


class MessageCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating messages."""
    
    class Meta:
        model = Message
        fields = ['content']


class ConversationSerializer(serializers.ModelSerializer):
    """Serializer for Conversation model."""
    messages_count = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    assigned_to_name = serializers.SerializerMethodField()
    location_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Conversation
        fields = [
            'id', 'organization', 'location', 'location_name', 'channel',
            'customer_name', 'customer_email', 'customer_phone', 'customer_metadata',
            'state', 'assigned_to', 'assigned_to_name',
            'intent', 'sentiment', 'tags',
            'is_locked', 'locked_by', 'locked_at',
            'created_at', 'updated_at', 'last_message_at', 'resolved_at',
            'messages_count', 'unread_count', 'last_message'
        ]
        read_only_fields = [
            'id', 'organization', 'channel', 'created_at', 'updated_at',
            'is_locked', 'locked_by', 'locked_at'
        ]
    
    def get_messages_count(self, obj):
        return obj.messages.count()
    
    def get_unread_count(self, obj):
        return obj.messages.filter(is_read=False, sender=MessageSender.CUSTOMER).count()
    
    def get_last_message(self, obj):
        last_msg = obj.messages.order_by('-created_at').first()
        if last_msg:
            return {
                'content': last_msg.content[:100],
                'sender': last_msg.sender,
                'created_at': last_msg.created_at
            }
        return None
    
    def get_assigned_to_name(self, obj):
        if obj.assigned_to:
            return f"{obj.assigned_to.first_name} {obj.assigned_to.last_name}".strip() or obj.assigned_to.email
        return None
    
    def get_location_name(self, obj):
        if obj.location:
            return obj.location.name
        return None


class ConversationDetailSerializer(ConversationSerializer):
    """Detailed serializer with messages."""
    messages = MessageSerializer(many=True, read_only=True)
    
    class Meta(ConversationSerializer.Meta):
        fields = ConversationSerializer.Meta.fields + ['messages']


class ConversationUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating conversation."""
    
    class Meta:
        model = Conversation
        fields = [
            'customer_name', 'customer_email', 'customer_phone',
            'location', 'tags', 'intent', 'sentiment'
        ]


class WidgetSessionSerializer(serializers.ModelSerializer):
    """Serializer for WidgetSession model."""
    
    class Meta:
        model = WidgetSession
        fields = [
            'id', 'session_token', 'conversation', 'location',
            'visitor_id', 'page_url', 'created_at', 'last_activity_at'
        ]
        read_only_fields = ['id', 'session_token', 'created_at', 'last_activity_at']


class WidgetInitSerializer(serializers.Serializer):
    """Serializer for widget initialization."""
    widget_key = serializers.UUIDField()
    visitor_id = serializers.CharField(max_length=255, required=False, allow_blank=True)
    page_url = serializers.URLField(required=False, allow_blank=True)
    location_id = serializers.UUIDField(required=False, allow_null=True)


class WidgetMessageSerializer(serializers.Serializer):
    """Serializer for widget messages."""
    session_token = serializers.UUIDField()
    content = serializers.CharField(max_length=4000)
    customer_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    customer_email = serializers.EmailField(required=False, allow_blank=True)
    customer_phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
