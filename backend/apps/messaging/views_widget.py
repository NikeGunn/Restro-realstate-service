"""
Widget views for website chatbot.
"""
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils import timezone

from .models import (
    Conversation, Message, WidgetSession,
    Channel, ConversationState, MessageSender
)
from .serializers import (
    WidgetInitSerializer,
    WidgetMessageSerializer,
    WidgetSessionSerializer,
    MessageSerializer,
)
from apps.accounts.models import Organization, Location


class WidgetInitView(APIView):
    """
    Initialize widget session.
    Called when widget loads on a page.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = WidgetInitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        widget_key = serializer.validated_data['widget_key']

        # Find organization by widget key
        try:
            organization = Organization.objects.get(widget_key=widget_key, is_active=True)
        except Organization.DoesNotExist:
            return Response(
                {'error': 'Invalid widget key.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get or determine location
        location = None
        location_id = serializer.validated_data.get('location_id')
        if location_id:
            try:
                location = Location.objects.get(
                    pk=location_id,
                    organization=organization,
                    is_active=True
                )
            except Location.DoesNotExist:
                pass

        if not location:
            # Default to primary location
            location = organization.locations.filter(is_primary=True, is_active=True).first()
            if not location:
                location = organization.locations.filter(is_active=True).first()

        # Create widget session
        session = WidgetSession.objects.create(
            organization=organization,
            location=location,
            visitor_id=serializer.validated_data.get('visitor_id', ''),
            page_url=serializer.validated_data.get('page_url', ''),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            ip_address=self._get_client_ip(request),
            referrer=request.META.get('HTTP_REFERER', ''),
        )

        # Get available locations for selection
        locations = organization.locations.filter(is_active=True).values('id', 'name', 'city')

        return Response({
            'session_token': str(session.session_token),
            'organization': {
                'name': organization.name,
                'business_type': organization.business_type,
            },
            'widget': {
                'color': organization.widget_color,
                'position': organization.widget_position,
                'greeting': organization.widget_greeting,
            },
            'location': {
                'id': str(location.id) if location else None,
                'name': location.name if location else None,
            },
            'locations': list(locations),
            'needs_location_selection': len(locations) > 1 and not location_id,
        })

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')


class WidgetMessageView(APIView):
    """
    Handle messages from the widget.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = WidgetMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        session_token = serializer.validated_data['session_token']
        content = serializer.validated_data['content']

        # Find session
        try:
            session = WidgetSession.objects.select_related(
                'organization', 'location', 'conversation'
            ).get(session_token=session_token)
        except WidgetSession.DoesNotExist:
            return Response(
                {'error': 'Invalid session token.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Update session activity
        session.last_activity_at = timezone.now()
        session.save(update_fields=['last_activity_at'])

        # Get or create conversation
        conversation = session.conversation
        if not conversation:
            conversation = Conversation.objects.create(
                organization=session.organization,
                location=session.location,
                channel=Channel.WEBSITE,
                customer_name=serializer.validated_data.get('customer_name', ''),
                customer_email=serializer.validated_data.get('customer_email', ''),
                customer_phone=serializer.validated_data.get('customer_phone', ''),
                state=ConversationState.NEW,
            )
            session.conversation = conversation
            session.save(update_fields=['conversation'])
        else:
            # Update customer info if provided
            updated = False
            if serializer.validated_data.get('customer_name'):
                conversation.customer_name = serializer.validated_data['customer_name']
                updated = True
            if serializer.validated_data.get('customer_email'):
                conversation.customer_email = serializer.validated_data['customer_email']
                updated = True
            if serializer.validated_data.get('customer_phone'):
                conversation.customer_phone = serializer.validated_data['customer_phone']
                updated = True
            if updated:
                conversation.save()

        # Create customer message
        customer_message = Message.objects.create(
            conversation=conversation,
            content=content,
            sender=MessageSender.CUSTOMER,
        )

        # Process with AI (if not locked for human handling)
        if conversation.is_locked:
            # Just return the message, human will respond
            return Response({
                'message': MessageSerializer(customer_message).data,
                'response': None,
                'is_human_handling': True,
            })

        # Get AI response
        from apps.ai_engine.services import AIService
        ai_service = AIService(conversation)
        ai_response = ai_service.process_message(content)

        # Create AI response message
        ai_message = Message.objects.create(
            conversation=conversation,
            content=ai_response['content'],
            sender=MessageSender.AI,
            confidence_score=ai_response.get('confidence', 0),
            intent=ai_response.get('intent', ''),
            ai_metadata=ai_response.get('metadata', {}),
        )

        # Update conversation state
        if conversation.state == ConversationState.NEW:
            conversation.transition_state(ConversationState.AI_HANDLING)

        # Check if handoff is needed
        if ai_response.get('needs_handoff', False):
            conversation.transition_state(ConversationState.HUMAN_HANDOFF)
            # Create handoff alert
            from apps.handoff.models import HandoffAlert
            HandoffAlert.objects.create(
                conversation=conversation,
                reason=ai_response.get('handoff_reason', 'Low confidence'),
                priority='high' if ai_response.get('confidence', 0) < 0.3 else 'medium',
            )

        return Response({
            'message': MessageSerializer(customer_message).data,
            'response': MessageSerializer(ai_message).data,
            'is_human_handling': False,
        })


class WidgetHistoryView(APIView):
    """
    Get conversation history for widget.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        session_token = request.query_params.get('session_token')
        if not session_token:
            return Response(
                {'error': 'Session token required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            session = WidgetSession.objects.select_related('conversation').get(
                session_token=session_token
            )
        except WidgetSession.DoesNotExist:
            return Response(
                {'error': 'Invalid session token.'},
                status=status.HTTP_404_NOT_FOUND
            )

        if not session.conversation:
            return Response({'messages': []})

        messages = session.conversation.messages.all()[:50]
        return Response({
            'messages': MessageSerializer(messages, many=True).data,
            'is_human_handling': session.conversation.is_locked,
        })


class WidgetLocationSelectView(APIView):
    """
    Select/change location for widget session.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        session_token = request.data.get('session_token')
        location_id = request.data.get('location_id')

        if not session_token or not location_id:
            return Response(
                {'error': 'Session token and location ID required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            session = WidgetSession.objects.select_related('organization').get(
                session_token=session_token
            )
        except WidgetSession.DoesNotExist:
            return Response(
                {'error': 'Invalid session token.'},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            location = Location.objects.get(
                pk=location_id,
                organization=session.organization,
                is_active=True
            )
        except Location.DoesNotExist:
            return Response(
                {'error': 'Invalid location.'},
                status=status.HTTP_404_NOT_FOUND
            )

        session.location = location
        session.save(update_fields=['location'])

        # Update conversation location if exists
        if session.conversation:
            session.conversation.location = location
            session.conversation.save(update_fields=['location'])

        return Response({
            'location': {
                'id': str(location.id),
                'name': location.name,
            }
        })
