"""
Handoff serializers.
"""
from rest_framework import serializers
from .models import HandoffAlert, EscalationRule
from apps.messaging.serializers import ConversationSerializer


class HandoffAlertSerializer(serializers.ModelSerializer):
    """Serializer for HandoffAlert."""
    conversation = ConversationSerializer(read_only=True)
    acknowledged_by_name = serializers.SerializerMethodField()
    resolved_by_name = serializers.SerializerMethodField()

    class Meta:
        model = HandoffAlert
        fields = [
            'id', 'conversation', 'alert_type', 'priority', 'reason',
            'is_acknowledged', 'acknowledged_by', 'acknowledged_by_name', 'acknowledged_at',
            'is_resolved', 'resolved_by', 'resolved_by_name', 'resolved_at', 'resolution_notes',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']

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
