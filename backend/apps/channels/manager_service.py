"""
Manager Service - Handles manager WhatsApp messages and commands.
Provides flexible management capabilities via WhatsApp for managers on-the-go.
Includes booking confirmation checks and intelligent escalation.
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, List

from django.conf import settings
from django.utils import timezone
from django.db.models import Count, Q, Sum, Avg
from openai import OpenAI

from apps.accounts.models import Organization
from apps.messaging.models import Conversation, Message, MessageSender
from .models import ManagerNumber, TemporaryOverride, ManagerQuery, WhatsAppConfig, PendingManagerAction

logger = logging.getLogger(__name__)


class ManagerService:
    """
    Service for processing manager WhatsApp commands.
    Managers can:
    - Send status updates (closed early, fully booked, etc.)
    - Respond to customer query escalations
    - Get quick status reports
    """
    
    def __init__(self, organization: Organization):
        self.organization = organization
        self.client = None
        if settings.OPENAI_API_KEY:
            self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
    
    @classmethod
    def is_manager_message(cls, phone_number: str, organization: Organization) -> Optional[ManagerNumber]:
        """
        Check if a phone number belongs to a registered manager.
        Returns the ManagerNumber if found, None otherwise.
        """
        return ManagerNumber.get_by_phone(phone_number, organization)
    
    def process_manager_message(
        self, 
        manager: ManagerNumber, 
        message: str
    ) -> Dict[str, Any]:
        """
        Process an incoming message from a manager.
        Returns a response dict with 'response_text' and 'actions_taken'.
        """
        message_lower = message.lower().strip()
        
        # Update last message timestamp
        manager.last_message_at = timezone.now()
        manager.save(update_fields=['last_message_at'])
        
        # Check if there's a pending action requiring confirmation
        pending_action = PendingManagerAction.get_pending_for_manager(manager)
        if pending_action:
            return self._handle_pending_action_response(pending_action, message)
        
        # Check if this is a response to a pending query
        pending_query = self._check_for_query_response(manager, message)
        if pending_query:
            return self._handle_query_response(pending_query, message)
        
        # Check for command patterns
        result = self._detect_and_process_command(manager, message)
        
        return result
    
    def _handle_pending_action_response(self, pending_action: PendingManagerAction, response: str) -> Dict[str, Any]:
        """
        Handle manager's response to a pending action confirmation.
        """
        response_lower = response.lower().strip()
        
        # Check for confirmation patterns
        confirm_patterns = [
            'yes', 'confirm', 'ok', 'proceed', 'do it', 'go ahead',
            'i will call', 'i called', 'i have called', 'i\'ll call',
            'contacted', 'notified', 'informed', 'close it', 'close anyway'
        ]
        
        cancel_patterns = ['no', 'cancel', 'stop', 'don\'t', 'abort', 'wait']
        
        is_confirmed = any(p in response_lower for p in confirm_patterns)
        is_cancelled = any(p in response_lower for p in cancel_patterns)
        
        if is_confirmed:
            pending_action.confirm()
            
            if pending_action.action_type == PendingManagerAction.ActionType.CLOSE_WITH_BOOKINGS:
                # Now actually create the closing override
                return self._execute_close_with_bookings(pending_action.manager, pending_action)
            
            return {
                'response_text': "✅ Action confirmed and executed.",
                'actions_taken': ['action_confirmed']
            }
        
        elif is_cancelled:
            pending_action.cancel()
            return {
                'response_text': "❌ Action cancelled. No changes made.\n\nYour business remains open and bookings are unaffected.",
                'actions_taken': ['action_cancelled']
            }
        
        else:
            # Not clear - ask again
            context = pending_action.context_data
            booking_count = context.get('booking_count', 0)
            return {
                'response_text': f"⚠️ I didn't understand your response.\n\n"
                               f"You have {booking_count} confirmed booking(s) for today.\n\n"
                               f"Please reply:\n"
                               f"• \"Yes, I will call them\" - to confirm closing\n"
                               f"• \"Cancel\" - to keep the restaurant open",
                'actions_taken': ['awaiting_confirmation']
            }
    
    def _check_for_query_response(self, manager: ManagerNumber, message: str) -> Optional[ManagerQuery]:
        """
        Check if this message is a response to a pending manager query.
        """
        # Get most recent pending query for this manager
        pending = ManagerQuery.objects.filter(
            manager=manager,
            status=ManagerQuery.Status.PENDING,
            expires_at__gt=timezone.now()
        ).order_by('-created_at').first()
        
        return pending
    
    def _handle_query_response(self, query: ManagerQuery, response: str) -> Dict[str, Any]:
        """
        Handle manager's response to a customer query.
        """
        try:
            # Mark query as answered
            query.mark_answered(response)
            
            # Generate customer-friendly response based on manager's input
            customer_response = self._generate_customer_response(query, response)
            
            # Send response to customer
            self._send_customer_response(query, customer_response)
            
            return {
                'response_text': f"✅ Thanks! I've sent a response to the customer.\n\n"
                                f"Customer's question: \"{query.customer_query[:100]}...\"\n\n"
                                f"Your response has been professionally formatted and sent.",
                'actions_taken': ['query_response_sent'],
                'query_id': str(query.id)
            }
        except Exception as e:
            logger.exception(f"Error handling query response: {e}")
            return {
                'response_text': f"❌ Sorry, there was an error sending the response. Please try again.",
                'actions_taken': ['error'],
                'error': str(e)
            }
    
    def _generate_customer_response(self, query: ManagerQuery, manager_response: str) -> str:
        """
        Use AI to generate a professional customer response based on manager's input.
        """
        if not self.client:
            # Fallback: use manager's response directly
            return f"Thank you for waiting! Our manager says: {manager_response}"
        
        try:
            prompt = f"""You are a professional customer service AI for {self.organization.name}.
A customer asked: "{query.customer_query}"
The manager responded with: "{manager_response}"

Generate a professional, friendly response to send to the customer.
- Keep it concise and helpful
- Sound natural, not robotic
- Don't mention that you asked the manager
- Present the information as if you knew it
- If the manager said "no" or denied something, be polite about it

Response:"""
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.7
            )
            
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"AI response generation failed: {e}")
            return f"Thank you for waiting! Here's what I found out: {manager_response}"
    
    def _send_customer_response(self, query: ManagerQuery, response: str):
        """
        Send the response to the customer via their original channel.
        """
        from .whatsapp_service import WhatsAppService
        from .instagram_service import InstagramService
        from apps.messaging.models import Channel
        
        conversation = query.conversation
        
        # Create message record
        Message.objects.create(
            conversation=conversation,
            sender=MessageSender.AI,
            content=response,
            ai_metadata={
                'source': 'manager_query_response',
                'manager_query_id': str(query.id),
                'manager_name': query.manager.name
            }
        )
        
        # Send via WhatsApp if that was the channel
        if conversation.channel == Channel.WHATSAPP and conversation.customer_phone:
            try:
                whatsapp_config = WhatsAppConfig.objects.get(
                    organization=self.organization,
                    is_active=True
                )
                service = WhatsAppService(whatsapp_config)
                service.send_message(conversation.customer_phone, response)
                logger.info(f"✅ Sent manager response to WhatsApp: {conversation.customer_phone}")
            except Exception as e:
                logger.error(f"Failed to send WhatsApp response: {e}")
        
        # Send via Instagram if that was the channel
        elif conversation.channel == Channel.INSTAGRAM and conversation.channel_conversation_id:
            try:
                instagram_service = InstagramService.get_for_organization(self.organization)
                if instagram_service:
                    # channel_conversation_id stores the customer's Instagram ID
                    instagram_service.send_message(
                        recipient_id=conversation.channel_conversation_id,
                        text=response
                    )
                    logger.info(f"✅ Sent manager response to Instagram: {conversation.channel_conversation_id}")
                else:
                    logger.error("Instagram service not configured for organization")
            except Exception as e:
                logger.error(f"Failed to send Instagram response: {e}")
        
        # Mark as sent
        query.customer_response = response
        query.customer_response_sent = True
        query.save()
    
    def _detect_and_process_command(self, manager: ManagerNumber, message: str) -> Dict[str, Any]:
        """
        Detect the type of command and process it.
        Uses AI for natural language understanding.
        Distinguishes between questions (status requests) and statements (updates).
        """
        message_lower = message.lower().strip()
        
        # Helper to detect if message is a question
        is_question = (
            message_lower.startswith(('are ', 'is ', 'do ', 'does ', 'can ', 'what ', 'when ', 'how ')) or
            message_lower.endswith('?') or
            any(q in message_lower for q in ['are we', 'is it', 'are you', 'what is', 'what are'])
        )
        
        # BOOKING MANAGEMENT COMMANDS - Full CRUD operations
        if 'complete' in message_lower and ('booking' in message_lower or any(x in message_lower for x in ['all', 'today', 'reservation'])):
            return self._complete_bookings(manager, message)
        
        if 'no show' in message_lower or 'noshow' in message_lower or 'no-show' in message_lower:
            return self._mark_no_show(manager, message)
        
        if 'cancel booking' in message_lower or 'cancel reservation' in message_lower:
            return self._cancel_booking(manager, message)
        
        if 'confirm booking' in message_lower or 'approve booking' in message_lower:
            return self._confirm_booking(manager, message)
        
        if ('create' in message_lower or 'add' in message_lower or 'new' in message_lower) and ('booking' in message_lower or 'reservation' in message_lower):
            return self._create_booking(manager, message)
        
        if ('update' in message_lower or 'change' in message_lower or 'modify' in message_lower) and ('booking' in message_lower or 'reservation' in message_lower):
            return self._update_booking(manager, message)
        
        if 'delete booking' in message_lower or 'remove booking' in message_lower:
            return self._delete_booking(manager, message)
        
        if ('list' in message_lower or 'show' in message_lower or 'get' in message_lower) and ('booking' in message_lower or 'reservation' in message_lower):
            return self._list_bookings(manager, message)
        
        # ANALYTICS COMMANDS - Auto-detects plan and shows appropriate analytics
        if any(word in message_lower for word in ['analytics', 'stats', 'statistics', 'performance', 'metrics', 'dashboard']):
            return self._get_analytics(manager, message)
        
        # REAL ESTATE MANAGEMENT COMMANDS
        if self.organization.business_type == 'real_estate':
            # Lead management
            if any(word in message_lower for word in ['lead', 'leads']):
                if 'list' in message_lower or 'show' in message_lower:
                    return self._list_leads(manager, message)
                elif 'qualify' in message_lower or 'qualified' in message_lower:
                    return self._qualify_lead(manager, message)
                elif 'contact' in message_lower or 'contacted' in message_lower:
                    return self._mark_lead_contacted(manager, message)
                elif 'convert' in message_lower or 'converted' in message_lower:
                    return self._convert_lead(manager, message)
                elif 'lost' in message_lower:
                    return self._mark_lead_lost(manager, message)
            
            # Appointment management
            if any(word in message_lower for word in ['appointment', 'appointments', 'viewing']):
                if 'complete' in message_lower:
                    return self._complete_appointment(manager, message)
                elif 'confirm' in message_lower:
                    return self._confirm_appointment(manager, message)
                elif 'cancel' in message_lower:
                    return self._cancel_appointment(manager, message)
                elif 'no show' in message_lower or 'noshow' in message_lower:
                    return self._mark_appointment_no_show(manager, message)
                elif 'list' in message_lower or 'show' in message_lower or 'today' in message_lower:
                    return self._list_appointments(manager, message)
                elif 'create' in message_lower or 'schedule' in message_lower or 'book' in message_lower:
                    return self._create_appointment(manager, message)
            
            # Property management
            if any(word in message_lower for word in ['property', 'properties', 'listing']):
                if 'mark sold' in message_lower or 'sold' in message_lower:
                    return self._mark_property_sold(manager, message)
                elif 'mark rented' in message_lower or 'rented' in message_lower:
                    return self._mark_property_rented(manager, message)
                elif 'activate' in message_lower or 'active' in message_lower:
                    return self._activate_property(manager, message)
                elif 'list' in message_lower or 'show' in message_lower:
                    return self._list_properties(manager, message)
        
        # If it's a question about status, return status report instead of creating override
        if is_question and any(word in message_lower for word in ['open', 'closed', 'status', 'hours']):
            return self._get_current_status(manager)
        
        # Quick pattern matching for common commands (only for statements, not questions)
        if not is_question:
            # CLOSED status updates - high priority
            if any(word in message_lower for word in ['close', 'closed', 'closing', 'shut']):
                return self._process_hours_update(manager, message, is_closing=True)
            
            # OPEN status updates - but check for conflicts first
            if any(word in message_lower for word in ['open', 'opening', 'reopening', 'back']):
                return self._process_hours_update(manager, message, is_closing=False)
        
        if any(word in message_lower for word in ['booked', 'full', 'no table', 'no availability']):
            return self._process_availability_update(manager, message)
        
        if any(word in message_lower for word in ['status', 'report', 'bookings today', 'how many']):
            return self._get_status_report(manager)
        
        if any(word in message_lower for word in ['help', 'commands', 'what can']):
            return self._get_help_message(manager)
        
        if any(word in message_lower for word in ['cancel override', 'remove override', 'clear']):
            return self._cancel_overrides(manager, message)
        
        # Use AI to understand more complex messages
        return self._process_with_ai(manager, message)
    
    def _get_current_status(self, manager: ManagerNumber) -> Dict[str, Any]:
        """
        Return current business status including any active overrides.
        Called when manager asks a question like "Are we open?"
        """
        # Get active overrides
        active_overrides = TemporaryOverride.objects.filter(
            organization=self.organization,
            is_active=True,
            expires_at__gt=timezone.now()
        ).order_by('-priority', '-created_at')
        
        if active_overrides.exists():
            override = active_overrides.first()
            status_text = f"📊 Current Status\n━━━━━━━━━━━━━━━\n\n"
            status_text += f"🚨 Active Override:\n\"{override.processed_content}\"\n\n"
            status_text += f"⏰ Expires: {override.expires_at.strftime('%Y-%m-%d %H:%M')}\n"
            status_text += f"👤 Set by: {override.created_by_manager.name if override.created_by_manager else 'System'}\n\n"
            status_text += f"To remove this, send: \"cancel override\""
            
            return {
                'response_text': status_text,
                'actions_taken': ['status_query_answered'],
                'current_override': str(override.id)
            }
        else:
            return {
                'response_text': "📊 Current Status\n━━━━━━━━━━━━━━━\n\n"
                               "✅ Normal operations - no active overrides.\n\n"
                               "Customers are seeing your regular business hours and info.",
                'actions_taken': ['status_query_answered']
            }
    
    def _get_todays_bookings(self) -> List[Dict[str, Any]]:
        """Get confirmed bookings for today."""
        try:
            from apps.restaurant.models import Booking
            
            today = timezone.now().date()
            bookings = Booking.objects.filter(
                organization=self.organization,
                booking_date=today,
                status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED]
            ).order_by('booking_time')
            
            result = []
            for b in bookings:
                result.append({
                    'code': b.confirmation_code,
                    'name': b.customer_name,
                    'phone': b.customer_phone,
                    'time': str(b.booking_time),
                    'party_size': b.party_size,
                    'status': b.status
                })
            return result
        except Exception as e:
            logger.warning(f"Error getting today's bookings: {e}")
            return []
    
    # ==================== BOOKING MANAGEMENT COMMANDS ====================
    
    def _complete_bookings(self, manager: ManagerNumber, message: str) -> Dict[str, Any]:
        """Mark booking(s) as complete."""
        try:
            from apps.restaurant.models import Booking
            
            message_lower = message.lower()
            
            # Check if "all" or "today" is mentioned
            if any(word in message_lower for word in ['all', 'today', 'all today', 'all bookings']):
                # Complete all today's bookings
                today = timezone.now().date()
                bookings = Booking.objects.filter(
                    organization=self.organization,
                    booking_date=today,
                    status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED]
                )
                
                count = bookings.count()
                if count == 0:
                    return {
                        'response_text': "ℹ️ No bookings to complete for today.",
                        'actions_taken': ['booking_complete_none']
                    }
                
                bookings.update(
                    status=Booking.Status.COMPLETED,
                    updated_at=timezone.now()
                )
                
                return {
                    'response_text': f"✅ Marked {count} booking{'s' if count != 1 else ''} as complete for today.",
                    'actions_taken': ['booking_bulk_complete'],
                    'count': count
                }
            
            # Extract confirmation code (e.g., RES123, RESP2N3EO)
            code_pattern = r'\b(RES[A-Z0-9]+)\b'
            match = re.search(code_pattern, message.upper())
            
            if match:
                code = match.group(1)
                booking = Booking.objects.filter(
                    organization=self.organization,
                    confirmation_code=code
                ).first()
                
                if not booking:
                    return {
                        'response_text': f"❌ Booking {code} not found.",
                        'actions_taken': ['booking_not_found']
                    }
                
                booking.status = Booking.Status.COMPLETED
                booking.save()
                
                return {
                    'response_text': f"✅ Booking {code} marked as complete!\n\n"
                                   f"👤 {booking.customer_name}\n"
                                   f"👥 {booking.party_size} guests\n"
                                   f"⏰ {booking.booking_time}",
                    'actions_taken': ['booking_completed'],
                    'booking_code': code
                }
            
            return {
                'response_text': "ℹ️ Please specify:\n• \"Complete all bookings for today\", or\n• \"Complete RES123\" (booking code)",
                'actions_taken': ['booking_complete_help']
            }
            
        except Exception as e:
            logger.error(f"Error completing bookings: {e}")
            return {
                'response_text': f"❌ Error: {str(e)}",
                'actions_taken': ['error']
            }
    
    def _mark_no_show(self, manager: ManagerNumber, message: str) -> Dict[str, Any]:
        """Mark booking as no-show."""
        try:
            from apps.restaurant.models import Booking
            
            # Extract confirmation code
            code_pattern = r'\b(RES[A-Z0-9]+)\b'
            match = re.search(code_pattern, message.upper())
            
            if not match:
                return {
                    'response_text': "ℹ️ Please specify booking code:\nExample: \"No show RES123\"",
                    'actions_taken': ['no_show_help']
                }
            
            code = match.group(1)
            booking = Booking.objects.filter(
                organization=self.organization,
                confirmation_code=code
            ).first()
            
            if not booking:
                return {
                    'response_text': f"❌ Booking {code} not found.",
                    'actions_taken': ['booking_not_found']
                }
            
            booking.status = Booking.Status.NO_SHOW
            booking.save()
            
            return {
                'response_text': f"✅ Booking {code} marked as NO SHOW\n\n"
                               f"👤 {booking.customer_name}\n"
                               f"📞 {booking.customer_phone}\n"
                               f"👥 {booking.party_size} guests\n"
                               f"⏰ {booking.booking_time}",
                'actions_taken': ['booking_no_show'],
                'booking_code': code
            }
            
        except Exception as e:
            logger.error(f"Error marking no-show: {e}")
            return {
                'response_text': f"❌ Error: {str(e)}",
                'actions_taken': ['error']
            }
    
    def _cancel_booking(self, manager: ManagerNumber, message: str) -> Dict[str, Any]:
        """Cancel a booking."""
        try:
            from apps.restaurant.models import Booking
            
            # Extract confirmation code
            code_pattern = r'\b(RES[A-Z0-9]+)\b'
            match = re.search(code_pattern, message.upper())
            
            if not match:
                return {
                    'response_text': "ℹ️ Please specify booking code:\nExample: \"Cancel booking RES123\"",
                    'actions_taken': ['cancel_booking_help']
                }
            
            code = match.group(1)
            booking = Booking.objects.filter(
                organization=self.organization,
                confirmation_code=code
            ).first()
            
            if not booking:
                return {
                    'response_text': f"❌ Booking {code} not found.",
                    'actions_taken': ['booking_not_found']
                }
            
            booking.status = Booking.Status.CANCELLED
            booking.cancelled_at = timezone.now()
            booking.save()
            
            return {
                'response_text': f"✅ Booking {code} CANCELLED\n\n"
                               f"👤 {booking.customer_name}\n"
                               f"📞 {booking.customer_phone}\n"
                               f"👥 {booking.party_size} guests\n"
                               f"⏰ {booking.booking_time}",
                'actions_taken': ['booking_cancelled'],
                'booking_code': code
            }
            
        except Exception as e:
            logger.error(f"Error cancelling booking: {e}")
            return {
                'response_text': f"❌ Error: {str(e)}",
                'actions_taken': ['error']
            }
    
    def _confirm_booking(self, manager: ManagerNumber, message: str) -> Dict[str, Any]:
        """Confirm a pending booking."""
        try:
            from apps.restaurant.models import Booking
            from apps.accounts.models import User
            
            # Extract confirmation code
            code_pattern = r'\b(RES[A-Z0-9]+)\b'
            match = re.search(code_pattern, message.upper())
            
            if not match:
                return {
                    'response_text': "ℹ️ Please specify booking code:\nExample: \"Confirm booking RES123\"",
                    'actions_taken': ['confirm_booking_help']
                }
            
            code = match.group(1)
            booking = Booking.objects.filter(
                organization=self.organization,
                confirmation_code=code,
                status=Booking.Status.PENDING
            ).first()
            
            if not booking:
                return {
                    'response_text': f"❌ Pending booking {code} not found.",
                    'actions_taken': ['booking_not_found']
                }
            
            booking.status = Booking.Status.CONFIRMED
            booking.confirmed_at = timezone.now()
            # Try to get the manager's user account
            try:
                user = User.objects.filter(phone_number=manager.phone_number).first()
                if user:
                    booking.confirmed_by = user
            except:
                pass
            booking.save()
            
            return {
                'response_text': f"✅ Booking {code} CONFIRMED!\n\n"
                               f"👤 {booking.customer_name}\n"
                               f"📞 {booking.customer_phone}\n"
                               f"👥 {booking.party_size} guests\n"
                               f"⏰ {booking.booking_time}",
                'actions_taken': ['booking_confirmed'],
                'booking_code': code
            }
            
        except Exception as e:
            logger.error(f"Error confirming booking: {e}")
            return {
                'response_text': f"❌ Error: {str(e)}",
                'actions_taken': ['error']
            }
    
    def _create_booking(self, manager: ManagerNumber, message: str) -> Dict[str, Any]:
        """Create a new booking via WhatsApp."""
        try:
            from apps.restaurant.models import Booking
            import random
            import string
            
            # Use AI to extract booking details
            if not self.client:
                return {
                    'response_text': "❌ AI service not available. Please create booking via admin panel.",
                    'actions_taken': ['ai_unavailable']
                }
            
            prompt = f"""Extract booking details from this manager message:
"{message}"

Return JSON with:
{{
    "customer_name": "name",
    "customer_phone": "phone with country code",
    "party_size": number,
    "booking_date": "YYYY-MM-DD",
    "booking_time": "HH:MM",
    "special_requests": "any notes"
}}

If date/time not specified, assume today. If information is missing, set to null."""
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            
            import json
            from dateutil import parser as date_parser
            
            data = json.loads(response.choices[0].message.content)
            
            # Validate required fields
            if not data.get('customer_name') or not data.get('party_size'):
                return {
                    'response_text': "ℹ️ Please provide:\n• Customer name\n• Party size\n• Date (optional, defaults to today)\n• Time\n\nExample: \"Create booking for John, 4 people, today 7pm\"",
                    'actions_taken': ['create_booking_help']
                }
            
            # Parse date and time
            booking_date = timezone.now().date()
            if data.get('booking_date'):
                try:
                    booking_date = date_parser.parse(data['booking_date']).date()
                except:
                    pass
            
            booking_time = None
            if data.get('booking_time'):
                try:
                    booking_time = date_parser.parse(data['booking_time']).time()
                except:
                    pass
            
            # Generate confirmation code
            code = 'RES' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            
            # Create booking
            booking = Booking.objects.create(
                organization=self.organization,
                confirmation_code=code,
                customer_name=data['customer_name'],
                customer_phone=data.get('customer_phone', manager.phone_number),
                party_size=data['party_size'],
                booking_date=booking_date,
                booking_time=booking_time,
                special_requests=data.get('special_requests', ''),
                status=Booking.Status.CONFIRMED,
                confirmed_at=timezone.now(),
                source='manager_whatsapp'
            )
            
            return {
                'response_text': f"✅ Booking Created! Code: {code}\n\n"
                               f"👤 {booking.customer_name}\n"
                               f"📞 {booking.customer_phone}\n"
                               f"👥 {booking.party_size} guests\n"
                               f"📅 {booking.booking_date}\n"
                               f"⏰ {booking.booking_time or 'Not specified'}\n"
                               + (f"📝 {booking.special_requests}\n" if booking.special_requests else ""),
                'actions_taken': ['booking_created'],
                'booking_code': code
            }
            
        except Exception as e:
            logger.error(f"Error creating booking: {e}")
            return {
                'response_text': f"❌ Error creating booking: {str(e)}",
                'actions_taken': ['error']
            }
    
    def _update_booking(self, manager: ManagerNumber, message: str) -> Dict[str, Any]:
        """Update booking details."""
        try:
            from apps.restaurant.models import Booking
            
            # Extract confirmation code
            code_pattern = r'\b(RES[A-Z0-9]+)\b'
            match = re.search(code_pattern, message.upper())
            
            if not match:
                return {
                    'response_text': "ℹ️ Please specify booking code:\nExample: \"Update RES123 to 6 people\"",
                    'actions_taken': ['update_booking_help']
                }
            
            code = match.group(1)
            booking = Booking.objects.filter(
                organization=self.organization,
                confirmation_code=code
            ).first()
            
            if not booking:
                return {
                    'response_text': f"❌ Booking {code} not found.",
                    'actions_taken': ['booking_not_found']
                }
            
            # Use AI to extract update details
            if self.client:
                prompt = f"""Extract booking update details from this message:
"{message}"

Current booking:
- Name: {booking.customer_name}
- Phone: {booking.customer_phone}
- Party size: {booking.party_size}
- Date: {booking.booking_date}
- Time: {booking.booking_time}

Return JSON with fields to update (only changed fields):
{{
    "customer_name": "name or null",
    "customer_phone": "phone or null",
    "party_size": number or null,
    "booking_date": "YYYY-MM-DD or null",
    "booking_time": "HH:MM or null",
    "special_requests": "notes or null"
}}"""
                
                try:
                    response = self.client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=300,
                        temperature=0.2,
                        response_format={"type": "json_object"}
                    )
                    
                    import json
                    from dateutil import parser as date_parser
                    
                    data = json.loads(response.choices[0].message.content)
                    
                    # Update fields
                    updated_fields = []
                    if data.get('customer_name'):
                        booking.customer_name = data['customer_name']
                        updated_fields.append('name')
                    if data.get('customer_phone'):
                        booking.customer_phone = data['customer_phone']
                        updated_fields.append('phone')
                    if data.get('party_size'):
                        booking.party_size = data['party_size']
                        updated_fields.append('party size')
                    if data.get('booking_date'):
                        try:
                            booking.booking_date = date_parser.parse(data['booking_date']).date()
                            updated_fields.append('date')
                        except:
                            pass
                    if data.get('booking_time'):
                        try:
                            booking.booking_time = date_parser.parse(data['booking_time']).time()
                            updated_fields.append('time')
                        except:
                            pass
                    if data.get('special_requests'):
                        booking.special_requests = data['special_requests']
                        updated_fields.append('notes')
                    
                    if updated_fields:
                        booking.save()
                        return {
                            'response_text': f"✅ Booking {code} updated!\n\n"
                                           f"Updated: {', '.join(updated_fields)}\n\n"
                                           f"👤 {booking.customer_name}\n"
                                           f"📞 {booking.customer_phone}\n"
                                           f"👥 {booking.party_size} guests\n"
                                           f"📅 {booking.booking_date}\n"
                                           f"⏰ {booking.booking_time}",
                            'actions_taken': ['booking_updated'],
                            'booking_code': code
                        }
                    else:
                        return {
                            'response_text': "ℹ️ No changes detected. What would you like to update?",
                            'actions_taken': ['no_changes']
                        }
                    
                except Exception as e:
                    logger.error(f"AI update parsing failed: {e}")
            
            return {
                'response_text': f"ℹ️ To update booking {code}, specify:\n"
                               "• Name: \"Update RES123 name to John Smith\"\n"
                               "• Party size: \"Update RES123 to 6 people\"\n"
                               "• Time: \"Update RES123 time to 8pm\"",
                'actions_taken': ['update_booking_help']
            }
            
        except Exception as e:
            logger.error(f"Error updating booking: {e}")
            return {
                'response_text': f"❌ Error: {str(e)}",
                'actions_taken': ['error']
            }
    
    def _delete_booking(self, manager: ManagerNumber, message: str) -> Dict[str, Any]:
        """Delete a booking permanently."""
        try:
            from apps.restaurant.models import Booking
            
            # Extract confirmation code
            code_pattern = r'\b(RES[A-Z0-9]+)\b'
            match = re.search(code_pattern, message.upper())
            
            if not match:
                return {
                    'response_text': "ℹ️ Please specify booking code:\nExample: \"Delete booking RES123\"",
                    'actions_taken': ['delete_booking_help']
                }
            
            code = match.group(1)
            booking = Booking.objects.filter(
                organization=self.organization,
                confirmation_code=code
            ).first()
            
            if not booking:
                return {
                    'response_text': f"❌ Booking {code} not found.",
                    'actions_taken': ['booking_not_found']
                }
            
            # Store details before deletion
            details = f"👤 {booking.customer_name}\n📞 {booking.customer_phone}\n👥 {booking.party_size} guests"
            
            booking.delete()
            
            return {
                'response_text': f"✅ Booking {code} DELETED permanently\n\n{details}",
                'actions_taken': ['booking_deleted'],
                'booking_code': code
            }
            
        except Exception as e:
            logger.error(f"Error deleting booking: {e}")
            return {
                'response_text': f"❌ Error: {str(e)}",
                'actions_taken': ['error']
            }
    
    def _list_bookings(self, manager: ManagerNumber, message: str) -> Dict[str, Any]:
        """List bookings with optional filters."""
        try:
            from apps.restaurant.models import Booking
            
            message_lower = message.lower()
            
            # Determine filter
            if 'today' in message_lower:
                target_date = timezone.now().date()
                bookings = Booking.objects.filter(
                    organization=self.organization,
                    booking_date=target_date
                ).order_by('booking_time')
                title = "📅 Today's Bookings"
            elif 'tomorrow' in message_lower:
                target_date = timezone.now().date() + timedelta(days=1)
                bookings = Booking.objects.filter(
                    organization=self.organization,
                    booking_date=target_date
                ).order_by('booking_time')
                title = "📅 Tomorrow's Bookings"
            elif 'pending' in message_lower:
                bookings = Booking.objects.filter(
                    organization=self.organization,
                    status=Booking.Status.PENDING
                ).order_by('booking_date', 'booking_time')
                title = "⏳ Pending Bookings"
            elif 'confirmed' in message_lower:
                target_date = timezone.now().date()
                bookings = Booking.objects.filter(
                    organization=self.organization,
                    booking_date__gte=target_date,
                    status=Booking.Status.CONFIRMED
                ).order_by('booking_date', 'booking_time')[:10]
                title = "✅ Confirmed Bookings"
            else:
                # Default: today's bookings
                target_date = timezone.now().date()
                bookings = Booking.objects.filter(
                    organization=self.organization,
                    booking_date=target_date
                ).order_by('booking_time')
                title = "📅 Today's Bookings"
            
            if not bookings.exists():
                return {
                    'response_text': f"{title}\n━━━━━━━━━━━━━━━\n\nNo bookings found.",
                    'actions_taken': ['list_bookings_empty']
                }
            
            # Build response
            lines = [title, "━━━━━━━━━━━━━━━\n"]
            total_guests = 0
            
            for booking in bookings[:15]:  # Limit to 15 to avoid too long messages
                status_emoji = {
                    Booking.Status.PENDING: '⏳',
                    Booking.Status.CONFIRMED: '✅',
                    Booking.Status.COMPLETED: '✔️',
                    Booking.Status.CANCELLED: '❌',
                    Booking.Status.NO_SHOW: '🚫'
                }.get(booking.status, '📝')
                
                lines.append(
                    f"{status_emoji} {booking.confirmation_code}\n"
                    f"👤 {booking.customer_name}\n"
                    f"👥 {booking.party_size} guests\n"
                    f"⏰ {booking.booking_time or 'TBD'}\n"
                    f"📞 {booking.customer_phone}\n"
                )
                total_guests += booking.party_size
            
            if bookings.count() > 15:
                lines.append(f"\n... and {bookings.count() - 15} more")
            
            lines.append(f"\n📊 Total: {bookings.count()} bookings, {total_guests} guests")
            
            return {
                'response_text': '\n'.join(lines),
                'actions_taken': ['list_bookings'],
                'count': bookings.count()
            }
            
        except Exception as e:
            logger.error(f"Error listing bookings: {e}")
            return {
                'response_text': f"❌ Error: {str(e)}",
                'actions_taken': ['error']
            }
    
    # ==================== END BOOKING MANAGEMENT ====================
    
    # ==================== ANALYTICS COMMANDS ====================
    
    def _get_analytics(self, manager: ManagerNumber, message: str) -> Dict[str, Any]:
        """
        Get analytics based on organization's plan.
        Basic plan: Basic metrics only
        Power plan: Full analytics with advanced metrics
        Automatically detects plan - no need for user to specify.
        """
        try:
            from apps.messaging.models import ConversationState
            from django.db.models import Count, Q, Sum, Avg
            
            message_lower = message.lower()
            
            # Determine time period (default: 7 days, can specify 30, 90, etc.)
            days = 7
            if '30' in message or 'month' in message_lower:
                days = 30
            elif '90' in message or 'quarter' in message_lower:
                days = 90
            elif 'week' in message_lower:
                days = 7
            elif 'today' in message_lower:
                days = 1
            
            start_date = timezone.now() - timedelta(days=days)
            
            # Get conversations and messages
            conversations = Conversation.objects.filter(
                organization=self.organization,
                created_at__gte=start_date
            )
            
            messages = Message.objects.filter(
                conversation__organization=self.organization,
                created_at__gte=start_date
            )
            
            # BASIC METRICS (Available on all plans)
            total_conversations = conversations.count()
            total_messages = messages.count()
            
            # Message breakdown
            ai_messages = messages.filter(sender=MessageSender.AI).count()
            human_messages = messages.filter(sender=MessageSender.HUMAN).count()
            customer_messages = messages.filter(sender=MessageSender.CUSTOMER).count()
            
            # Conversations by state
            active_conversations = conversations.exclude(
                state__in=[ConversationState.RESOLVED, ConversationState.ARCHIVED]
            ).count()
            resolved_conversations = conversations.filter(state=ConversationState.RESOLVED).count()
            waiting_conversations = conversations.filter(state=ConversationState.AWAITING_USER).count()
            
            # Resolution rate
            resolution_rate = round((resolved_conversations / total_conversations * 100), 1) if total_conversations > 0 else 0
            
            # AI automation rate
            ai_automation_rate = round((ai_messages / total_messages * 100), 1) if total_messages > 0 else 0
            
            # Build basic response
            response_lines = [
                f"📊 Analytics ({days} days)",
                "━━━━━━━━━━━━━━━━━━━━",
                "",
                "💬 CONVERSATIONS:",
                f"  • Total: {total_conversations}",
                f"  • Active: {active_conversations}",
                f"  • Resolved: {resolved_conversations}",
                f"  • Resolution Rate: {resolution_rate}%",
                "",
                "📨 MESSAGES:",
                f"  • Total: {total_messages}",
                f"  • From Customers: {customer_messages}",
                f"  • AI Responses: {ai_messages}",
                f"  • Human Responses: {human_messages}",
                f"  • AI Automation: {ai_automation_rate}%",
            ]
            
            # Add vertical-specific metrics
            if self.organization.business_type == 'restaurant':
                restaurant_metrics = self._get_restaurant_analytics(start_date)
                if restaurant_metrics:
                    response_lines.extend([
                        "",
                        "🍽️ RESTAURANT METRICS:",
                        f"  • Bookings: {restaurant_metrics.get('total_bookings', 0)}",
                        f"  • Confirmed: {restaurant_metrics.get('confirmed', 0)}",
                        f"  • Completed: {restaurant_metrics.get('completed', 0)}",
                        f"  • Total Guests: {restaurant_metrics.get('total_guests', 0)}",
                        f"  • No-shows: {restaurant_metrics.get('no_shows', 0)}",
                    ])
            
            # POWER PLAN EXCLUSIVE ANALYTICS
            if self.organization.plan == 'power':
                response_lines.extend([
                    "",
                    "⚡ POWER ANALYTICS:",
                    "━━━━━━━━━━━━━━━━━━━━",
                ])
                
                # Response time analysis
                response_time_data = self._calculate_response_times(start_date)
                if response_time_data:
                    avg_response = response_time_data['avg_seconds']
                    if avg_response:
                        if avg_response < 60:
                            avg_str = f"{round(avg_response)}s"
                        elif avg_response < 3600:
                            avg_str = f"{round(avg_response/60)}m"
                        else:
                            avg_str = f"{round(avg_response/3600, 1)}h"
                        
                        response_lines.extend([
                            "",
                            "⚡ RESPONSE TIME:",
                            f"  • Average: {avg_str}",
                            f"  • Fastest: {round(response_time_data['min_seconds'])}s",
                            f"  • Sample: {response_time_data['sample_size']} responses",
                        ])
                
                # Peak hours
                peak_hours_data = self._get_peak_hours(messages)
                if peak_hours_data:
                    peak_hours_str = ", ".join([f"{h}:00" for h in peak_hours_data])
                    response_lines.extend([
                        "",
                        "📈 PEAK HOURS:",
                        f"  • Busiest: {peak_hours_str}",
                    ])
                
                # Channel performance
                channel_perf = self._get_channel_performance(conversations)
                if channel_perf:
                    response_lines.extend([
                        "",
                        "📱 CHANNEL PERFORMANCE:",
                    ])
                    for ch in channel_perf:
                        response_lines.append(f"  • {ch['channel'].upper()}: {ch['total']} convos ({ch['resolution_rate']}% resolved)")
                
                # AI efficiency
                ai_only_resolved = conversations.filter(
                    state=ConversationState.RESOLVED
                ).exclude(
                    messages__sender=MessageSender.HUMAN
                ).count()
                
                ai_resolution_rate = round((ai_only_resolved / resolved_conversations * 100), 1) if resolved_conversations > 0 else 0
                
                response_lines.extend([
                    "",
                    "🤖 AI EFFICIENCY:",
                    f"  • AI-Only Resolved: {ai_only_resolved}",
                    f"  • AI Resolution Rate: {ai_resolution_rate}%",
                ])
            else:
                # Basic plan users get a teaser
                response_lines.extend([
                    "",
                    "💡 Upgrade to Power Plan for:",
                    "  • Response time analytics",
                    "  • Peak hours insights",
                    "  • Channel performance",
                    "  • AI efficiency metrics",
                    "  • Day-of-week trends",
                ])
            
            response_text = "\n".join(response_lines)
            
            return {
                'response_text': response_text,
                'actions_taken': ['analytics_sent'],
                'plan': self.organization.plan,
                'period_days': days
            }
            
        except Exception as e:
            logger.error(f"Error getting analytics: {e}")
            return {
                'response_text': f"❌ Error getting analytics: {str(e)}",
                'actions_taken': ['error']
            }
    
    def _get_restaurant_analytics(self, start_date) -> Dict[str, Any]:
        """Get restaurant-specific analytics."""
        try:
            from apps.restaurant.models import Booking
            
            bookings = Booking.objects.filter(
                organization=self.organization,
                created_at__gte=start_date
            )
            
            return {
                'total_bookings': bookings.count(),
                'confirmed': bookings.filter(status=Booking.Status.CONFIRMED).count(),
                'completed': bookings.filter(status=Booking.Status.COMPLETED).count(),
                'cancelled': bookings.filter(status=Booking.Status.CANCELLED).count(),
                'no_shows': bookings.filter(status=Booking.Status.NO_SHOW).count(),
                'total_guests': bookings.filter(
                    status__in=[Booking.Status.CONFIRMED, Booking.Status.COMPLETED]
                ).aggregate(total=Sum('party_size'))['total'] or 0,
            }
        except Exception as e:
            logger.warning(f"Error getting restaurant analytics: {e}")
            return {}
    
    def _calculate_response_times(self, start_date) -> Optional[Dict[str, Any]]:
        """Calculate average response times (Power plan feature)."""
        try:
            customer_messages = Message.objects.filter(
                conversation__organization=self.organization,
                sender=MessageSender.CUSTOMER,
                created_at__gte=start_date
            ).order_by('conversation_id', 'created_at')
            
            response_times = []
            for msg in customer_messages[:100]:  # Limit for WhatsApp performance
                # Find next AI or human message in same conversation
                next_response = Message.objects.filter(
                    conversation_id=msg.conversation_id,
                    sender__in=[MessageSender.AI, MessageSender.HUMAN],
                    created_at__gt=msg.created_at
                ).order_by('created_at').first()
                
                if next_response:
                    diff = (next_response.created_at - msg.created_at).total_seconds()
                    # Only count responses within 24 hours
                    if diff < 86400:
                        response_times.append(diff)
            
            if response_times:
                return {
                    'avg_seconds': sum(response_times) / len(response_times),
                    'min_seconds': min(response_times),
                    'max_seconds': max(response_times),
                    'sample_size': len(response_times),
                }
            return None
        except Exception as e:
            logger.warning(f"Error calculating response times: {e}")
            return None
    
    def _get_peak_hours(self, messages) -> List[int]:
        """Get peak hours (Power plan feature)."""
        try:
            from django.db.models.functions import ExtractHour
            
            hourly_distribution = list(
                messages.annotate(hour=ExtractHour('created_at'))
                .values('hour')
                .annotate(count=Count('id'))
                .order_by('-count')[:3]  # Top 3 hours
            )
            
            return [h['hour'] for h in hourly_distribution]
        except Exception as e:
            logger.warning(f"Error getting peak hours: {e}")
            return []
    
    def _get_channel_performance(self, conversations) -> List[Dict]:
        """Get channel performance breakdown (Power plan feature)."""
        try:
            from apps.messaging.models import ConversationState
            
            channel_perf = list(
                conversations.values('channel').annotate(
                    total=Count('id'),
                    resolved=Count('id', filter=Q(state=ConversationState.RESOLVED)),
                ).order_by('-total')
            )
            
            for ch in channel_perf:
                ch['resolution_rate'] = round((ch['resolved'] / ch['total'] * 100), 1) if ch['total'] > 0 else 0
            
            return channel_perf
        except Exception as e:
            logger.warning(f"Error getting channel performance: {e}")
            return []
    
    # ==================== END ANALYTICS ====================
    
    # ==================== REAL ESTATE MANAGEMENT ====================
    
    def _list_leads(self, manager: ManagerNumber, message: str) -> Dict[str, Any]:
        """List leads with optional filters."""
        try:
            from apps.realestate.models import Lead
            
            message_lower = message.lower()
            
            # Determine filter
            if 'new' in message_lower:
                leads = Lead.objects.filter(
                    organization=self.organization,
                    status=Lead.Status.NEW
                ).order_by('-created_at')[:15]
                title = "🆕 New Leads"
            elif 'hot' in message_lower or 'high priority' in message_lower:
                leads = Lead.objects.filter(
                    organization=self.organization,
                    priority__in=[Lead.Priority.HOT, Lead.Priority.HIGH]
                ).order_by('-lead_score', '-created_at')[:15]
                title = "🔥 Hot Leads"
            elif 'qualified' in message_lower:
                leads = Lead.objects.filter(
                    organization=self.organization,
                    status=Lead.Status.QUALIFIED
                ).order_by('-created_at')[:15]
                title = "✅ Qualified Leads"
            elif 'today' in message_lower:
                today = timezone.now().date()
                leads = Lead.objects.filter(
                    organization=self.organization,
                    created_at__date=today
                ).order_by('-created_at')
                title = "📅 Today's Leads"
            else:
                # Recent leads
                leads = Lead.objects.filter(
                    organization=self.organization
                ).exclude(status__in=[Lead.Status.CONVERTED, Lead.Status.LOST]
                ).order_by('-created_at')[:15]
                title = "📋 Recent Leads"
            
            if not leads.exists():
                return {
                    'response_text': f"{title}\n━━━━━━━━━━━━━━━\n\nNo leads found.",
                    'actions_taken': ['list_leads_empty']
                }
            
            lines = [title, "━━━━━━━━━━━━━━━\n"]
            
            for lead in leads:
                priority_emoji = {
                    Lead.Priority.HOT: '🔥',
                    Lead.Priority.HIGH: '⚡',
                    Lead.Priority.MEDIUM: '📌',
                    Lead.Priority.LOW: '📝'
                }.get(lead.priority, '📝')
                
                intent_emoji = {
                    Lead.IntentType.BUY: '🏠',
                    Lead.IntentType.RENT: '🔑',
                    Lead.IntentType.SELL: '💰',
                    Lead.IntentType.INVEST: '📈'
                }.get(lead.intent, '💬')
                
                lines.append(
                    f"{priority_emoji} {lead.name}\n"
                    f"  {intent_emoji} {lead.intent.upper()} | Score: {lead.lead_score}\n"
                    f"  📞 {lead.phone}\n"
                    f"  Status: {lead.status.title()}\n"
                )
            
            lines.append(f"\n📊 Total: {leads.count()} leads")
            
            return {
                'response_text': '\n'.join(lines),
                'actions_taken': ['list_leads'],
                'count': leads.count()
            }
            
        except Exception as e:
            logger.error(f"Error listing leads: {e}")
            return {
                'response_text': f"❌ Error: {str(e)}",
                'actions_taken': ['error']
            }
    
    def _qualify_lead(self, manager: ManagerNumber, message: str) -> Dict[str, Any]:
        """Mark lead as qualified."""
        try:
            from apps.realestate.models import Lead
            
            # Extract lead name or phone
            words = message.split()
            # Try to find phone number or name after "qualify"
            qualifier_idx = next((i for i, w in enumerate(words) if 'qualify' in w.lower()), -1)
            
            if qualifier_idx == -1 or qualifier_idx + 1 >= len(words):
                return {
                    'response_text': "ℹ️ Please specify lead:\nExample: \"Qualify John Smith\" or \"Qualify 555-1234\"",
                    'actions_taken': ['qualify_lead_help']
                }
            
            search_term = ' '.join(words[qualifier_idx + 1:])
            
            # Search by name or phone
            lead = Lead.objects.filter(
                organization=self.organization,
                status__in=[Lead.Status.NEW, Lead.Status.CONTACTED]
            ).filter(
                Q(name__icontains=search_term) | Q(phone__icontains=search_term)
            ).first()
            
            if not lead:
                return {
                    'response_text': f"❌ Lead not found: {search_term}",
                    'actions_taken': ['lead_not_found']
                }
            
            lead.qualify()
            lead.calculate_score()
            
            return {
                'response_text': f"✅ Lead Qualified!\n\n"
                               f"👤 {lead.name}\n"
                               f"📞 {lead.phone}\n"
                               f"🎯 {lead.intent.upper()}\n"
                               f"⭐ Score: {lead.lead_score}",
                'actions_taken': ['lead_qualified'],
                'lead_id': str(lead.id)
            }
            
        except Exception as e:
            logger.error(f"Error qualifying lead: {e}")
            return {
                'response_text': f"❌ Error: {str(e)}",
                'actions_taken': ['error']
            }
    
    def _mark_lead_contacted(self, manager: ManagerNumber, message: str) -> Dict[str, Any]:
        """Mark lead as contacted."""
        try:
            from apps.realestate.models import Lead
            
            words = message.split()
            contact_idx = next((i for i, w in enumerate(words) if 'contact' in w.lower()), -1)
            
            if contact_idx == -1 or contact_idx + 1 >= len(words):
                return {
                    'response_text': "ℹ️ Please specify lead:\nExample: \"Contacted John Smith\"",
                    'actions_taken': ['contact_lead_help']
                }
            
            search_term = ' '.join(words[contact_idx + 1:])
            
            lead = Lead.objects.filter(
                organization=self.organization,
                status=Lead.Status.NEW
            ).filter(
                Q(name__icontains=search_term) | Q(phone__icontains=search_term)
            ).first()
            
            if not lead:
                return {
                    'response_text': f"❌ New lead not found: {search_term}",
                    'actions_taken': ['lead_not_found']
                }
            
            lead.mark_contacted()
            
            return {
                'response_text': f"✅ Marked as Contacted!\n\n"
                               f"👤 {lead.name}\n"
                               f"📞 {lead.phone}",
                'actions_taken': ['lead_contacted']
            }
            
        except Exception as e:
            logger.error(f"Error marking lead contacted: {e}")
            return {
                'response_text': f"❌ Error: {str(e)}",
                'actions_taken': ['error']
            }
    
    def _convert_lead(self, manager: ManagerNumber, message: str) -> Dict[str, Any]:
        """Mark lead as converted."""
        try:
            from apps.realestate.models import Lead
            
            words = message.split()
            convert_idx = next((i for i, w in enumerate(words) if 'convert' in w.lower()), -1)
            
            if convert_idx == -1 or convert_idx + 1 >= len(words):
                return {
                    'response_text': "ℹ️ Please specify lead:\nExample: \"Convert John Smith\"",
                    'actions_taken': ['convert_lead_help']
                }
            
            search_term = ' '.join(words[convert_idx + 1:])
            
            lead = Lead.objects.filter(
                organization=self.organization
            ).filter(
                Q(name__icontains=search_term) | Q(phone__icontains=search_term)
            ).first()
            
            if not lead:
                return {
                    'response_text': f"❌ Lead not found: {search_term}",
                    'actions_taken': ['lead_not_found']
                }
            
            lead.convert()
            
            return {
                'response_text': f"🎉 Lead Converted!\n\n"
                               f"👤 {lead.name}\n"
                               f"📞 {lead.phone}\n"
                               f"💼 {lead.intent.upper()}",
                'actions_taken': ['lead_converted']
            }
            
        except Exception as e:
            logger.error(f"Error converting lead: {e}")
            return {
                'response_text': f"❌ Error: {str(e)}",
                'actions_taken': ['error']
            }
    
    def _mark_lead_lost(self, manager: ManagerNumber, message: str) -> Dict[str, Any]:
        """Mark lead as lost."""
        try:
            from apps.realestate.models import Lead
            
            words = message.split()
            lost_idx = next((i for i, w in enumerate(words) if 'lost' in w.lower()), -1)
            
            if lost_idx == -1 or lost_idx + 1 >= len(words):
                return {
                    'response_text': "ℹ️ Please specify lead:\nExample: \"Mark lost John Smith\"",
                    'actions_taken': ['lost_lead_help']
                }
            
            search_term = ' '.join(words[lost_idx + 1:])
            
            lead = Lead.objects.filter(
                organization=self.organization
            ).filter(
                Q(name__icontains=search_term) | Q(phone__icontains=search_term)
            ).first()
            
            if not lead:
                return {
                    'response_text': f"❌ Lead not found: {search_term}",
                    'actions_taken': ['lead_not_found']
                }
            
            lead.status = Lead.Status.LOST
            lead.save()
            
            return {
                'response_text': f"❌ Lead Marked as Lost\n\n"
                               f"👤 {lead.name}\n"
                               f"📞 {lead.phone}",
                'actions_taken': ['lead_lost']
            }
            
        except Exception as e:
            logger.error(f"Error marking lead lost: {e}")
            return {
                'response_text': f"❌ Error: {str(e)}",
                'actions_taken': ['error']
            }
    
    def _list_appointments(self, manager: ManagerNumber, message: str) -> Dict[str, Any]:
        """List appointments."""
        try:
            from apps.realestate.models import Appointment
            
            message_lower = message.lower()
            
            if 'today' in message_lower:
                target_date = timezone.now().date()
                appointments = Appointment.objects.filter(
                    organization=self.organization,
                    appointment_date=target_date
                ).order_by('appointment_time')
                title = "📅 Today's Appointments"
            elif 'tomorrow' in message_lower:
                target_date = timezone.now().date() + timedelta(days=1)
                appointments = Appointment.objects.filter(
                    organization=self.organization,
                    appointment_date=target_date
                ).order_by('appointment_time')
                title = "📅 Tomorrow's Appointments"
            else:
                # Upcoming appointments
                today = timezone.now().date()
                appointments = Appointment.objects.filter(
                    organization=self.organization,
                    appointment_date__gte=today,
                    status__in=[Appointment.Status.SCHEDULED, Appointment.Status.CONFIRMED]
                ).order_by('appointment_date', 'appointment_time')[:15]
                title = "📅 Upcoming Appointments"
            
            if not appointments.exists():
                return {
                    'response_text': f"{title}\n━━━━━━━━━━━━━━━\n\nNo appointments found.",
                    'actions_taken': ['list_appointments_empty']
                }
            
            lines = [title, "━━━━━━━━━━━━━━━\n"]
            
            for apt in appointments:
                status_emoji = {
                    Appointment.Status.SCHEDULED: '📝',
                    Appointment.Status.CONFIRMED: '✅',
                    Appointment.Status.COMPLETED: '✔️',
                    Appointment.Status.CANCELLED: '❌',
                    Appointment.Status.NO_SHOW: '🚫'
                }.get(apt.status, '📝')
                
                lines.append(
                    f"{status_emoji} {apt.confirmation_code}\n"
                    f"  👤 {apt.lead.name}\n"
                    f"  📞 {apt.lead.phone}\n"
                    f"  📅 {apt.appointment_date} ⏰ {apt.appointment_time}\n"
                    f"  🏠 {apt.appointment_type.title()}\n"
                )
            
            lines.append(f"\n📊 Total: {appointments.count()} appointments")
            
            return {
                'response_text': '\n'.join(lines),
                'actions_taken': ['list_appointments'],
                'count': appointments.count()
            }
            
        except Exception as e:
            logger.error(f"Error listing appointments: {e}")
            return {
                'response_text': f"❌ Error: {str(e)}",
                'actions_taken': ['error']
            }
    
    def _complete_appointment(self, manager: ManagerNumber, message: str) -> Dict[str, Any]:
        """Mark appointment as complete."""
        try:
            from apps.realestate.models import Appointment
            
            # Extract confirmation code
            code_pattern = r'\b(APT[A-Z0-9]+)\b'
            match = re.search(code_pattern, message.upper())
            
            if not match:
                return {
                    'response_text': "ℹ️ Please specify appointment code:\nExample: \"Complete APT123\"",
                    'actions_taken': ['complete_appointment_help']
                }
            
            code = match.group(1)
            apt = Appointment.objects.filter(
                organization=self.organization,
                confirmation_code=code
            ).first()
            
            if not apt:
                return {
                    'response_text': f"❌ Appointment {code} not found.",
                    'actions_taken': ['appointment_not_found']
                }
            
            apt.complete()
            
            return {
                'response_text': f"✅ Appointment {code} COMPLETED!\n\n"
                               f"👤 {apt.lead.name}\n"
                               f"📅 {apt.appointment_date} {apt.appointment_time}\n"
                               f"🏠 {apt.appointment_type.title()}",
                'actions_taken': ['appointment_completed'],
                'appointment_code': code
            }
            
        except Exception as e:
            logger.error(f"Error completing appointment: {e}")
            return {
                'response_text': f"❌ Error: {str(e)}",
                'actions_taken': ['error']
            }
    
    def _confirm_appointment(self, manager: ManagerNumber, message: str) -> Dict[str, Any]:
        """Confirm appointment."""
        try:
            from apps.realestate.models import Appointment
            
            code_pattern = r'\b(APT[A-Z0-9]+)\b'
            match = re.search(code_pattern, message.upper())
            
            if not match:
                return {
                    'response_text': "ℹ️ Please specify appointment code:\nExample: \"Confirm APT123\"",
                    'actions_taken': ['confirm_appointment_help']
                }
            
            code = match.group(1)
            apt = Appointment.objects.filter(
                organization=self.organization,
                confirmation_code=code
            ).first()
            
            if not apt:
                return {
                    'response_text': f"❌ Appointment {code} not found.",
                    'actions_taken': ['appointment_not_found']
                }
            
            apt.confirm()
            
            return {
                'response_text': f"✅ Appointment {code} CONFIRMED!\n\n"
                               f"👤 {apt.lead.name}\n"
                               f"📞 {apt.lead.phone}\n"
                               f"📅 {apt.appointment_date} ⏰ {apt.appointment_time}",
                'actions_taken': ['appointment_confirmed'],
                'appointment_code': code
            }
            
        except Exception as e:
            logger.error(f"Error confirming appointment: {e}")
            return {
                'response_text': f"❌ Error: {str(e)}",
                'actions_taken': ['error']
            }
    
    def _cancel_appointment(self, manager: ManagerNumber, message: str) -> Dict[str, Any]:
        """Cancel appointment."""
        try:
            from apps.realestate.models import Appointment
            
            code_pattern = r'\b(APT[A-Z0-9]+)\b'
            match = re.search(code_pattern, message.upper())
            
            if not match:
                return {
                    'response_text': "ℹ️ Please specify appointment code:\nExample: \"Cancel APT123\"",
                    'actions_taken': ['cancel_appointment_help']
                }
            
            code = match.group(1)
            apt = Appointment.objects.filter(
                organization=self.organization,
                confirmation_code=code
            ).first()
            
            if not apt:
                return {
                    'response_text': f"❌ Appointment {code} not found.",
                    'actions_taken': ['appointment_not_found']
                }
            
            apt.cancel()
            
            return {
                'response_text': f"❌ Appointment {code} CANCELLED\n\n"
                               f"👤 {apt.lead.name}\n"
                               f"📅 {apt.appointment_date} {apt.appointment_time}",
                'actions_taken': ['appointment_cancelled'],
                'appointment_code': code
            }
            
        except Exception as e:
            logger.error(f"Error cancelling appointment: {e}")
            return {
                'response_text': f"❌ Error: {str(e)}",
                'actions_taken': ['error']
            }
    
    def _mark_appointment_no_show(self, manager: ManagerNumber, message: str) -> Dict[str, Any]:
        """Mark appointment as no-show."""
        try:
            from apps.realestate.models import Appointment
            
            code_pattern = r'\b(APT[A-Z0-9]+)\b'
            match = re.search(code_pattern, message.upper())
            
            if not match:
                return {
                    'response_text': "ℹ️ Please specify appointment code:\nExample: \"No show APT123\"",
                    'actions_taken': ['no_show_appointment_help']
                }
            
            code = match.group(1)
            apt = Appointment.objects.filter(
                organization=self.organization,
                confirmation_code=code
            ).first()
            
            if not apt:
                return {
                    'response_text': f"❌ Appointment {code} not found.",
                    'actions_taken': ['appointment_not_found']
                }
            
            apt.mark_no_show()
            
            return {
                'response_text': f"🚫 Appointment {code} marked as NO SHOW\n\n"
                               f"👤 {apt.lead.name}\n"
                               f"📞 {apt.lead.phone}\n"
                               f"📅 {apt.appointment_date} {apt.appointment_time}",
                'actions_taken': ['appointment_no_show'],
                'appointment_code': code
            }
            
        except Exception as e:
            logger.error(f"Error marking appointment no-show: {e}")
            return {
                'response_text': f"❌ Error: {str(e)}",
                'actions_taken': ['error']
            }
    
    def _create_appointment(self, manager: ManagerNumber, message: str) -> Dict[str, Any]:
        """Create new appointment."""
        try:
            from apps.realestate.models import Appointment, Lead
            
            if not self.client:
                return {
                    'response_text': "❌ AI service not available.",
                    'actions_taken': ['ai_unavailable']
                }
            
            prompt = f"""Extract appointment details from this message:
"{message}"

Return JSON with:
{{
    "lead_identifier": "name or phone",
    "date": "YYYY-MM-DD",
    "time": "HH:MM",
    "appointment_type": "viewing|consultation|virtual_tour|meeting",
    "notes": "any notes"
}}

If date/time not specified, set to null."""
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            
            import json
            from dateutil import parser as date_parser
            
            data = json.loads(response.choices[0].message.content)
            
            if not data.get('lead_identifier'):
                return {
                    'response_text': "ℹ️ Please specify lead name or phone:\nExample: \"Schedule viewing for John Smith tomorrow 2pm\"",
                    'actions_taken': ['create_appointment_help']
                }
            
            # Find lead
            lead = Lead.objects.filter(
                organization=self.organization
            ).filter(
                Q(name__icontains=data['lead_identifier']) | 
                Q(phone__icontains=data['lead_identifier'])
            ).first()
            
            if not lead:
                return {
                    'response_text': f"❌ Lead not found: {data['lead_identifier']}",
                    'actions_taken': ['lead_not_found']
                }
            
            # Parse date/time
            apt_date = None
            apt_time = None
            
            if data.get('date'):
                try:
                    apt_date = date_parser.parse(data['date']).date()
                except:
                    pass
            
            if data.get('time'):
                try:
                    apt_time = date_parser.parse(data['time']).time()
                except:
                    pass
            
            if not apt_date or not apt_time:
                return {
                    'response_text': "ℹ️ Please specify date and time:\nExample: \"Schedule viewing for John Smith tomorrow 2pm\"",
                    'actions_taken': ['appointment_datetime_required']
                }
            
            # Create appointment
            apt = Appointment.objects.create(
                organization=self.organization,
                lead=lead,
                appointment_type=data.get('appointment_type', 'viewing'),
                appointment_date=apt_date,
                appointment_time=apt_time,
                notes=data.get('notes', ''),
                status=Appointment.Status.SCHEDULED
            )
            
            return {
                'response_text': f"✅ Appointment Created! Code: {apt.confirmation_code}\n\n"
                               f"👤 {lead.name}\n"
                               f"📞 {lead.phone}\n"
                               f"📅 {apt_date}\n"
                               f"⏰ {apt_time}\n"
                               f"🏠 {apt.appointment_type.title()}",
                'actions_taken': ['appointment_created'],
                'appointment_code': apt.confirmation_code
            }
            
        except Exception as e:
            logger.error(f"Error creating appointment: {e}")
            return {
                'response_text': f"❌ Error: {str(e)}",
                'actions_taken': ['error']
            }
    
    def _list_properties(self, manager: ManagerNumber, message: str) -> Dict[str, Any]:
        """List property listings."""
        try:
            from apps.realestate.models import PropertyListing
            
            message_lower = message.lower()
            
            if 'active' in message_lower:
                properties = PropertyListing.objects.filter(
                    organization=self.organization,
                    status=PropertyListing.Status.ACTIVE
                ).order_by('-created_at')[:10]
                title = "🏠 Active Properties"
            elif 'sold' in message_lower:
                properties = PropertyListing.objects.filter(
                    organization=self.organization,
                    status=PropertyListing.Status.SOLD
                ).order_by('-sold_date')[:10]
                title = "✅ Sold Properties"
            else:
                properties = PropertyListing.objects.filter(
                    organization=self.organization
                ).exclude(status=PropertyListing.Status.OFF_MARKET
                ).order_by('-created_at')[:10]
                title = "🏠 Properties"
            
            if not properties.exists():
                return {
                    'response_text': f"{title}\n━━━━━━━━━━━━━━━\n\nNo properties found.",
                    'actions_taken': ['list_properties_empty']
                }
            
            lines = [title, "━━━━━━━━━━━━━━━\n"]
            
            for prop in properties:
                lines.append(
                    f"🏠 {prop.reference_number}\n"
                    f"  {prop.title}\n"
                    f"  💰 ${prop.price:,.0f}\n"
                    f"  📍 {prop.city}\n"
                    f"  Status: {prop.status.title()}\n"
                )
            
            lines.append(f"\n📊 Total: {properties.count()} properties")
            
            return {
                'response_text': '\n'.join(lines),
                'actions_taken': ['list_properties'],
                'count': properties.count()
            }
            
        except Exception as e:
            logger.error(f"Error listing properties: {e}")
            return {
                'response_text': f"❌ Error: {str(e)}",
                'actions_taken': ['error']
            }
    
    def _mark_property_sold(self, manager: ManagerNumber, message: str) -> Dict[str, Any]:
        """Mark property as sold."""
        try:
            from apps.realestate.models import PropertyListing
            
            code_pattern = r'\b(PROP[0-9]+)\b'
            match = re.search(code_pattern, message.upper())
            
            if not match:
                return {
                    'response_text': "ℹ️ Please specify property code:\nExample: \"Mark sold PROP123\"",
                    'actions_taken': ['mark_sold_help']
                }
            
            code = match.group(1)
            prop = PropertyListing.objects.filter(
                organization=self.organization,
                reference_number=code
            ).first()
            
            if not prop:
                return {
                    'response_text': f"❌ Property {code} not found.",
                    'actions_taken': ['property_not_found']
                }
            
            prop.status = PropertyListing.Status.SOLD
            prop.sold_date = timezone.now().date()
            prop.save()
            
            return {
                'response_text': f"🎉 Property {code} Marked as SOLD!\n\n"
                               f"🏠 {prop.title}\n"
                               f"💰 ${prop.price:,.0f}\n"
                               f"📍 {prop.city}",
                'actions_taken': ['property_sold'],
                'property_code': code
            }
            
        except Exception as e:
            logger.error(f"Error marking property sold: {e}")
            return {
                'response_text': f"❌ Error: {str(e)}",
                'actions_taken': ['error']
            }
    
    def _mark_property_rented(self, manager: ManagerNumber, message: str) -> Dict[str, Any]:
        """Mark property as rented."""
        try:
            from apps.realestate.models import PropertyListing
            
            code_pattern = r'\b(PROP[0-9]+)\b'
            match = re.search(code_pattern, message.upper())
            
            if not match:
                return {
                    'response_text': "ℹ️ Please specify property code:\nExample: \"Mark rented PROP123\"",
                    'actions_taken': ['mark_rented_help']
                }
            
            code = match.group(1)
            prop = PropertyListing.objects.filter(
                organization=self.organization,
                reference_number=code
            ).first()
            
            if not prop:
                return {
                    'response_text': f"❌ Property {code} not found.",
                    'actions_taken': ['property_not_found']
                }
            
            prop.status = PropertyListing.Status.RENTED
            prop.save()
            
            return {
                'response_text': f"✅ Property {code} Marked as RENTED!\n\n"
                               f"🏠 {prop.title}\n"
                               f"💰 ${prop.price:,.0f}\n"
                               f"📍 {prop.city}",
                'actions_taken': ['property_rented'],
                'property_code': code
            }
            
        except Exception as e:
            logger.error(f"Error marking property rented: {e}")
            return {
                'response_text': f"❌ Error: {str(e)}",
                'actions_taken': ['error']
            }
    
    def _activate_property(self, manager: ManagerNumber, message: str) -> Dict[str, Any]:
        """Activate property listing."""
        try:
            from apps.realestate.models import PropertyListing
            
            code_pattern = r'\b(PROP[0-9]+)\b'
            match = re.search(code_pattern, message.upper())
            
            if not match:
                return {
                    'response_text': "ℹ️ Please specify property code:\nExample: \"Activate PROP123\"",
                    'actions_taken': ['activate_property_help']
                }
            
            code = match.group(1)
            prop = PropertyListing.objects.filter(
                organization=self.organization,
                reference_number=code
            ).first()
            
            if not prop:
                return {
                    'response_text': f"❌ Property {code} not found.",
                    'actions_taken': ['property_not_found']
                }
            
            prop.status = PropertyListing.Status.ACTIVE
            prop.save()
            
            return {
                'response_text': f"✅ Property {code} ACTIVATED!\n\n"
                               f"🏠 {prop.title}\n"
                               f"💰 ${prop.price:,.0f}\n"
                               f"📍 {prop.city}",
                'actions_taken': ['property_activated'],
                'property_code': code
            }
            
        except Exception as e:
            logger.error(f"Error activating property: {e}")
            return {
                'response_text': f"❌ Error: {str(e)}",
                'actions_taken': ['error']
            }
    
    # ==================== END REAL ESTATE MANAGEMENT ====================
    
    def _process_hours_update(self, manager: ManagerNumber, message: str, is_closing: bool = True) -> Dict[str, Any]:
        """
        Process business hours/status updates.
        Examples: "We're closing early at 5pm today", "Closed for private event"
        
        Args:
            manager: The manager sending the update
            message: The message content
            is_closing: True if this is a CLOSING update (higher priority), 
                       False if this is an OPENING update
        """
        if not manager.can_update_hours:
            return {
                'response_text': "❌ Sorry, you don't have permission to update business hours.",
                'actions_taken': ['permission_denied']
            }
        
        # If closing, check for confirmed bookings first
        if is_closing and self.organization.business_type == 'restaurant':
            todays_bookings = self._get_todays_bookings()
            
            if todays_bookings:
                # There are confirmed bookings - ask for confirmation
                booking_count = len(todays_bookings)
                booking_details = "\n".join([
                    f"  • {b['name']} ({b['party_size']} guests) at {b['time']}"
                    for b in todays_bookings[:5]  # Show max 5
                ])
                
                if booking_count > 5:
                    booking_details += f"\n  ... and {booking_count - 5} more"
                
                # Create pending action
                pending = PendingManagerAction.objects.create(
                    organization=self.organization,
                    manager=manager,
                    action_type=PendingManagerAction.ActionType.CLOSE_WITH_BOOKINGS,
                    original_message=message,
                    context_data={
                        'booking_count': booking_count,
                        'bookings': todays_bookings[:10],
                        'is_closing': is_closing,
                        'parsed_message': message
                    },
                    expires_at=timezone.now() + timedelta(minutes=10)
                )
                
                return {
                    'response_text': f"⚠️ WAIT! You have {booking_count} confirmed booking(s) for today:\n\n"
                                   f"{booking_details}\n\n"
                                   f"These customers are expecting to visit!\n\n"
                                   f"Please reply:\n"
                                   f"• \"Yes, I will call them\" - I'll notify them myself\n"
                                   f"• \"Cancel\" - Keep the restaurant open\n\n"
                                   f"⏰ Waiting for your confirmation...",
                    'actions_taken': ['awaiting_booking_confirmation'],
                    'pending_action_id': str(pending.id),
                    'booking_count': booking_count
                }
        
        # No bookings or opening - proceed directly
        return self._execute_hours_update(manager, message, is_closing)
    
    def _execute_hours_update(self, manager: ManagerNumber, message: str, is_closing: bool) -> Dict[str, Any]:
        """Actually execute the hours update after confirmation (if needed)."""
        # Check for conflicting overrides
        existing_overrides = TemporaryOverride.objects.filter(
            organization=self.organization,
            is_active=True,
            override_type=TemporaryOverride.OverrideType.HOURS,
            expires_at__gt=timezone.now()
        )
        
        # If this is an "OPEN" update and there's a recent "CLOSED" override, 
        # deactivate the closed override first
        if not is_closing and existing_overrides.exists():
            # Deactivate old overrides when opening
            deactivated_count = existing_overrides.update(is_active=False)
            logger.info(f"📢 Deactivated {deactivated_count} previous hours overrides (now opening)")
        elif is_closing and existing_overrides.exists():
            # If closing and there are existing overrides, deactivate them to avoid conflicts
            deactivated_count = existing_overrides.update(is_active=False)
            logger.info(f"📢 Deactivated {deactivated_count} previous hours overrides (updating to closed)")
        
        # Parse the message to extract details
        parsed = self._parse_hours_message(message, is_closing=is_closing)
        
        # Create temporary override with appropriate priority
        # CLOSING updates get URGENT priority, OPENING updates get HIGH priority
        priority = TemporaryOverride.Priority.URGENT if is_closing else TemporaryOverride.Priority.HIGH
        
        override = TemporaryOverride.objects.create(
            organization=self.organization,
            override_type=TemporaryOverride.OverrideType.HOURS,
            priority=priority,
            original_message=message,
            processed_content=parsed['processed_content'],
            trigger_keywords=parsed['keywords'],
            created_by_manager=manager,
            starts_at=timezone.now(),
            expires_at=parsed['expires_at'],
            auto_expire_on_next_open=parsed.get('auto_expire', True)
        )
        
        logger.info(f"📢 Manager {manager.name} created hours override ({'CLOSED' if is_closing else 'OPEN'}): {message[:50]}")
        
        return {
            'response_text': f"✅ Got it! I've updated the status.\n\n"
                            f"📢 New message for customers:\n\"{parsed['processed_content']}\"\n\n"
                            f"⏰ This will expire: {parsed['expires_at'].strftime('%Y-%m-%d %H:%M')}\n\n"
                            f"To cancel this, send: \"cancel override\"",
            'actions_taken': ['hours_override_created'],
            'override_id': str(override.id)
        }
    
    def _execute_close_with_bookings(self, manager: ManagerNumber, pending_action: PendingManagerAction) -> Dict[str, Any]:
        """Execute closing after manager confirmed they'll handle the bookings."""
        context = pending_action.context_data
        booking_count = context.get('booking_count', 0)
        original_message = pending_action.original_message
        
        # Execute the actual close
        result = self._execute_hours_update(manager, original_message, is_closing=True)
        
        # Modify response to acknowledge the bookings
        result['response_text'] = (
            f"✅ Restaurant is now marked as CLOSED.\n\n"
            f"📞 Please remember to contact your {booking_count} customer(s) to inform them.\n\n"
            f"📢 Customers asking will now see:\n\"{result.get('processed_content', 'We are currently closed.')}\"\n\n"
            f"To re-open, send: \"We are open now\"\n"
            f"To cancel: \"cancel override\""
        )
        result['actions_taken'].append('bookings_acknowledged')
        
        return result
    
    def _parse_hours_message(self, message: str, is_closing: bool = True) -> Dict[str, Any]:
        """
        Parse a hours-related message to extract details.
        
        Args:
            message: The manager's message
            is_closing: True if this is a closing update, False if opening
        """
        message_lower = message.lower()
        now = timezone.now()
        
        # Default expiration: end of today or next business day
        default_expiry = now.replace(hour=23, minute=59, second=59)
        
        # Check for specific times
        time_pattern = r'(\d{1,2})\s*(?::(\d{2}))?\s*(am|pm|AM|PM)?'
        time_match = re.search(time_pattern, message)
        
        # Check for "today", "tonight", "tomorrow"
        if 'tomorrow' in message_lower:
            default_expiry = (now + timedelta(days=1)).replace(hour=23, minute=59, second=59)
        
        # Keywords for triggering this override
        keywords = ['hours', 'open', 'closed', 'closing', 'time', 'today']
        if 'early' in message_lower:
            keywords.append('early')
        if 'late' in message_lower:
            keywords.append('late')
        
        # Generate customer-facing message based on is_closing parameter
        if is_closing:
            # CLOSED message
            if time_match:
                time_str = time_match.group(0)
                processed = f"We are closing early today at {time_str}. We apologize for any inconvenience."
            else:
                processed = "We are currently closed. We apologize for any inconvenience and will be open again during our regular hours."
        else:
            # OPEN message
            processed = "Great news! We are now open and ready to serve you."
        
        return {
            'processed_content': processed,
            'keywords': keywords,
            'expires_at': default_expiry,
            'auto_expire': True
        }
    
    def _process_availability_update(self, manager: ManagerNumber, message: str) -> Dict[str, Any]:
        """
        Process availability updates (fully booked, no tables, etc.)
        """
        if not manager.can_update_hours:
            return {
                'response_text': "❌ Sorry, you don't have permission to update availability.",
                'actions_taken': ['permission_denied']
            }
        
        now = timezone.now()
        default_expiry = now.replace(hour=23, minute=59, second=59)
        
        # Generate customer message
        message_lower = message.lower()
        if 'full' in message_lower or 'booked' in message_lower:
            processed = "We are fully booked for today. Please try booking for another day or call us for waitlist options."
        elif 'no table' in message_lower:
            processed = "Unfortunately, we have no tables available at the moment. Please try again later or book for another time."
        else:
            processed = f"Availability update: {message}"
        
        override = TemporaryOverride.objects.create(
            organization=self.organization,
            override_type=TemporaryOverride.OverrideType.AVAILABILITY,
            priority=TemporaryOverride.Priority.HIGH,
            original_message=message,
            processed_content=processed,
            trigger_keywords=['booking', 'reservation', 'table', 'available', 'availability'],
            created_by_manager=manager,
            starts_at=timezone.now(),
            expires_at=default_expiry,
            auto_expire_on_next_open=True
        )
        
        return {
            'response_text': f"✅ Availability updated!\n\n"
                            f"📢 Message for customers asking about bookings:\n\"{processed}\"\n\n"
                            f"⏰ This expires at end of day.\n"
                            f"To cancel: \"cancel override\"",
            'actions_taken': ['availability_override_created'],
            'override_id': str(override.id)
        }
    
    def _cancel_overrides(self, manager: ManagerNumber, message: str) -> Dict[str, Any]:
        """
        Cancel active overrides created by this manager.
        """
        # Get active overrides
        overrides = TemporaryOverride.objects.filter(
            organization=self.organization,
            is_active=True,
            expires_at__gt=timezone.now()
        )
        
        if 'all' in message.lower():
            count = overrides.count()
            overrides.update(is_active=False)
            return {
                'response_text': f"✅ Cancelled {count} active override(s). Normal operations resumed.",
                'actions_taken': ['all_overrides_cancelled']
            }
        
        # Cancel most recent
        latest = overrides.first()
        if latest:
            latest.is_active = False
            latest.save()
            return {
                'response_text': f"✅ Cancelled override: \"{latest.original_message[:50]}...\"\n\nNormal operations resumed.",
                'actions_taken': ['override_cancelled'],
                'override_id': str(latest.id)
            }
        
        return {
            'response_text': "ℹ️ No active overrides to cancel. Everything is running normally.",
            'actions_taken': []
        }
    
    def _get_status_report(self, manager: ManagerNumber) -> Dict[str, Any]:
        """
        Get a quick status report for the manager.
        """
        from apps.messaging.models import Conversation, ConversationState
        
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Get conversation stats
        total_conversations = Conversation.objects.filter(
            organization=self.organization,
            created_at__gte=today_start
        ).count()
        
        active_conversations = Conversation.objects.filter(
            organization=self.organization,
            state__in=[ConversationState.AI_HANDLING, ConversationState.AWAITING_USER]
        ).count()
        
        handoff_conversations = Conversation.objects.filter(
            organization=self.organization,
            state=ConversationState.HUMAN_HANDOFF
        ).count()
        
        # Get booking stats (for restaurants)
        booking_stats = ""
        if self.organization.business_type == 'restaurant':
            try:
                from apps.restaurant.models import Booking
                today_bookings = Booking.objects.filter(
                    organization=self.organization,
                    booking_date=now.date()
                )
                pending = today_bookings.filter(status='pending').count()
                confirmed = today_bookings.filter(status='confirmed').count()
                booking_stats = f"\n\n📅 Bookings Today:\n   Confirmed: {confirmed}\n   Pending: {pending}"
            except:
                pass
        
        # Get active overrides
        active_overrides = TemporaryOverride.objects.filter(
            organization=self.organization,
            is_active=True,
            expires_at__gt=timezone.now()
        ).count()
        
        override_text = ""
        if active_overrides > 0:
            override_text = f"\n\n⚠️ Active Overrides: {active_overrides}"
        
        return {
            'response_text': f"📊 Status Report for {self.organization.name}\n"
                            f"━━━━━━━━━━━━━━━━\n\n"
                            f"💬 Conversations Today: {total_conversations}\n"
                            f"   Active: {active_conversations}\n"
                            f"   Need Attention: {handoff_conversations}"
                            f"{booking_stats}{override_text}\n\n"
                            f"Send 'help' for available commands.",
            'actions_taken': ['status_report_sent']
        }
    
    def _get_help_message(self, manager: ManagerNumber) -> Dict[str, Any]:
        """
        Return help message with available commands.
        """
        help_text = f"""🤖 Manager Panel for {self.organization.name}
━━━━━━━━━━━━━━━━━━━━━━━

📋 BOOKING MANAGEMENT:
Complete:
• "Complete all bookings for today"
• "Complete RES123"

Status Changes:
• "No show RES123"
• "Cancel booking RES123"
• "Confirm booking RES123"

Create/Edit:
• "Create booking for John, 4 people, today 7pm"
• "Update RES123 to 6 people"
• "Update RES123 time to 8pm"
• "Delete booking RES123"

View:
• "List bookings today"
• "List bookings tomorrow"
• "List pending bookings"
• "List confirmed bookings"

� ANALYTICS:
• "analytics" or "stats" - Get analytics
• "analytics 30" - Last 30 days
• "analytics today" - Today only
{f'  ⚡ Power Plan active - Full analytics!' if self.organization.plan == 'power' else '  📦 Basic Plan - Upgrade for advanced metrics'}

�📢 STATUS UPDATES:
• "We're closing early at 5pm"
• "Closed for private event"
• "We're fully booked tonight"
• "Back open now"

📊 QUICK INFO:
• "status" - Current business status
• "bookings today" - Today's stats

🔧 SETTINGS:
• "cancel override" - Remove last update
• "cancel all overrides" - Resume normal

💡 You have FULL control! Just describe what you want to do in natural language."""
        
        # Add real estate commands if business type is real_estate
        if self.organization.business_type == 'real_estate':
            help_text = f"""🤖 Manager Panel for {self.organization.name}
━━━━━━━━━━━━━━━━━━━━━━━

👥 LEAD MANAGEMENT:
View:
• "List leads"
• "List new leads"
• "List hot leads"
• "List qualified leads"
• "List leads today"

Update Status:
• "Qualify John Smith"
• "Contacted 555-1234"
• "Convert John Smith"
• "Mark lost John Smith"

📅 APPOINTMENT MANAGEMENT:
View:
• "List appointments"
• "List appointments today"
• "List appointments tomorrow"

Status Changes:
• "Complete APT123"
• "Confirm APT123"
• "Cancel APT123"
• "No show APT123"

Create:
• "Schedule viewing for John Smith tomorrow 2pm"
• "Create consultation for 555-1234 Monday 10am"

🏠 PROPERTY MANAGEMENT:
View:
• "List properties"
• "List active properties"
• "List sold properties"

Update Status:
• "Mark sold PROP123"
• "Mark rented PROP456"
• "Activate PROP789"

📊 ANALYTICS:
• "analytics" or "stats" - Get analytics
• "analytics 30" - Last 30 days
• "analytics today" - Today only
{f'  ⚡ Power Plan active - Full analytics!' if self.organization.plan == 'power' else '  📦 Basic Plan - Upgrade for advanced metrics'}

🔧 SETTINGS:
• "cancel override" - Remove last update
• "cancel all overrides" - Resume normal

💡 You have FULL control! Just describe what you want to do in natural language."""
        
        return {
            'response_text': help_text,
            'actions_taken': ['help_sent']
        }
    
    def _process_with_ai(self, manager: ManagerNumber, message: str) -> Dict[str, Any]:
        """
        Use AI to understand and process complex manager messages.
        """
        if not self.client:
            return {
                'response_text': "ℹ️ I couldn't understand that command. Send 'help' to see available options.",
                'actions_taken': ['unknown_command']
            }
        
        try:
            prompt = f"""You are an AI assistant helping a restaurant/business manager send updates via WhatsApp.
The manager sent: "{message}"

Analyze this message and determine:
1. What is the manager trying to do?
2. What should the response be?
3. Should this create a temporary override for customer responses?

If the message is a business status update (closing, hours change, availability, etc.), 
extract the key information.

Respond in JSON format:
{{
    "intent": "hours_update|availability_update|query|status_request|unknown",
    "should_create_override": true/false,
    "processed_content": "Customer-facing message if creating override",
    "keywords": ["list", "of", "trigger", "keywords"],
    "expiry_hours": 24,
    "response_to_manager": "What to reply to the manager"
}}"""
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            
            import json
            result = json.loads(response.choices[0].message.content)
            
            if result.get('should_create_override'):
                # Create override from AI analysis
                expiry_hours = result.get('expiry_hours', 24)
                override = TemporaryOverride.objects.create(
                    organization=self.organization,
                    override_type=TemporaryOverride.OverrideType.GENERAL,
                    priority=TemporaryOverride.Priority.HIGH,
                    original_message=message,
                    processed_content=result.get('processed_content', message),
                    trigger_keywords=result.get('keywords', []),
                    created_by_manager=manager,
                    starts_at=timezone.now(),
                    expires_at=timezone.now() + timedelta(hours=expiry_hours),
                    auto_expire_on_next_open=True
                )
                
                return {
                    'response_text': result.get('response_to_manager', '✅ Update saved!'),
                    'actions_taken': ['ai_override_created'],
                    'override_id': str(override.id)
                }
            
            return {
                'response_text': result.get('response_to_manager', "ℹ️ Message received. Send 'help' for commands."),
                'actions_taken': ['ai_processed']
            }
            
        except Exception as e:
            logger.warning(f"AI processing failed: {e}")
            return {
                'response_text': "ℹ️ I understood your message but couldn't process it automatically. "
                               "Try being more specific or send 'help' for commands.",
                'actions_taken': ['ai_fallback']
            }
    
    @classmethod
    def get_nearest_manager(
        cls,
        organization: Organization,
        location = None
    ) -> Optional[ManagerNumber]:
        """
        Get the nearest/most appropriate manager based on location.
        Prioritizes:
        1. Managers linked to the specific location
        2. Active managers who can respond
        3. Managers with recent activity
        """
        # Try location-specific manager first if location is provided
        if location:
            # Check if there's a manager associated with this location via user
            from apps.accounts.models import OrganizationMembership
            location_managers = ManagerNumber.objects.filter(
                organization=organization,
                is_active=True,
                can_respond_queries=True,
                user__memberships__organization=organization,
                user__memberships__locations=location
            ).order_by('-last_message_at')
            
            if location_managers.exists():
                logger.info(f"📍 Found location-specific manager for {location.name}")
                return location_managers.first()
        
        # Fallback to any active manager, prioritize by recent activity
        managers = ManagerNumber.objects.filter(
            organization=organization,
            is_active=True,
            can_respond_queries=True
        ).order_by('-last_message_at', '-created_at')
        
        if managers.exists():
            manager = managers.first()
            logger.info(f"👤 Selected manager: {manager.name}")
            return manager
        
        logger.warning(f"⚠️ No active manager found for {organization.name}")
        return None
    
    @classmethod
    def get_enhanced_handoff_message(
        cls,
        organization: Organization,
        manager: Optional[ManagerNumber],
        detected_lang: str = 'en'
    ) -> str:
        """
        Generate an enhanced, professional handoff message.
        If manager doesn't respond, provides manager's contact info as fallback.
        
        ENHANCED: More respectful, less frustrating for customers.
        """
        business_name = organization.name
        
        if not manager:
            # No manager available - provide general message
            messages = {
                'en': f"I appreciate your patience. To better assist you with this specific inquiry, I recommend reaching out to our team directly. You can find our contact information in your conversation history. How else may I help you today?",
                'zh-CN': f"感谢您的耐心。为了更好地帮助您解决这个具体问题，我建议您直接联系我们的团队。您可以在对话历史记录中找到我们的联系信息。我今天还能为您做些什么？",
                'zh-TW': f"感謝您的耐心。為了更好地幫助您解決這個具體問題，我建議您直接聯繫我們的團隊。您可以在對話歷史記錄中找到我們的聯繫信息。我今天還能為您做些什麼？"
            }
            return messages.get(detected_lang, messages['en'])
        
        # Manager available - provide professional handoff with contact info
        manager_name = manager.name
        manager_phone = manager.phone_number
        
        # Format phone number nicely (add + if not present)
        if manager_phone and not manager_phone.startswith('+'):
            manager_phone = f"+{manager_phone}"
        
        messages = {
            'en': {
                'connecting': f"Thank you for your question! I'm connecting you with {manager_name}, one of our team members who can provide you with detailed assistance.",
                'fallback': f"If you don't receive a response shortly, please feel free to contact {manager_name} directly at {manager_phone}. We're here to help and appreciate your patience!"
            },
            'zh-CN': {
                'connecting': f"感谢您的提问！我正在为您联系我们的团队成员{manager_name}，他/她可以为您提供详细的帮助。",
                'fallback': f"如果您很快没有收到回复，请随时直接联系{manager_name}，电话：{manager_phone}。我们随时为您服务，感谢您的耐心！"
            },
            'zh-TW': {
                'connecting': f"感謝您的提問！我正在為您聯繫我們的團隊成員{manager_name}，他/她可以為您提供詳細的幫助。",
                'fallback': f"如果您很快沒有收到回覆，請隨時直接聯繫{manager_name}，電話：{manager_phone}。我們隨時為您服務，感謝您的耐心！"
            }
        }
        
        lang_messages = messages.get(detected_lang, messages['en'])
        
        # Combine connecting and fallback messages
        full_message = f"{lang_messages['connecting']}\n\n{lang_messages['fallback']}"
        
        return full_message
    
    @classmethod
    def escalate_to_manager(
        cls,
        organization: Organization,
        conversation: 'Conversation',
        customer_query: str,
        wait_minutes: int = 5
    ) -> Optional[ManagerQuery]:
        """
        Escalate a customer query to the manager via WhatsApp.
        
        ENHANCED:
        - Uses location-based manager selection
        - Provides professional handoff messages with manager contact
        - Auto-fallback if manager doesn't respond
        
        Returns the ManagerQuery object if successful.
        """
        # Get nearest/best manager using location-aware selection
        location = getattr(conversation, 'location', None)
        manager = cls.get_nearest_manager(organization, location)
        
        if not manager:
            logger.warning(f"No active manager found for escalation in {organization.name}")
            return None
        
        # Create query record
        query = ManagerQuery.objects.create(
            organization=organization,
            conversation=conversation,
            manager=manager,
            customer_query=customer_query,
            query_summary=f"Customer question: {customer_query[:200]}",
            expires_at=timezone.now() + timedelta(minutes=wait_minutes),
            status=ManagerQuery.Status.PENDING
        )
        
        # Send WhatsApp message to manager
        try:
            from .whatsapp_service import WhatsAppService
            
            whatsapp_config = WhatsAppConfig.objects.get(
                organization=organization,
                is_active=True
            )
            service = WhatsAppService(whatsapp_config)
            
            manager_message = (
                f"🆘 Customer Question\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"A customer is asking:\n\"{customer_query[:300]}\"\n\n"
                f"💬 Reply to this message to respond to them.\n"
                f"⏰ Waiting for your response ({wait_minutes} mins)"
            )
            
            message_id = service.send_message(manager.phone_number, manager_message)
            if message_id:
                query.whatsapp_message_id = message_id
                query.save()
                logger.info(f"📤 Escalated query to manager {manager.name}: {customer_query[:50]}")
            
        except Exception as e:
            logger.error(f"Failed to send escalation to manager: {e}")
            query.status = ManagerQuery.Status.CANCELLED
            query.save()
            return None
        
        return query
    
    @classmethod
    def get_pending_query_response(cls, conversation: 'Conversation') -> Optional[str]:
        """
        Check if there's a pending manager query for this conversation
        and return appropriate response for customer.
        
        ENHANCED: Uses professional messages with manager contact info.
        """
        pending = ManagerQuery.objects.filter(
            conversation=conversation,
            status=ManagerQuery.Status.PENDING
        ).first()
        
        if pending:
            if pending.is_expired:
                pending.mark_expired()
                # Return enhanced fallback message with manager contact
                detected_lang = getattr(conversation, 'detected_language', 'en')
                return cls.get_enhanced_handoff_message(
                    pending.organization,
                    pending.manager,
                    detected_lang
                )
            else:
                # Still waiting
                return None
        
        return None
