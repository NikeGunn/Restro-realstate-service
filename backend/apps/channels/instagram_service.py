"""
Instagram Messaging API Service.
Handles incoming webhooks and outgoing messages via Instagram Graph API.
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
from .models import InstagramConfig, WebhookLog

logger = logging.getLogger(__name__)


class InstagramService:
    """
    Service for Instagram Messaging API integration.
    """
    
    GRAPH_API_URL = "https://graph.facebook.com/v18.0"
    
    def __init__(self, config: InstagramConfig):
        self.config = config
        self.organization = config.organization
    
    @classmethod
    def get_for_organization(cls, organization: Organization) -> Optional['InstagramService']:
        """Get Instagram service for an organization."""
        try:
            config = InstagramConfig.objects.get(
                organization=organization,
                is_active=True
            )
            return cls(config)
        except InstagramConfig.DoesNotExist:
            return None
    
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify the webhook signature from Meta."""
        app_secret = getattr(settings, 'META_APP_SECRET', '')
        if not app_secret:
            logger.warning("META_APP_SECRET not configured")
            return True  # Skip verification in dev
        
        expected_signature = hmac.new(
            app_secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(f"sha256={expected_signature}", signature)
    
    def process_webhook(self, data: Dict[str, Any]) -> bool:
        """
        Process incoming Instagram webhook event.
        """
        try:
            # Log the webhook
            WebhookLog.objects.create(
                source=WebhookLog.Source.INSTAGRAM,
                organization=self.organization,
                body=data,
                is_processed=False
            )
            
            # Parse webhook structure (Instagram uses similar structure to Messenger)
            entry = data.get('entry', [{}])[0]
            messaging = entry.get('messaging', [])
            
            for event in messaging:
                if 'message' in event:
                    self._handle_incoming_message(event)
                elif 'read' in event:
                    self._handle_read_receipt(event)
                elif 'reaction' in event:
                    self._handle_reaction(event)
            
            return True
            
        except Exception as e:
            logger.exception(f"Error processing Instagram webhook: {e}")
            return False
    
    def _handle_incoming_message(self, event: Dict):
        """Handle incoming message from Instagram."""
        sender_id = event.get('sender', {}).get('id', '')
        recipient_id = event.get('recipient', {}).get('id', '')
        timestamp = event.get('timestamp', '')
        message = event.get('message', {})
        
        message_id = message.get('mid', '')
        content = message.get('text', '')
        
        # Handle attachments
        attachments = message.get('attachments', [])
        if attachments and not content:
            att_type = attachments[0].get('type', 'unknown')
            content = f"[{att_type.upper()}] Media message received"
        
        # Quick replies
        if message.get('quick_reply'):
            content = message['quick_reply'].get('payload', content)
        
        # Get sender info
        sender_name = self._get_user_profile(sender_id)
        
        # Find or create conversation
        conversation = self._get_or_create_conversation(
            sender_id,
            sender_name
        )
        
        # Create message
        msg = Message.objects.create(
            conversation=conversation,
            sender=MessageSender.CUSTOMER,
            content=content,
            ai_metadata={
                'ig_message_id': message_id,
                'sender_id': sender_id,
                'timestamp': timestamp
            }
        )
        
        # Process with AI if not in human handoff
        if conversation.state not in [ConversationState.HUMAN_HANDOFF]:
            conversation.state = ConversationState.AI_HANDLING
            conversation.save()
            self._process_with_ai(conversation, msg)
        
        logger.info(f"Instagram message received from {sender_id}: {content[:50]}...")
    
    def _get_user_profile(self, user_id: str) -> str:
        """Fetch user profile from Instagram."""
        if not self.config.access_token:
            return "Instagram User"
        
        try:
            url = f"{self.GRAPH_API_URL}/{user_id}"
            params = {
                "fields": "name,username",
                "access_token": self.config.access_token
            }
            
            response = requests.get(url, params=params, timeout=10)
            if response.ok:
                data = response.json()
                return data.get('username') or data.get('name', 'Instagram User')
        except Exception as e:
            logger.warning(f"Failed to fetch Instagram profile: {e}")
        
        return "Instagram User"
    
    def _get_or_create_conversation(self, ig_user_id: str, name: str) -> Conversation:
        """Get or create conversation for an Instagram user."""
        conversation = Conversation.objects.filter(
            organization=self.organization,
            channel=Channel.INSTAGRAM,
            external_id=ig_user_id,
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
                channel=Channel.INSTAGRAM,
                customer_name=name,
                external_id=ig_user_id,
                state=ConversationState.NEW
            )
        
        return conversation
    
    def _process_with_ai(self, conversation: Conversation, message: Message):
        """Process message with AI and send response. Supports multilingual responses."""
        try:
            # AIService takes conversation as parameter (not organization)
            ai_service = AIService(conversation)
            
            # Check if AI service is properly initialized
            if not ai_service.client:
                logger.error(f"❌ CRITICAL: OpenAI client not initialized - check OPENAI_API_KEY in environment")
                return
            
            response = ai_service.process_message(message.content)
            
            if response:
                detected_lang = response.get('language', 'en')
                logger.info(f"✅ Instagram AI response - Intent: {response.get('intent')}, Confidence: {response.get('confidence')}, Language: {detected_lang}")
                
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
                
                # Check if handoff is needed and create alert
                if response.get('needs_handoff', False):
                    from apps.handoff.services import create_alert_from_ai_response
                    alert = create_alert_from_ai_response(
                        conversation=conversation,
                        ai_response=response,
                        user_message=message.content
                    )
                    if alert:
                        logger.info(f"🚨 Instagram handoff alert created: {alert.id}")
                        conversation.state = ConversationState.HUMAN_HANDOFF
                        conversation.save()
                
                # Send via Instagram
                logger.info(f"📤 Sending Instagram message in {detected_lang}")
                self.send_message(
                    recipient_id=conversation.external_id,
                    text=response['content']
                )
                
                conversation.state = ConversationState.AWAITING_USER
                conversation.save()
                
        except Exception as e:
            logger.exception(f"Error processing with AI: {e}")
    
    def _process_extracted_data(self, conversation: Conversation, ai_response: dict):
        """
        Process extracted data from AI response.
        Creates bookings, leads, appointments etc. based on the extracted data.
        """
        extracted_data = ai_response.get('extracted_data', {})
        
        if not extracted_data:
            return
        
        logger.info(f"📊 Instagram: Processing extracted data: {extracted_data}")
        
        # Handle booking cancellation for restaurant businesses
        if extracted_data.get('cancel_booking_code') and self.organization.business_type == 'restaurant':
            self._process_booking_cancellation(conversation, extracted_data)
        
        # Handle booking intent for restaurant businesses
        if extracted_data.get('booking_intent') and self.organization.business_type == 'restaurant':
            self._process_booking_data(conversation, ai_response)
        
        # Handle lead/appointment intent for real estate businesses
        if self.organization.business_type == 'real_estate':
            if extracted_data.get('lead_intent') or extracted_data.get('appointment_intent'):
                self._process_realestate_data(conversation, ai_response)
    
    def _process_booking_cancellation(self, conversation: Conversation, extracted_data: dict):
        """
        Process booking cancellation request.
        """
        try:
            from apps.restaurant.models import Booking
            
            cancel_code = extracted_data.get('cancel_booking_code', '').strip().upper()
            if not cancel_code:
                logger.warning("Cancel request but no booking code provided")
                return
            
            # Find the booking
            booking = Booking.objects.filter(
                organization=self.organization,
                confirmation_code=cancel_code,
                status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED]
            ).first()
            
            if booking:
                booking.cancel(reason="Cancelled by customer via Instagram")
                logger.info(f"❌ Booking cancelled via Instagram: {cancel_code}")
            else:
                logger.warning(f"Booking not found for cancellation: {cancel_code}")
        except Exception as e:
            logger.exception(f"❌ Error cancelling booking: {e}")
    
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
                source='instagram'
            )
            
            if booking:
                logger.info(f"📅 Booking created from Instagram: {booking.confirmation_code}")
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
                source='instagram'
            )
            
            if result.get('lead'):
                lead = result['lead']
                logger.info(f"🏠 Lead created from Instagram: {lead.id}")
                logger.info(f"   Customer: {lead.name}")
                logger.info(f"   Intent: {lead.intent}")
                logger.info(f"   Score: {lead.lead_score}")
            
            if result.get('appointment'):
                apt = result['appointment']
                logger.info(f"📅 Appointment created from Instagram: {apt.confirmation_code}")
                logger.info(f"   Lead: {apt.lead.name}")
                logger.info(f"   Date: {apt.appointment_date} at {apt.appointment_time}")
                logger.info(f"   Type: {apt.appointment_type}")
        except Exception as e:
            logger.exception(f"❌ Error processing real estate data: {e}")
    
    def _handle_read_receipt(self, event: Dict):
        """Handle read receipt event."""
        logger.debug(f"Instagram read receipt: {event}")
    
    def _handle_reaction(self, event: Dict):
        """Handle reaction event."""
        logger.debug(f"Instagram reaction: {event}")
    
    def send_message(self, recipient_id: str, text: str) -> Optional[str]:
        """
        Send a text message via Instagram.
        Returns message ID on success.
        """
        if not self.config.is_active or not self.config.access_token:
            logger.warning("Instagram not configured or inactive")
            return None
        
        url = f"{self.GRAPH_API_URL}/{self.config.instagram_business_id}/messages"
        
        headers = {
            "Authorization": f"Bearer {self.config.access_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "recipient": {"id": recipient_id},
            "message": {"text": text}
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            message_id = result.get('message_id')
            
            logger.info(f"Instagram message sent to {recipient_id}: {message_id}")
            return message_id
            
        except requests.exceptions.RequestException as e:
            logger.exception(f"Failed to send Instagram message: {e}")
            return None
    
    def send_quick_replies(
        self,
        recipient_id: str,
        text: str,
        quick_replies: list[Dict[str, str]]
    ) -> Optional[str]:
        """
        Send a message with quick reply buttons.
        quick_replies: [{"title": "Option 1", "payload": "OPTION_1"}, ...]
        """
        if not self.config.is_active:
            return None
        
        url = f"{self.GRAPH_API_URL}/{self.config.instagram_business_id}/messages"
        
        headers = {
            "Authorization": f"Bearer {self.config.access_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "recipient": {"id": recipient_id},
            "message": {
                "text": text,
                "quick_replies": [
                    {
                        "content_type": "text",
                        "title": qr.get("title", "")[:20],  # Max 20 chars
                        "payload": qr.get("payload", qr.get("title", ""))
                    }
                    for qr in quick_replies[:13]  # Max 13 quick replies
                ]
            }
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json().get('message_id')
        except Exception as e:
            logger.exception(f"Failed to send Instagram quick replies: {e}")
            return None
