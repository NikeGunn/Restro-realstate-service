"""CRM serializers (Phase 1)."""
from rest_framework import serializers

from .models import (
    CRMCustomer, CRMTag, CRMInteraction, CRMConsent, CRMSegment,
)
from .services import segment_service


class CRMTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = CRMTag
        fields = ['id', 'organization', 'name', 'color', 'is_system', 'created_at']
        read_only_fields = ['is_system', 'created_at']

    def validate(self, attrs):
        # Block renaming a system tag.
        if self.instance and self.instance.is_system:
            new_name = attrs.get('name', self.instance.name)
            if new_name != self.instance.name:
                raise serializers.ValidationError("System tags cannot be renamed.")
        return attrs


class _TagBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = CRMTag
        fields = ['id', 'name', 'color', 'is_system']


class CRMCustomerSerializer(serializers.ModelSerializer):
    tags = serializers.SerializerMethodField()

    class Meta:
        model = CRMCustomer
        fields = [
            'id', 'organization', 'name', 'phone', 'phone_raw', 'email',
            'whatsapp_number', 'birthday', 'birthday_month', 'gender',
            'preferred_language', 'source', 'notes', 'last_visit_date',
            'last_interaction_at', 'visit_count', 'marketing_consent_status',
            'is_active', 'tags', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'phone_raw', 'birthday_month', 'last_interaction_at', 'visit_count',
            'marketing_consent_status', 'created_at', 'updated_at',
        ]

    def get_tags(self, obj):
        tags = [ct.tag for ct in obj.customer_tags.all()]
        return _TagBriefSerializer(tags, many=True).data


class CRMInteractionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CRMInteraction
        fields = [
            'id', 'organization', 'customer', 'interaction_type', 'source_channel',
            'summary', 'related_entity_type', 'related_entity_id',
            'created_at', 'created_by',
        ]
        read_only_fields = fields  # interactions are created via the service, read-only here


class CRMConsentSerializer(serializers.ModelSerializer):
    class Meta:
        model = CRMConsent
        fields = [
            'id', 'organization', 'customer', 'consent_given', 'consent_source',
            'consent_text_snapshot', 'consent_text_version',
            'marketing_channels_allowed', 'opt_out_timestamp',
            'privacy_notice_version', 'ip_address_hashed', 'created_at',
        ]
        read_only_fields = ['opt_out_timestamp', 'ip_address_hashed', 'created_at']


class CRMSegmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = CRMSegment
        fields = [
            'id', 'organization', 'name', 'description', 'filter_rules',
            'customer_count', 'is_dynamic', 'last_evaluated_at',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['customer_count', 'last_evaluated_at', 'created_at', 'updated_at']

    def validate_filter_rules(self, value):
        # Compiling validates the whitelist + structure; raises ValidationError.
        segment_service.compile_rules(value)
        return value


# ── Action payload serializers ────────────────────────────────────────
class TagActionSerializer(serializers.Serializer):
    tag_id = serializers.UUIDField()
    action = serializers.ChoiceField(choices=['add', 'remove'], default='add')


class ConsentRecordSerializer(serializers.Serializer):
    customer = serializers.UUIDField()
    consent_given = serializers.BooleanField(default=False)
    consent_source = serializers.ChoiceField(
        choices=[c[0] for c in CRMConsent._meta.get_field('consent_source').choices]
    )
    consent_text_snapshot = serializers.CharField(allow_blank=True, required=False)
    consent_text_version = serializers.CharField(required=False, default='v1')
    marketing_channels_allowed = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )
    privacy_notice_version = serializers.CharField(allow_blank=True, required=False)


class MergeSerializer(serializers.Serializer):
    duplicate_id = serializers.UUIDField()


class SegmentPreviewSerializer(serializers.Serializer):
    filter_rules = serializers.JSONField()
