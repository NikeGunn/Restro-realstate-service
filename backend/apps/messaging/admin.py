"""
Admin configuration for messaging app.
"""
from django.contrib import admin
from .models import Conversation, Message, WidgetSession


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['id', 'organization', 'channel', 'customer_name', 'state', 'created_at']
    list_filter = ['channel', 'state', 'organization', 'is_locked']
    search_fields = ['customer_name', 'customer_email', 'customer_phone']
    readonly_fields = ['created_at', 'updated_at', 'last_message_at']
    raw_id_fields = ['organization', 'location', 'assigned_to', 'locked_by']


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'conversation', 'sender', 'content_preview', 'created_at']
    list_filter = ['sender', 'is_read']
    search_fields = ['content']
    readonly_fields = ['created_at']
    raw_id_fields = ['conversation', 'sent_by']

    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Content'


@admin.register(WidgetSession)
class WidgetSessionAdmin(admin.ModelAdmin):
    list_display = ['session_token', 'organization', 'visitor_id', 'created_at']
    list_filter = ['organization']
    search_fields = ['visitor_id', 'ip_address']
    readonly_fields = ['session_token', 'created_at', 'last_activity_at']
    raw_id_fields = ['organization', 'conversation', 'location']
