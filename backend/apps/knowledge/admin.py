"""
Admin configuration for knowledge app.
"""
from django.contrib import admin
from .models import KnowledgeBase, FAQ


@admin.register(KnowledgeBase)
class KnowledgeBaseAdmin(admin.ModelAdmin):
    list_display = ['organization', 'location', 'created_at', 'updated_at']
    list_filter = ['organization']
    search_fields = ['business_description', 'additional_info']
    raw_id_fields = ['organization', 'location']


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ['question_preview', 'knowledge_base', 'order', 'is_active']
    list_filter = ['knowledge_base__organization', 'is_active']
    search_fields = ['question', 'answer']
    raw_id_fields = ['knowledge_base']

    def question_preview(self, obj):
        return obj.question[:50] + '...' if len(obj.question) > 50 else obj.question
    question_preview.short_description = 'Question'
