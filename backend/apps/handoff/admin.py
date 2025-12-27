"""
Admin configuration for handoff app.
"""
from django.contrib import admin
from .models import HandoffAlert, EscalationRule


@admin.register(HandoffAlert)
class HandoffAlertAdmin(admin.ModelAdmin):
    list_display = ['id', 'conversation', 'alert_type', 'priority', 'is_acknowledged', 'is_resolved', 'created_at']
    list_filter = ['alert_type', 'priority', 'is_acknowledged', 'is_resolved']
    search_fields = ['reason']
    readonly_fields = ['created_at']
    raw_id_fields = ['conversation', 'acknowledged_by', 'resolved_by']


@admin.register(EscalationRule)
class EscalationRuleAdmin(admin.ModelAdmin):
    list_display = ['name', 'organization', 'trigger_type', 'priority', 'is_active']
    list_filter = ['is_active', 'priority', 'organization']
    search_fields = ['name', 'description']
