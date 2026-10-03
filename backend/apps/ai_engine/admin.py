"""
Admin configuration for AI engine app.
"""
from django.contrib import admin
from .models import AIPromptTemplate, AILog


@admin.register(AIPromptTemplate)
class AIPromptTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_default', 'is_active', 'created_at']
    list_filter = ['is_default', 'is_active']
    search_fields = ['name', 'description']


@admin.register(AILog)
class AILogAdmin(admin.ModelAdmin):
    list_display = ['id', 'organization', 'intent', 'confidence_score', 'tokens_used', 'created_at']
    list_filter = ['organization', 'intent', 'model']
    search_fields = ['prompt', 'response']
    readonly_fields = ['created_at']
    raw_id_fields = ['organization', 'conversation']


from .models import AgentMemory  # noqa: E402


@admin.register(AgentMemory)
class AgentMemoryAdmin(admin.ModelAdmin):
    list_display = ['organization', 'subject_type', 'subject_key', 'display_name', 'updated_at']
    list_filter = ['subject_type']
    search_fields = ['subject_key', 'display_name', 'organization__name']


from .models import AgentAction, AgentSettings  # noqa: E402


@admin.register(AgentSettings)
class AgentSettingsAdmin(admin.ModelAdmin):
    list_display = ('organization', 'bookings_enabled', 'viewings_need_staff_approval', 'viewing_start_hour',
                    'viewing_end_hour', 'daily_ai_reply_cap', 'updated_at')
    search_fields = ('organization__name',)


@admin.register(AgentAction)
class AgentActionAdmin(admin.ModelAdmin):
    """The agent's action ledger is evidence — read-only."""
    list_display = ('created_at', 'organization', 'kind', 'status', 'executed_at')
    list_filter = ('kind', 'status')
    search_fields = ('organization__name', 'receipt')
    readonly_fields = [f.name for f in AgentAction._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
