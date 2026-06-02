"""Content Studio serializers."""
from rest_framework import serializers

from .models import (
    ContentUseCase, BrandKit, ContentGenerationJob, ContentGenerationOutput,
)


class ContentUseCaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentUseCase
        fields = [
            'id', 'use_case_key', 'display_name', 'description', 'icon',
            'required_fields', 'optional_fields', 'supported_formats',
            'credit_cost', 'active', 'sort_order',
        ]
        read_only_fields = fields


class BrandKitSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = BrandKit
        fields = [
            'id', 'organization', 'restaurant_name', 'logo', 'logo_url',
            'brand_colors', 'preferred_language', 'default_cta',
            'phone', 'whatsapp', 'address', 'website_url', 'social_handles',
            'watermark_preference', 'style_preferences',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'logo', 'logo_url', 'created_at', 'updated_at']

    def get_logo_url(self, obj):
        if not obj.logo:
            return None
        request = self.context.get('request')
        url = obj.logo.url
        return request.build_absolute_uri(url) if request else url

    def validate_brand_colors(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('brand_colors must be a list of hex strings.')
        if len(value) > 5:
            raise serializers.ValidationError('At most 5 brand colors.')
        for c in value:
            if not isinstance(c, str) or not c.startswith('#'):
                raise serializers.ValidationError(f'Invalid hex color: {c!r}')
        return value


class ContentGenerationOutputSerializer(serializers.ModelSerializer):
    asset_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = ContentGenerationOutput
        fields = [
            'id', 'job', 'asset_url', 'thumbnail_url', 'file_type',
            'width', 'height', 'format', 'download_count', 'is_favorite',
            'created_at',
        ]
        read_only_fields = fields

    def _abs(self, field):
        if not field:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(field.url) if request else field.url

    def get_asset_url(self, obj):
        return self._abs(obj.asset)

    def get_thumbnail_url(self, obj):
        return self._abs(obj.thumbnail or obj.asset)


class ContentGenerationJobSerializer(serializers.ModelSerializer):
    use_case_key = serializers.CharField(source='use_case.use_case_key', read_only=True)
    use_case_name = serializers.CharField(source='use_case.display_name', read_only=True)
    outputs = ContentGenerationOutputSerializer(many=True, read_only=True)

    class Meta:
        model = ContentGenerationJob
        fields = [
            'id', 'organization', 'created_by', 'use_case', 'use_case_key',
            'use_case_name', 'input_payload', 'aspect', 'output_resolution',
            'generated_prompt', 'provider', 'model', 'status',
            'credits_estimated', 'credits_used', 'cost_estimated_usd',
            'cost_actual_usd', 'output_count', 'error_message',
            'outputs', 'created_at', 'completed_at',
        ]
        read_only_fields = [
            'id', 'created_by', 'use_case_key', 'use_case_name',
            'generated_prompt', 'provider', 'model', 'status',
            'credits_estimated', 'credits_used', 'cost_estimated_usd',
            'cost_actual_usd', 'output_count', 'error_message',
            'outputs', 'created_at', 'completed_at',
        ]


class ContentGenerationJobCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentGenerationJob
        fields = [
            'id', 'organization', 'use_case', 'input_payload',
            'aspect', 'output_resolution',
        ]
        read_only_fields = ['id']
