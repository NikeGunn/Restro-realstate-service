"""
Handoff views for alerts and escalations.
"""
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone

from .models import HandoffAlert, EscalationRule
from .serializers import HandoffAlertSerializer, EscalationRuleSerializer
from apps.accounts.models import OrganizationMembership


class HandoffAlertViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing handoff alerts.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = HandoffAlertSerializer

    def get_queryset(self):
        """Return alerts for user's organizations."""
        user = self.request.user
        org_ids = OrganizationMembership.objects.filter(
            user=user
        ).values_list('organization_id', flat=True)

        queryset = HandoffAlert.objects.filter(
            conversation__organization_id__in=org_ids
        ).select_related('conversation', 'acknowledged_by', 'resolved_by')

        # Filter by organization
        org_id = self.request.query_params.get('organization')
        if org_id:
            queryset = queryset.filter(conversation__organization_id=org_id)

        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter == 'pending':
            queryset = queryset.filter(is_resolved=False)
        elif status_filter == 'acknowledged':
            queryset = queryset.filter(is_acknowledged=True, is_resolved=False)
        elif status_filter == 'resolved':
            queryset = queryset.filter(is_resolved=True)

        # Filter by priority
        priority = self.request.query_params.get('priority')
        if priority:
            queryset = queryset.filter(priority=priority)

        return queryset

    @action(detail=True, methods=['post'])
    def acknowledge(self, request, pk=None):
        """Acknowledge an alert."""
        alert = self.get_object()
        alert.acknowledge(request.user)
        return Response(HandoffAlertSerializer(alert).data)

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """Resolve an alert."""
        alert = self.get_object()
        notes = request.data.get('notes', '')
        alert.resolve(request.user, notes)
        return Response(HandoffAlertSerializer(alert).data)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get alert statistics."""
        queryset = self.get_queryset()
        return Response({
            'total': queryset.count(),
            'pending': queryset.filter(is_resolved=False).count(),
            'acknowledged': queryset.filter(is_acknowledged=True, is_resolved=False).count(),
            'resolved_today': queryset.filter(
                is_resolved=True,
                resolved_at__date=timezone.now().date()
            ).count(),
            'by_priority': {
                'urgent': queryset.filter(priority='urgent', is_resolved=False).count(),
                'high': queryset.filter(priority='high', is_resolved=False).count(),
                'medium': queryset.filter(priority='medium', is_resolved=False).count(),
                'low': queryset.filter(priority='low', is_resolved=False).count(),
            }
        })


class EscalationRuleViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing escalation rules (Power plan).
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = EscalationRuleSerializer

    def get_queryset(self):
        user = self.request.user
        org_ids = OrganizationMembership.objects.filter(
            user=user,
            role=OrganizationMembership.Role.OWNER
        ).values_list('organization_id', flat=True)

        return EscalationRule.objects.filter(organization_id__in=org_ids)

    def perform_create(self, serializer):
        org_id = self.request.data.get('organization')
        # Verify user is owner
        if not OrganizationMembership.objects.filter(
            user=self.request.user,
            organization_id=org_id,
            role=OrganizationMembership.Role.OWNER
        ).exists():
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Only organization owners can create escalation rules.')
        serializer.save()
