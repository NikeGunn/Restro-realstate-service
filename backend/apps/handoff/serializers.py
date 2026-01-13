"""
Handoff serializers.
"""
from rest_framework import serializers
from .models import HandoffAlert, EscalationRule
from apps.messaging.serializers import ConversationSerializer


class HandoffAlertSerializer(serializers.ModelSerializer):
    """Serializer for HandoffAlert."""
    conversation = serializers.UUIDField(source='conversation.id', read_only=True)
    conversation_customer_name = serializers.CharField(source='conversation.customer_name', read_only=True)
    conversation_channel = serializers.CharField(source='conversation.channel', read_only=True)
    type = serializers.CharField(source='alert_type', read_only=True)
    status = serializers.SerializerMethodField()
    acknowledged_by_name = serializers.SerializerMethodField()
    resolved_by_name = serializers.SerializerMethodField()
    trigger_message = serializers.SerializerMethodField()

    class Meta:
        model = HandoffAlert
        fields = [
            'id', 'conversation', 'conversation_customer_name', 'conversation_channel',
            'alert_type', 'type', 'priority', 'reason',
            'status', 'trigger_message',
            'is_acknowledged', 'acknowledged_by', 'acknowledged_by_name', 'acknowledged_at',
            'is_resolved', 'resolved_by', 'resolved_by_name', 'resolved_at', 'resolution_notes',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def get_status(self, obj):
        """Derive status from is_acknowledged and is_resolved."""
        if obj.is_resolved:
            return 'resolved'
        elif obj.is_acknowledged:
            return 'acknowledged'
        else:
            return 'pending'
    
    def get_trigger_message(self, obj):
        """Extract trigger message from reason if embedded there."""
        reason = obj.reason or ''
        if 'Triggering message: "' in reason:
            start = reason.find('Triggering message: "') + len('Triggering message: "')
            end = reason.rfind('"...')
            if end > start:
                return reason[start:end]
        # Try to get last customer message from conversation
        from apps.messaging.models import MessageSender
        last_customer_msg = obj.conversation.messages.filter(
            sender=MessageSender.CUSTOMER
        ).order_by('-created_at').first()
        return last_customer_msg.content[:200] if last_customer_msg else None

    def get_acknowledged_by_name(self, obj):
        if obj.acknowledged_by:
            return f"{obj.acknowledged_by.first_name} {obj.acknowledged_by.last_name}".strip()
        return None

    def get_resolved_by_name(self, obj):
        if obj.resolved_by:
            return f"{obj.resolved_by.first_name} {obj.resolved_by.last_name}".strip()
        return None


class EscalationRuleSerializer(serializers.ModelSerializer):
    """Serializer for EscalationRule."""

    class Meta:
        model = EscalationRule
        fields = [
            'id', 'name', 'description', 'trigger_type', 'trigger_value',
            'priority', 'auto_assign_to', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
