"""
Knowledge base views.
"""
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import KnowledgeBase, FAQ
from .serializers import (
    KnowledgeBaseSerializer,
    KnowledgeBaseCreateSerializer,
    FAQSerializer,
    FAQCreateSerializer,
)
from apps.accounts.models import OrganizationMembership, Organization


class KnowledgeBaseViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing knowledge bases.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        org_ids = OrganizationMembership.objects.filter(
            user=user
        ).values_list('organization_id', flat=True)

        queryset = KnowledgeBase.objects.filter(organization_id__in=org_ids)

        # Filter by organization
        org_id = self.request.query_params.get('organization')
        if org_id:
            queryset = queryset.filter(organization_id=org_id)

        # Filter by location
        location_id = self.request.query_params.get('location')
        if location_id:
            queryset = queryset.filter(location_id=location_id)

        return queryset.select_related('organization', 'location')

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return KnowledgeBaseCreateSerializer
        return KnowledgeBaseSerializer

    def perform_create(self, serializer):
        org_id = self.request.data.get('organization')
        # Verify membership
        if not OrganizationMembership.objects.filter(
            user=self.request.user,
            organization_id=org_id
        ).exists():
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('You do not have access to this organization.')

        serializer.save()

    @action(detail=False, methods=['get'])
    def for_organization(self, request):
        """Get all knowledge for an organization (org + location level)."""
        org_id = request.query_params.get('organization')
        if not org_id:
            return Response({'error': 'Organization ID required.'}, status=400)

        kbs = self.get_queryset().filter(organization_id=org_id)
        return Response(KnowledgeBaseSerializer(kbs, many=True).data)


class FAQViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing FAQs.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        org_ids = OrganizationMembership.objects.filter(
            user=user
        ).values_list('organization_id', flat=True)

        queryset = FAQ.objects.filter(knowledge_base__organization_id__in=org_ids)

        # Filter by organization
        org_id = self.request.query_params.get('organization')
        if org_id:
            queryset = queryset.filter(knowledge_base__organization_id=org_id)

        # Filter by knowledge_base
        kb_id = self.request.query_params.get('knowledge_base')
        if kb_id:
            queryset = queryset.filter(knowledge_base_id=kb_id)

        # Filter by active status
        active = self.request.query_params.get('active')
        if active is not None:
            queryset = queryset.filter(is_active=active.lower() == 'true')

        return queryset.select_related('knowledge_base', 'knowledge_base__organization')

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return FAQCreateSerializer
        return FAQSerializer

    def perform_create(self, serializer):
        kb_id = self.request.data.get('knowledge_base')
        try:
            kb = KnowledgeBase.objects.get(pk=kb_id)
        except KnowledgeBase.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound('Knowledge base not found.')
            
        if not OrganizationMembership.objects.filter(
            user=self.request.user,
            organization_id=kb.organization_id
        ).exists():
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('You do not have access to this organization.')

        serializer.save()

    @action(detail=False, methods=['post'])
    def reorder(self, request):
        """Reorder FAQs."""
        items = request.data.get('items', [])  # [{"id": "uuid", "order": 0}, ...]

        for item in items:
            FAQ.objects.filter(pk=item['id']).update(order=item['order'])

        return Response({'status': 'FAQs reordered.'})
