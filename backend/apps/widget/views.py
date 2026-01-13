from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.shortcuts import get_object_or_404
from django.http import HttpResponse, FileResponse
from django.conf import settings
import os
from apps.accounts.models import Organization
from apps.messaging.models import Conversation, Message, WidgetSession
from apps.ai_engine.services import AIService


class WidgetConfigView(APIView):
    """Get widget configuration for embedding"""
    permission_classes = [AllowAny]

    def get(self, request):
        widget_key = request.query_params.get('key')
        if not widget_key:
            return Response(
                {'error': 'Widget key is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            org = Organization.objects.get(widget_key=widget_key, is_active=True)
        except Organization.DoesNotExist:
            return Response(
                {'error': 'Invalid widget key'},
                status=status.HTTP_404_NOT_FOUND
            )

        return Response({
            'widget_key': str(org.widget_key),
            'business_name': org.name,
            'business_type': org.business_type,
            'color': org.widget_color,
            'position': org.widget_position,
            'greeting': org.widget_greeting,
        })


class WidgetSessionView(APIView):
    """Create a new widget session and conversation"""
    permission_classes = [AllowAny]

    def post(self, request):
        widget_key = request.data.get('widget_key')
        customer_name = request.data.get('customer_name')
        customer_email = request.data.get('customer_email')
        customer_phone = request.data.get('customer_phone')

        if not widget_key:
            return Response(
                {'error': 'Widget key is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            org = Organization.objects.get(widget_key=widget_key, is_active=True)
        except Organization.DoesNotExist:
            return Response(
                {'error': 'Invalid widget key'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Create widget session
        session = WidgetSession.objects.create(
            organization=org,
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            ip_address=self._get_client_ip(request),
        )

        # Create conversation
        conversation = Conversation.objects.create(
            organization=org,
            channel='website',
            customer_name=customer_name or 'Website Visitor',
            customer_email=customer_email or '',
            customer_phone=customer_phone or '',
            state='ai_handling',
        )

        # Link session to conversation
        session.conversation = conversation
        session.save()

        return Response({
            'session_id': str(session.id),
            'conversation_id': str(conversation.id),
        }, status=status.HTTP_201_CREATED)

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')


class WidgetMessageView(APIView):
    """Send a message from the widget"""
    permission_classes = [AllowAny]

    def post(self, request):
        session_id = request.data.get('session_id')
        conversation_id = request.data.get('conversation_id')
        content = request.data.get('content', '').strip()

        if not all([session_id, conversation_id, content]):
            return Response(
                {'error': 'session_id, conversation_id, and content are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate session
        try:
            session = WidgetSession.objects.get(
                id=session_id,
                conversation_id=conversation_id
            )
        except WidgetSession.DoesNotExist:
            return Response(
                {'error': 'Invalid session'},
                status=status.HTTP_403_FORBIDDEN
            )

        conversation = session.conversation

        # Create customer message
        customer_message = Message.objects.create(
            conversation=conversation,
            sender='customer',
            content=content,
        )

        # Update conversation timestamps
        conversation.last_message_at = customer_message.created_at
        conversation.save(update_fields=['last_message_at', 'updated_at'])

        response_data = {
            'message_id': str(customer_message.id),
            'response': None,
            'handoff_initiated': False,
        }

        # If not locked by human, get AI response
        if not conversation.is_locked and conversation.state in ['new', 'ai_handling', 'awaiting_user']:
            try:
                ai_service = AIService(conversation)
                ai_result = ai_service.process_message(content)

                # Process any extracted booking data
                self._process_extracted_data(session.organization, conversation, ai_result)

                # Create AI message
                ai_message = Message.objects.create(
                    conversation=conversation,
                    sender='ai',
                    content=ai_result['content'],
                )

                response_data['response'] = {
                    'sender': 'ai',
                    'content': ai_result['content'],
                }

                # Handle handoff if needed
                if ai_result.get('needs_handoff'):
                    from apps.handoff.models import HandoffAlert
                    HandoffAlert.objects.create(
                        conversation=conversation,
                        reason=ai_result.get('handoff_reason', 'ai_requested'),
                        triggered_by_ai=True,
                    )
                    conversation.state = 'human_handoff'
                    conversation.save(update_fields=['state', 'updated_at'])
                    response_data['handoff_initiated'] = True

            except Exception as e:
                # Log error but don't fail the request
                import traceback
                print(f"AI response error: {e}")
                print(traceback.format_exc())

        return Response(response_data)
    
    def _process_extracted_data(self, organization, conversation, ai_result):
        """
        Process extracted data from AI response.
        Creates bookings, leads, appointments etc. based on the extracted data.
        """
        extracted_data = ai_result.get('extracted_data', {})
        
        if not extracted_data:
            return
        
        # Handle booking cancellation for restaurant businesses
        if extracted_data.get('cancel_booking_code') and organization.business_type == 'restaurant':
            try:
                from apps.restaurant.models import Booking
                
                cancel_code = extracted_data.get('cancel_booking_code', '').strip().upper()
                if cancel_code:
                    booking = Booking.objects.filter(
                        organization=organization,
                        confirmation_code=cancel_code,
                        status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED]
                    ).first()
                    
                    if booking:
                        booking.cancel(reason="Cancelled by customer via website widget")
                        print(f"❌ Booking cancelled via widget: {cancel_code}")
            except Exception as e:
                import traceback
                print(f"Error cancelling booking: {e}")
                print(traceback.format_exc())
        
        # Handle booking intent for restaurant businesses
        if extracted_data.get('booking_intent') and organization.business_type == 'restaurant':
            try:
                from apps.restaurant.booking_service import process_booking_from_ai_response
                
                booking = process_booking_from_ai_response(
                    organization=organization,
                    conversation=conversation,
                    ai_response=ai_result,
                    source='website'
                )
                
                if booking:
                    print(f"📅 Booking created from widget: {booking.confirmation_code}")
            except Exception as e:
                import traceback
                print(f"Error processing booking data: {e}")
                print(traceback.format_exc())
        
        # Handle lead/appointment intent for real estate businesses
        if organization.business_type == 'real_estate':
            if extracted_data.get('lead_intent') or extracted_data.get('appointment_intent'):
                try:
                    from apps.realestate.lead_service import process_realestate_from_ai_response
                    
                    result = process_realestate_from_ai_response(
                        organization=organization,
                        conversation=conversation,
                        ai_response=ai_result,
                        source='website'
                    )
                    
                    if result.get('lead'):
                        print(f"🏠 Lead created from widget: {result['lead'].id}")
                    if result.get('appointment'):
                        print(f"📅 Appointment created from widget: {result['appointment'].confirmation_code}")
                except Exception as e:
                    import traceback
                    print(f"Error processing real estate data: {e}")
                    print(traceback.format_exc())


class WidgetConversationView(APIView):
    """Get conversation history for widget"""
    permission_classes = [AllowAny]

    def get(self, request, conversation_id):
        session_id = request.query_params.get('session_id')

        if not session_id:
            return Response(
                {'error': 'session_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate session
        try:
            session = WidgetSession.objects.get(
                id=session_id,
                conversation_id=conversation_id
            )
        except WidgetSession.DoesNotExist:
            return Response(
                {'error': 'Invalid session'},
                status=status.HTTP_403_FORBIDDEN
            )

        conversation = session.conversation
        messages = conversation.messages.order_by('created_at').values(
            'id', 'sender', 'content', 'created_at'
        )

        return Response({
            'conversation_id': str(conversation.id),
            'state': conversation.state,
            'messages': list(messages),
        })


class WidgetJSView(APIView):
    """Serve the widget.js file"""
    permission_classes = [AllowAny]

    def get(self, request):
        widget_js_path = os.path.join(settings.STATIC_ROOT, 'widget.js')
        
        # Check if file exists
        if os.path.exists(widget_js_path):
            return FileResponse(
                open(widget_js_path, 'rb'),
                content_type='application/javascript'
            )
        
        # Fallback: return inline JavaScript with error message
        return HttpResponse(
            'console.error("Widget.js file not found. Please ensure static files are collected.");',
            content_type='application/javascript'
        )
