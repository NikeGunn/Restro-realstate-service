"""
Manager Service - Handles manager WhatsApp messages and commands.
Provides flexible management capabilities via WhatsApp for managers on-the-go.
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple

from django.conf import settings
from django.utils import timezone
from openai import OpenAI

from apps.accounts.models import Organization
from apps.messaging.models import Conversation, Message, MessageSender
from .models import ManagerNumber, TemporaryOverride, ManagerQuery, WhatsAppConfig

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
        
        # Check if this is a response to a pending query
        pending_query = self._check_for_query_response(manager, message)
        if pending_query:
            return self._handle_query_response(pending_query, message)
        
        # Check for command patterns
        result = self._detect_and_process_command(manager, message)
        
        return result
    
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
        if conversation.channel == 'whatsapp' and conversation.customer_phone:
            try:
                whatsapp_config = WhatsAppConfig.objects.get(
                    organization=self.organization,
                    is_active=True
                )
                service = WhatsAppService(whatsapp_config)
                service.send_message(conversation.customer_phone, response)
            except Exception as e:
                logger.error(f"Failed to send WhatsApp response: {e}")
        
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
        help_text = f"""🤖 Manager Commands for {self.organization.name}
━━━━━━━━━━━━━━━━━━━━━━━

📢 STATUS UPDATES:
• "We're closing early at 5pm"
• "Closed for private event"
• "We're fully booked tonight"
• "Back open now"

📊 QUICK INFO:
• "status" - Get today's stats
• "bookings today" - See today's bookings

🔧 MANAGEMENT:
• "cancel override" - Cancel last update
• "cancel all overrides" - Resume normal

💡 TIPS:
• Messages are processed naturally
• Just describe what you want
• Updates auto-expire at end of day

Need help? Just describe what you want to do!"""
        
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
    def escalate_to_manager(
        cls,
        organization: Organization,
        conversation: 'Conversation',
        customer_query: str,
        wait_minutes: int = 5
    ) -> Optional[ManagerQuery]:
        """
        Escalate a customer query to the manager via WhatsApp.
        Returns the ManagerQuery object if successful.
        """
        # Get an active manager
        manager = ManagerNumber.objects.filter(
            organization=organization,
            is_active=True,
            can_respond_queries=True
        ).first()
        
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
        """
        pending = ManagerQuery.objects.filter(
            conversation=conversation,
            status=ManagerQuery.Status.PENDING
        ).first()
        
        if pending:
            if pending.is_expired:
                pending.mark_expired()
                return (
                    "I apologize, but I wasn't able to get a quick answer from my team. "
                    f"You can reach our manager directly at {pending.manager.phone_number} "
                    "or I can help you with something else."
                )
            else:
                # Still waiting
                return None
        
        return None
