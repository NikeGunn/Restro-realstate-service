"""
Analytics views - MVP metrics.
Simple counts only as per Phase 1 requirements.
"""
from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Avg, Q
from django.db.models.functions import TruncDate
from rest_framework import permissions
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.accounts.models import OrganizationMembership
from apps.messaging.models import Conversation, Message, MessageSender, ConversationState
from apps.handoff.models import HandoffAlert


class AnalyticsOverviewView(APIView):
    """
    Get overview analytics for an organization.
    MVP metrics only - simple counts.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        org_id = request.query_params.get('organization')
        if not org_id:
            return Response({'error': 'Organization ID required.'}, status=400)
        
        # Verify access
        if not OrganizationMembership.objects.filter(
            user=request.user,
            organization_id=org_id
        ).exists():
            return Response({'error': 'Access denied.'}, status=403)
        
        # Time range
        days = int(request.query_params.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)
        
        # Get conversations
        conversations = Conversation.objects.filter(
            organization_id=org_id,
            created_at__gte=start_date
        )
        
        # Get messages
        messages = Message.objects.filter(
            conversation__organization_id=org_id,
            created_at__gte=start_date
        )
        
        # Calculate metrics
        total_conversations = conversations.count()
        total_messages = messages.count()
        
        # AI vs Human handled
        ai_messages = messages.filter(sender=MessageSender.AI).count()
        human_messages = messages.filter(sender=MessageSender.HUMAN).count()
        customer_messages = messages.filter(sender=MessageSender.CUSTOMER).count()
        
        # Conversations by state
        conversations_by_state = dict(
            conversations.values('state').annotate(count=Count('id')).values_list('state', 'count')
        )
        
        # Handoff stats
        handoffs = HandoffAlert.objects.filter(
            conversation__organization_id=org_id,
            created_at__gte=start_date
        )
        total_handoffs = handoffs.count()
        resolved_handoffs = handoffs.filter(is_resolved=True).count()
        
        # Average response time (simplified - time between customer message and next AI/human message)
        # For MVP, we'll skip complex calculation and return None
        avg_response_time = None
        
        return Response({
            'period': {
                'days': days,
                'start': start_date.isoformat(),
                'end': timezone.now().isoformat(),
            },
            'conversations': {
                'total': total_conversations,
                'by_state': conversations_by_state,
            },
            'messages': {
                'total': total_messages,
                'customer': customer_messages,
                'ai': ai_messages,
                'human': human_messages,
            },
            'handoffs': {
                'total': total_handoffs,
                'resolved': resolved_handoffs,
                'pending': total_handoffs - resolved_handoffs,
            },
            'avg_response_time_seconds': avg_response_time,
        })


class AnalyticsByChannelView(APIView):
    """
    Get analytics breakdown by channel.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        org_id = request.query_params.get('organization')
        if not org_id:
            return Response({'error': 'Organization ID required.'}, status=400)
        
        if not OrganizationMembership.objects.filter(
            user=request.user,
            organization_id=org_id
        ).exists():
            return Response({'error': 'Access denied.'}, status=403)
        
        days = int(request.query_params.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)
        
        conversations = Conversation.objects.filter(
            organization_id=org_id,
            created_at__gte=start_date
        )
        
        by_channel = list(
            conversations.values('channel').annotate(
                conversations=Count('id')
            ).order_by('-conversations')
        )
        
        # Add message counts per channel
        for channel_stat in by_channel:
            channel = channel_stat['channel']
            message_count = Message.objects.filter(
                conversation__organization_id=org_id,
                conversation__channel=channel,
                created_at__gte=start_date
            ).count()
            channel_stat['messages'] = message_count
        
        return Response(by_channel)


class AnalyticsByLocationView(APIView):
    """
    Get analytics breakdown by location.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        org_id = request.query_params.get('organization')
        if not org_id:
            return Response({'error': 'Organization ID required.'}, status=400)
        
        if not OrganizationMembership.objects.filter(
            user=request.user,
            organization_id=org_id
        ).exists():
            return Response({'error': 'Access denied.'}, status=403)
        
        days = int(request.query_params.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)
        
        conversations = Conversation.objects.filter(
            organization_id=org_id,
            created_at__gte=start_date
        )
        
        by_location = list(
            conversations.values('location__id', 'location__name').annotate(
                count=Count('id')
            ).order_by('-count')
        )
        
        return Response({
            'by_location': by_location,
        })


class AnalyticsDailyView(APIView):
    """
    Get daily conversation counts.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        org_id = request.query_params.get('organization')
        if not org_id:
            return Response({'error': 'Organization ID required.'}, status=400)
        
        if not OrganizationMembership.objects.filter(
            user=request.user,
            organization_id=org_id
        ).exists():
            return Response({'error': 'Access denied.'}, status=403)
        
        days = int(request.query_params.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)
        
        daily_counts = list(
            Conversation.objects.filter(
                organization_id=org_id,
                created_at__gte=start_date
            ).annotate(
                date=TruncDate('created_at')
            ).values('date').annotate(
                count=Count('id')
            ).order_by('date')
        )
        
        return Response({
            'daily': daily_counts,
        })
