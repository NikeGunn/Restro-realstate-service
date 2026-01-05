from django.contrib import admin
from .models import WhatsAppConfig, InstagramConfig, WebhookLog


@admin.register(WhatsAppConfig)
class WhatsAppConfigAdmin(admin.ModelAdmin):
    list_display = ['organization', 'phone_number_id', 'is_verified', 'is_active', 'created_at']
    list_filter = ['is_verified', 'is_active']
    search_fields = ['organization__name', 'phone_number_id']


@admin.register(InstagramConfig)
class InstagramConfigAdmin(admin.ModelAdmin):
    list_display = ['organization', 'instagram_business_id', 'is_verified', 'is_active', 'created_at']
    list_filter = ['is_verified', 'is_active']
    search_fields = ['organization__name', 'instagram_business_id']


@admin.register(WebhookLog)
class WebhookLogAdmin(admin.ModelAdmin):
    list_display = ['source', 'organization', 'is_processed', 'created_at']
    list_filter = ['source', 'is_processed']
    readonly_fields = ['id', 'source', 'organization', 'headers', 'body', 'is_processed', 'error_message', 'created_at']
