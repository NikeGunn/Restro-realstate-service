"""
Knowledge base serializers.
"""
from rest_framework import serializers
from .models import KnowledgeBase, FAQ


class KnowledgeBaseSerializer(serializers.ModelSerializer):
    """Serializer for KnowledgeBase."""
    location_name = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeBase
        fields = [
            'id', 'organization', 'location', 'location_name',
            'business_description', 'opening_hours', 'contact_info',
            'services', 'additional_info', 'policies',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_location_name(self, obj):
        return obj.location.name if obj.location else None


class KnowledgeBaseCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating knowledge base."""

    class Meta:
        model = KnowledgeBase
        fields = [
            'organization', 'location', 'business_description', 'opening_hours',
            'contact_info', 'services', 'additional_info', 'policies'
        ]


class FAQSerializer(serializers.ModelSerializer):
    """Serializer for FAQ."""
    organization = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()

    class Meta:
        model = FAQ
        fields = [
            'id', 'knowledge_base', 'organization', 'location', 
            'question', 'answer', 'order', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'location', 'created_at', 'updated_at']

    def get_organization(self, obj):
        return str(obj.knowledge_base.organization.id)
    
    def get_location(self, obj):
        return str(obj.knowledge_base.location.id) if obj.knowledge_base.location else None


class FAQCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating FAQ."""

    class Meta:
        model = FAQ
        fields = ['knowledge_base', 'question', 'answer', 'order']
