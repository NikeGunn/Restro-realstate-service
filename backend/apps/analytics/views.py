"""
Analytics views - MVP metrics.
Simple counts only as per Phase 1 requirements.
Extended in Phase 2 & 3 for vertical-specific metrics.
"""
from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Avg, Q, Sum
from django.db.models.functions import TruncDate
from rest_framework import permissions
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.accounts.models import OrganizationMembership, Organization
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
        
        # Get organization for business type
        try:
            org = Organization.objects.get(id=org_id)
        except Organization.DoesNotExist:
            return Response({'error': 'Organization not found.'}, status=404)
        
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
        
        response_data = {
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
        }
        
        # Add vertical-specific metrics
        if org.business_type == 'restaurant':
            response_data['restaurant'] = self._get_restaurant_metrics(org_id, start_date)
        elif org.business_type == 'real_estate':
            response_data['real_estate'] = self._get_realestate_metrics(org_id, start_date)
        
        return Response(response_data)
    
    def _get_restaurant_metrics(self, org_id, start_date):
        """Get restaurant-specific metrics."""
        try:
            from apps.restaurant.models import Booking
            
            bookings = Booking.objects.filter(
                organization_id=org_id,
                created_at__gte=start_date
            )
            
            total_bookings = bookings.count()
            confirmed_bookings = bookings.filter(status=Booking.Status.CONFIRMED).count()
            completed_bookings = bookings.filter(status=Booking.Status.COMPLETED).count()
            cancelled_bookings = bookings.filter(status=Booking.Status.CANCELLED).count()
            no_shows = bookings.filter(status=Booking.Status.NO_SHOW).count()
            
            total_guests = bookings.filter(
                status__in=[Booking.Status.CONFIRMED, Booking.Status.COMPLETED]
            ).aggregate(total=Sum('party_size'))['total'] or 0
            
            by_source = dict(
                bookings.values('source').annotate(count=Count('id')).values_list('source', 'count')
            )
            
            return {
                'bookings': {
                    'total': total_bookings,
                    'confirmed': confirmed_bookings,
                    'completed': completed_bookings,
                    'cancelled': cancelled_bookings,
                    'no_shows': no_shows,
                    'total_guests': total_guests,
                    'by_source': by_source,
                }
            }
        except Exception as e:
            return {'error': str(e)}
    
    def _get_realestate_metrics(self, org_id, start_date):
        """Get real estate-specific metrics."""
        try:
            from apps.realestate.models import Lead, Appointment, PropertyListing
            
            # Lead metrics
            leads = Lead.objects.filter(
                organization_id=org_id,
                created_at__gte=start_date
            )
            
            total_leads = leads.count()
            leads_by_status = dict(
                leads.values('status').annotate(count=Count('id')).values_list('status', 'count')
            )
            leads_by_intent = dict(
                leads.values('intent').annotate(count=Count('id')).values_list('intent', 'count')
            )
            avg_lead_score = leads.aggregate(avg=Avg('lead_score'))['avg'] or 0
            
            converted_leads = leads_by_status.get('converted', 0)
            conversion_rate = round((converted_leads / total_leads * 100), 1) if total_leads > 0 else 0
            
            # Appointment metrics
            appointments = Appointment.objects.filter(
                organization_id=org_id,
                created_at__gte=start_date
            )
            
            total_appointments = appointments.count()
            appointments_by_status = dict(
                appointments.values('status').annotate(count=Count('id')).values_list('status', 'count')
            )
            
            # Property metrics
            active_listings = PropertyListing.objects.filter(
                organization_id=org_id,
                status=PropertyListing.Status.ACTIVE
            ).count()
            
            sold_in_period = PropertyListing.objects.filter(
                organization_id=org_id,
                sold_date__gte=start_date.date()
            ).count()
            
            return {
                'leads': {
                    'total': total_leads,
                    'by_status': leads_by_status,
                    'by_intent': leads_by_intent,
                    'avg_score': round(avg_lead_score, 1),
                    'conversion_rate': conversion_rate,
                },
                'appointments': {
                    'total': total_appointments,
                    'by_status': appointments_by_status,
                },
                'properties': {
                    'active_listings': active_listings,
                    'sold_in_period': sold_in_period,
                }
            }
        except Exception as e:
            return {'error': str(e)}


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
