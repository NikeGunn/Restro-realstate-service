"""
Analytics views - MVP metrics.
Simple counts only as per Phase 1 requirements.
Extended in Phase 2 & 3 for vertical-specific metrics.
Power Plan features: response time metrics, peak hours, trends.
"""
from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Avg, Q, Sum, F, ExpressionWrapper, DurationField
from django.db.models.functions import TruncDate, TruncHour, ExtractHour, ExtractWeekDay
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
        
        # Power Plan exclusive analytics
        if org.plan == 'power':
            response_data['power_analytics'] = self._get_power_analytics(org_id, start_date, conversations, messages)
        
        return Response(response_data)
    
    def _get_power_analytics(self, org_id, start_date, conversations, messages):
        """Get Power Plan exclusive analytics: response times, peak hours, trends."""
        power_data = {}
        
        # Calculate average response time
        # For each customer message, find the next AI/human message and compute difference
        try:
            customer_messages = Message.objects.filter(
                conversation__organization_id=org_id,
                sender=MessageSender.CUSTOMER,
                created_at__gte=start_date
            ).order_by('conversation_id', 'created_at')
            
            response_times = []
            for msg in customer_messages[:200]:  # Limit for performance
                # Find next AI or human message in same conversation
                next_response = Message.objects.filter(
                    conversation_id=msg.conversation_id,
                    sender__in=[MessageSender.AI, MessageSender.HUMAN],
                    created_at__gt=msg.created_at
                ).order_by('created_at').first()
                
                if next_response:
                    diff = (next_response.created_at - msg.created_at).total_seconds()
                    # Only count responses within 24 hours (ignore stale conversations)
                    if diff < 86400:
                        response_times.append(diff)
            
            if response_times:
                avg_response_seconds = sum(response_times) / len(response_times)
                min_response_seconds = min(response_times)
                max_response_seconds = max(response_times)
            else:
                avg_response_seconds = None
                min_response_seconds = None
                max_response_seconds = None
            
            power_data['response_time'] = {
                'avg_seconds': round(avg_response_seconds) if avg_response_seconds else None,
                'min_seconds': round(min_response_seconds) if min_response_seconds else None,
                'max_seconds': round(max_response_seconds) if max_response_seconds else None,
                'sample_size': len(response_times),
            }
        except Exception as e:
            power_data['response_time'] = {'error': str(e)}
        
        # Peak hours analysis
        try:
            hourly_distribution = list(
                messages.annotate(hour=ExtractHour('created_at'))
                .values('hour')
                .annotate(count=Count('id'))
                .order_by('hour')
            )
            
            # Find peak hours (top 3)
            sorted_hours = sorted(hourly_distribution, key=lambda x: x['count'], reverse=True)
            peak_hours = [h['hour'] for h in sorted_hours[:3]] if sorted_hours else []
            
            power_data['peak_hours'] = {
                'hourly_distribution': hourly_distribution,
                'peak_hours': peak_hours,
            }
        except Exception as e:
            power_data['peak_hours'] = {'error': str(e)}
        
        # Day of week analysis
        # ExtractWeekDay: Sunday=1, Monday=2, ..., Saturday=7
        try:
            dow_distribution = list(
                conversations.annotate(day_of_week=ExtractWeekDay('created_at'))
                .values('day_of_week')
                .annotate(count=Count('id'))
                .order_by('day_of_week')
            )
            
            day_names = {1: 'Sunday', 2: 'Monday', 3: 'Tuesday', 4: 'Wednesday', 5: 'Thursday', 6: 'Friday', 7: 'Saturday'}
            for item in dow_distribution:
                item['day_name'] = day_names.get(item['day_of_week'], 'Unknown')
            
            power_data['day_of_week'] = dow_distribution
        except Exception as e:
            power_data['day_of_week'] = []
        
        # AI efficiency metrics
        try:
            ai_resolved = conversations.filter(
                state=ConversationState.RESOLVED
            ).exclude(
                messages__sender=MessageSender.HUMAN
            ).count()
            
            total_resolved = conversations.filter(state=ConversationState.RESOLVED).count()
            
            power_data['ai_efficiency'] = {
                'ai_only_resolved': ai_resolved,
                'total_resolved': total_resolved,
                'ai_resolution_rate': round((ai_resolved / total_resolved * 100), 1) if total_resolved > 0 else 0,
            }
        except Exception as e:
            power_data['ai_efficiency'] = {'error': str(e)}
        
        # Channel performance comparison
        try:
            channel_perf = list(
                conversations.values('channel').annotate(
                    total=Count('id'),
                    resolved=Count('id', filter=Q(state=ConversationState.RESOLVED)),
                ).order_by('-total')
            )
            
            for ch in channel_perf:
                ch['resolution_rate'] = round((ch['resolved'] / ch['total'] * 100), 1) if ch['total'] > 0 else 0
            
            power_data['channel_performance'] = channel_perf
        except Exception as e:
            power_data['channel_performance'] = []
        
        return power_data
    
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
    Power Plan exclusive feature.
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
        
        # Check if Power Plan
        try:
            org = Organization.objects.get(id=org_id)
            if org.plan != 'power':
                return Response({'error': 'Power Plan required for location analytics.'}, status=403)
        except Organization.DoesNotExist:
            return Response({'error': 'Organization not found.'}, status=404)
        
        days = int(request.query_params.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)
        
        conversations = Conversation.objects.filter(
            organization_id=org_id,
            created_at__gte=start_date
        )
        
        by_location = list(
            conversations.values('location__id', 'location__name').annotate(
                conversations=Count('id'),
                resolved=Count('id', filter=Q(state=ConversationState.RESOLVED)),
                handoffs=Count('id', filter=Q(state='human_handoff')),
            ).order_by('-conversations')
        )
        
        # Calculate resolution rate for each location
        for loc in by_location:
            loc['location_id'] = loc.pop('location__id')
            loc['location_name'] = loc.pop('location__name') or 'Primary'
            loc['resolution_rate'] = round((loc['resolved'] / loc['conversations'] * 100), 1) if loc['conversations'] > 0 else 0
        
        # Get message counts per location
        messages = Message.objects.filter(
            conversation__organization_id=org_id,
            created_at__gte=start_date
        )
        
        for loc in by_location:
            loc_messages = messages.filter(
                conversation__location_id=loc['location_id']
            ).count()
            loc['messages'] = loc_messages
        
        return Response({
            'by_location': by_location,
            'period_days': days,
        })


class AnalyticsDailyView(APIView):
    """
    Get daily conversation counts and trends.
    Power Plan exclusive feature.
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
        
        # Check if Power Plan
        try:
            org = Organization.objects.get(id=org_id)
            if org.plan != 'power':
                return Response({'error': 'Power Plan required for daily trends.'}, status=403)
        except Organization.DoesNotExist:
            return Response({'error': 'Organization not found.'}, status=404)
        
        days = int(request.query_params.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)
        
        # Daily conversation counts
        daily_conversations = list(
            Conversation.objects.filter(
                organization_id=org_id,
                created_at__gte=start_date
            ).annotate(
                date=TruncDate('created_at')
            ).values('date').annotate(
                conversations=Count('id'),
                resolved=Count('id', filter=Q(state=ConversationState.RESOLVED)),
            ).order_by('date')
        )
        
        # Daily message counts
        daily_messages = list(
            Message.objects.filter(
                conversation__organization_id=org_id,
                created_at__gte=start_date
            ).annotate(
                date=TruncDate('created_at')
            ).values('date').annotate(
                messages=Count('id'),
                ai_messages=Count('id', filter=Q(sender=MessageSender.AI)),
                human_messages=Count('id', filter=Q(sender=MessageSender.HUMAN)),
                customer_messages=Count('id', filter=Q(sender=MessageSender.CUSTOMER)),
            ).order_by('date')
        )
        
        # Merge the data by date
        message_by_date = {str(m['date']): m for m in daily_messages}
        
        for conv in daily_conversations:
            date_str = str(conv['date'])
            conv['date'] = date_str  # Convert to string for JSON serialization
            if date_str in message_by_date:
                msg_data = message_by_date[date_str]
                conv['messages'] = msg_data['messages']
                conv['ai_messages'] = msg_data['ai_messages']
                conv['human_messages'] = msg_data['human_messages']
                conv['customer_messages'] = msg_data['customer_messages']
            else:
                conv['messages'] = 0
                conv['ai_messages'] = 0
                conv['human_messages'] = 0
                conv['customer_messages'] = 0
        
        # Calculate trends (compare to previous period)
        if len(daily_conversations) >= 2:
            mid_point = len(daily_conversations) // 2
            first_half = sum(d['conversations'] for d in daily_conversations[:mid_point])
            second_half = sum(d['conversations'] for d in daily_conversations[mid_point:])
            
            if first_half > 0:
                trend_percent = round(((second_half - first_half) / first_half) * 100, 1)
            else:
                trend_percent = 100 if second_half > 0 else 0
        else:
            trend_percent = 0
        
        return Response({
            'daily': daily_conversations,
            'period_days': days,
            'trend': {
                'direction': 'up' if trend_percent > 0 else 'down' if trend_percent < 0 else 'flat',
                'percent': abs(trend_percent),
            },
        })
