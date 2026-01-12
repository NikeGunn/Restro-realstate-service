"""
WhatsApp Business API Service.
Handles incoming webhooks and outgoing messages.
"""
import hashlib
import hmac
import logging
import requests
from typing import Optional, Dict, Any
from django.conf import settings

from apps.messaging.models import Conversation, Message, Channel, ConversationState, MessageSender
from apps.accounts.models import Organization
from apps.ai_engine.services import AIService
from .models import WhatsAppConfig, WebhookLog

logger = logging.getLogger(__name__)


class WhatsAppService:
    """
    Service for WhatsApp Business API integration.
    """
    
    GRAPH_API_URL = "https://graph.facebook.com/v18.0"
    
    def __init__(self, config: WhatsAppConfig):
        self.config = config
        self.organization = config.organization
    
    @classmethod
    def get_for_organization(cls, organization: Organization) -> Optional['WhatsAppService']:
        """Get WhatsApp service for an organization."""
        try:
            config = WhatsAppConfig.objects.get(
                organization=organization,
                is_active=True
            )
            return cls(config)
        except WhatsAppConfig.DoesNotExist:
            return None
    
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify the webhook signature from Meta.
        Payload must be the raw request body bytes, not parsed JSON.
        """
        app_secret = getattr(settings, 'META_APP_SECRET', '')
        if not app_secret:
            logger.warning("META_APP_SECRET not configured - skipping signature verification")
            return True  # Skip verification in dev
        
        # Calculate expected signature using raw bytes
        expected_signature = hmac.new(
            app_secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        expected_full = f"sha256={expected_signature}"
        is_valid = hmac.compare_digest(expected_full, signature)
        
        if not is_valid:
            logger.error(f"❌ Webhook signature verification FAILED")
            logger.error(f"   Expected: {expected_full[:60]}...")
            logger.error(f"   Received: {signature[:60]}...")
            logger.error(f"   App Secret: {app_secret[:8]}...{app_secret[-4:]}")
            logger.error(f"   Payload length: {len(payload)} bytes")
            logger.error(f"   This means the META_APP_SECRET doesn't match the app sending webhooks")
        else:
            logger.info(f"✅ Webhook signature verified successfully")
        
        return is_valid
    
    def process_webhook(self, data: Dict[str, Any]) -> bool:
        """
        Process incoming WhatsApp webhook event.
        """
        try:
            # Log the webhook
            WebhookLog.objects.create(
                source=WebhookLog.Source.WHATSAPP,
                organization=self.organization,
                body=data,
                is_processed=False
            )
            
            # Parse webhook structure
            entry = data.get('entry', [{}])[0]
            changes = entry.get('changes', [{}])[0]
            value = changes.get('value', {})
            
            # Check for messages
            messages = value.get('messages', [])
            for msg in messages:
                self._handle_incoming_message(msg, value.get('contacts', []))
            
            # Check for status updates
            statuses = value.get('statuses', [])
            for status in statuses:
                self._handle_status_update(status)
            
            return True
            
        except Exception as e:
            logger.exception(f"Error processing WhatsApp webhook: {e}")
            return False
    
    def _handle_incoming_message(self, msg: Dict, contacts: list):
        """Handle incoming message from WhatsApp."""
        sender_phone = msg.get('from', '')
        message_type = msg.get('type', 'text')
        timestamp = msg.get('timestamp', '')
        wa_message_id = msg.get('id', '')
        
        # Get sender name from contacts
        sender_name = "WhatsApp User"
        for contact in contacts:
            if contact.get('wa_id') == sender_phone:
                profile = contact.get('profile', {})
                sender_name = profile.get('name', sender_name)
                break
        
        # Extract message content based on type
        content = ""
        if message_type == 'text':
            content = msg.get('text', {}).get('body', '')
        elif message_type == 'interactive':
            interactive = msg.get('interactive', {})
            if interactive.get('type') == 'button_reply':
                content = interactive.get('button_reply', {}).get('title', '')
            elif interactive.get('type') == 'list_reply':
                content = interactive.get('list_reply', {}).get('title', '')
        elif message_type in ['image', 'audio', 'video', 'document']:
            content = f"[{message_type.upper()}] Media message received"
        else:
            content = f"[{message_type.upper()}] Unsupported message type"
        
        # Find or create conversation
        conversation = self._get_or_create_conversation(
            sender_phone, 
            sender_name
        )
        
        # Create message
        message = Message.objects.create(
            conversation=conversation,
            sender=MessageSender.CUSTOMER,
            content=content,
            channel_message_id=wa_message_id,
            ai_metadata={
                'message_type': message_type,
                'sender_phone': sender_phone,
                'timestamp': timestamp
            }
        )
        
        # Update conversation state
        if conversation.state not in [ConversationState.HUMAN_HANDOFF]:
            conversation.state = ConversationState.AI_HANDLING
            conversation.save()
            
            # Process with AI (async in production)
            self._process_with_ai(conversation, message)
        
        logger.info(f"WhatsApp message received from {sender_phone}: {content[:50]}...")
    
    def _get_or_create_conversation(self, phone: str, name: str) -> Conversation:
        """Get or create conversation for a WhatsApp user."""
        # Try to find existing active conversation
        conversation = Conversation.objects.filter(
            organization=self.organization,
            channel=Channel.WHATSAPP,
            customer_phone=phone,
            state__in=[
                ConversationState.NEW,
                ConversationState.AI_HANDLING,
                ConversationState.AWAITING_USER,
                ConversationState.HUMAN_HANDOFF
            ]
        ).first()
        
        if not conversation:
            conversation = Conversation.objects.create(
                organization=self.organization,
                channel=Channel.WHATSAPP,
                customer_name=name,
                customer_phone=phone,
                state=ConversationState.NEW
            )
        
        return conversation
    
    def _process_with_ai(self, conversation: Conversation, message: Message):
        """Process message with AI and send response. Supports multilingual responses."""
        try:
            logger.info(f"🤖 Processing message with AI for conversation {conversation.id}")
            ai_service = AIService(conversation)
            
            # Check if AI service is properly initialized
            if not ai_service.client:
                logger.error(f"❌ CRITICAL: OpenAI client not initialized - check OPENAI_API_KEY in environment")
                logger.error(f"AI responses will fail until OPENAI_API_KEY is set")
                return
            
            response = ai_service.process_message(message.content)
            
            if response:
                detected_lang = response.get('language', 'en')
                logger.info(f"✅ AI response generated - Intent: {response.get('intent')}, Confidence: {response.get('confidence')}, Language: {detected_lang}")
                
                # Process any extracted booking data
                self._process_extracted_data(conversation, response)
                
                # Create AI message
                ai_message = Message.objects.create(
                    conversation=conversation,
                    sender=MessageSender.AI,
                    content=response['content'],
                    confidence_score=response.get('confidence', 0),
                    intent=response.get('intent', 'unknown'),
                    ai_metadata={
                        'confidence': response.get('confidence', 0),
                        'intent': response.get('intent', 'unknown'),
                        'needs_handoff': response.get('needs_handoff', False),
                        'language': detected_lang,
                    }
                )
                
                # Send via WhatsApp
                logger.info(f"📤 Sending WhatsApp message to {conversation.customer_phone} in {detected_lang}")
                sent_message_id = self.send_message(
                    to=conversation.customer_phone,
                    text=response['content']
                )
                
                if sent_message_id:
                    ai_message.channel_message_id = sent_message_id
                    ai_message.save()
                    logger.info(f"✅ WhatsApp message sent successfully - ID: {sent_message_id}")
                else:
                    logger.error(f"❌ CRITICAL: Failed to send WhatsApp message - check access_token and phone_number_id")
                    logger.error(f"Org: {self.organization.name}, Phone ID: {self.config.phone_number_id}")
                
                # Update conversation state
                conversation.state = ConversationState.AWAITING_USER
                conversation.save()
            else:
                logger.error(f"❌ No response from AI service")
                
        except Exception as e:
            logger.exception(f"❌ CRITICAL: Error processing with AI: {e}")
            logger.error(f"This will prevent replies from being sent to customer")
    
    def _process_extracted_data(self, conversation: Conversation, ai_response: dict):
        """
        Process extracted data from AI response.
        Creates bookings, leads, appointments etc. based on the extracted data.
        """
        extracted_data = ai_response.get('extracted_data', {})
        
        if not extracted_data:
            return
        
        logger.info(f"📊 Processing extracted data: {extracted_data}")
        
        # Handle booking intent for restaurant businesses
        if extracted_data.get('booking_intent') and self.organization.business_type == 'restaurant':
            self._process_booking_data(conversation, ai_response)
        
        # Handle lead/appointment intent for real estate businesses
        if self.organization.business_type == 'real_estate':
            if extracted_data.get('lead_intent') or extracted_data.get('appointment_intent'):
                self._process_realestate_data(conversation, ai_response)
    
    def _process_booking_data(self, conversation: Conversation, ai_response: dict):
        """
        Process booking data and create a reservation.
        """
        try:
            from apps.restaurant.booking_service import process_booking_from_ai_response
            
            booking = process_booking_from_ai_response(
                organization=self.organization,
                conversation=conversation,
                ai_response=ai_response,
                source='whatsapp'
            )
            
            if booking:
                logger.info(f"📅 Booking created from WhatsApp: {booking.confirmation_code}")
                logger.info(f"   Customer: {booking.customer_name}")
                logger.info(f"   Date: {booking.booking_date} at {booking.booking_time}")
                logger.info(f"   Party size: {booking.party_size}")
                logger.info(f"   Status: {booking.status}")
        except Exception as e:
            logger.exception(f"❌ Error processing booking data: {e}")
    
    def _process_realestate_data(self, conversation: Conversation, ai_response: dict):
        """
        Process real estate lead and appointment data.
        """
        try:
            from apps.realestate.lead_service import process_realestate_from_ai_response
            
            result = process_realestate_from_ai_response(
                organization=self.organization,
                conversation=conversation,
                ai_response=ai_response,
                source='whatsapp'
            )
            
            if result.get('lead'):
                lead = result['lead']
                logger.info(f"🏠 Lead created from WhatsApp: {lead.id}")
                logger.info(f"   Customer: {lead.name}")
                logger.info(f"   Intent: {lead.intent}")
                logger.info(f"   Score: {lead.lead_score}")
            
            if result.get('appointment'):
                apt = result['appointment']
                logger.info(f"📅 Appointment created from WhatsApp: {apt.confirmation_code}")
                logger.info(f"   Lead: {apt.lead.name}")
                logger.info(f"   Date: {apt.appointment_date} at {apt.appointment_time}")
                logger.info(f"   Type: {apt.appointment_type}")
        except Exception as e:
            logger.exception(f"❌ Error processing real estate data: {e}")
    
    def _handle_status_update(self, status: Dict):
        """Handle message status update (sent, delivered, read)."""
        wa_message_id = status.get('id', '')
        status_type = status.get('status', '')
        
        logger.debug(f"WhatsApp status update: {wa_message_id} -> {status_type}")
        
        # Update message status if needed
        try:
            # Use channel_message_id instead of metadata for lookups
            message = Message.objects.get(channel_message_id=wa_message_id)
            if message.ai_metadata is None:
                message.ai_metadata = {}
            message.ai_metadata['delivery_status'] = status_type
            message.save()
        except Message.DoesNotExist:
            pass
    
    def send_message(self, to: str, text: str) -> Optional[str]:
        """
        Send a text message via WhatsApp.
        Returns message ID on success.
        """
        if not self.config.is_active:
            logger.error(f"❌ CRITICAL: WhatsApp config is_active=False for {self.organization.name}")
            logger.error(f"Set is_active=True in WhatsApp configuration to enable messaging")
            return None
            
        if not self.config.access_token:
            logger.error(f"❌ CRITICAL: WhatsApp access_token is empty for {self.organization.name}")
            logger.error(f"Add valid Meta API access token to WhatsApp configuration")
            return None
            
        if not self.config.phone_number_id:
            logger.error(f"❌ CRITICAL: WhatsApp phone_number_id is empty for {self.organization.name}")
            logger.error(f"Add phone_number_id from Meta Business to WhatsApp configuration")
            return None
        
        url = f"{self.GRAPH_API_URL}/{self.config.phone_number_id}/messages"
        
        headers = {
            "Authorization": f"Bearer {self.config.access_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": text
            }
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            message_id = result.get('messages', [{}])[0].get('id')
            
            logger.info(f"WhatsApp message sent to {to}: {message_id}")
            return message_id
            
        except requests.exceptions.RequestException as e:
            # Log the full error response from Graph API
            error_detail = f"Failed to send WhatsApp message: {e}"
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_json = e.response.json()
                    logger.error(f"Graph API Error Response: {error_json}")
                    error_detail += f" | API Response: {error_json}"
                except:
                    logger.error(f"Graph API Error Response (text): {e.response.text}")
                    error_detail += f" | API Response: {e.response.text}"
            logger.exception(error_detail)
            return None
    
    def send_interactive_buttons(
        self, 
        to: str, 
        body: str, 
        buttons: list[Dict[str, str]]
    ) -> Optional[str]:
        """
        Send an interactive button message.
        buttons: [{"id": "btn1", "title": "Option 1"}, ...]
        """
        if not self.config.is_active:
            return None
        
        url = f"{self.GRAPH_API_URL}/{self.config.phone_number_id}/messages"
        
        headers = {
            "Authorization": f"Bearer {self.config.access_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": btn} 
                        for btn in buttons[:3]  # Max 3 buttons
                    ]
                }
            }
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json().get('messages', [{}])[0].get('id')
        except Exception as e:
            logger.exception(f"Failed to send WhatsApp buttons: {e}")
            return None
