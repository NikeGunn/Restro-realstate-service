"""Content Studio admin."""
import json

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    ContentUseCase, BrandKit, ContentPromptTemplate,
    ContentGenerationJob, ContentGenerationOutput,
)


def _pretty_json(value):
    if not value:
        return '—'
    return format_html('<pre style="white-space:pre-wrap">{}</pre>',
                       json.dumps(value, indent=2, ensure_ascii=False))


class ContentPromptTemplateInline(admin.StackedInline):
    model = ContentPromptTemplate
    extra = 0


@admin.register(ContentUseCase)
class ContentUseCaseAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'use_case_key', 'credit_cost', 'active', 'sort_order')
    list_filter = ('active',)
    search_fields = ('use_case_key', 'display_name')
    ordering = ('sort_order', 'display_name')
    inlines = [ContentPromptTemplateInline]


@admin.register(ContentPromptTemplate)
class ContentPromptTemplateAdmin(admin.ModelAdmin):
    list_display = ('use_case', 'provider', 'model', 'version', 'updated_at')
    search_fields = ('use_case__use_case_key',)


@admin.register(BrandKit)
class BrandKitAdmin(admin.ModelAdmin):
    list_display = ('restaurant_name', 'organization', 'preferred_language',
                    'watermark_preference', 'updated_at')
    search_fields = ('restaurant_name', 'organization__name')


@admin.register(ContentGenerationJob)
class ContentGenerationJobAdmin(admin.ModelAdmin):
    list_display = ('id', 'organization', 'use_case', 'status', 'output_count',
                    'credits_used', 'created_at')
    list_filter = ('status', 'organization')
    search_fields = ('id', 'organization__name')
    readonly_fields = (
        'organization', 'created_by', 'use_case', 'brand_kit_snapshot_pretty',
        'input_payload_pretty', 'generated_prompt', 'negative_prompt',
        'provider', 'model', 'output_resolution', 'aspect', 'status',
        'credits_estimated', 'credits_used', 'cost_estimated_usd',
        'cost_actual_usd', 'output_count', 'idempotency_key', 'usage_event_id',
        'error_message', 'created_at', 'completed_at', 'updated_at',
    )
    exclude = ('brand_kit_snapshot', 'input_payload')

    @admin.display(description='Brand kit snapshot')
    def brand_kit_snapshot_pretty(self, obj):
        return _pretty_json(obj.brand_kit_snapshot)

    @admin.display(description='Input payload')
    def input_payload_pretty(self, obj):
        return _pretty_json(obj.input_payload)

    def has_add_permission(self, request):
        return False


@admin.register(ContentGenerationOutput)
class ContentGenerationOutputAdmin(admin.ModelAdmin):
    list_display = ('id', 'job', 'width', 'height', 'format', 'download_count', 'is_favorite')
    list_filter = ('is_favorite', 'format')
    readonly_fields = (
        'job', 'asset', 'thumbnail', 'file_type', 'width', 'height',
        'format', 'provider_asset_id', 'download_count', 'created_at', 'updated_at',
    )

    def has_add_permission(self, request):
        return False
