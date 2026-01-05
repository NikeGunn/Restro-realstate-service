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
            metadata={
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
        """Process message with AI and send response."""
        try:
            ai_service = AIService(self.organization)
            response = ai_service.process_message(conversation, message.content)
            
            if response:
                # Create AI message
                ai_message = Message.objects.create(
                    conversation=conversation,
                    sender=MessageSender.AI,
                    content=response['reply'],
                    metadata={
                        'confidence': response.get('confidence', 0),
                        'intent': response.get('intent', 'unknown')
                    }
                )
                
                # Send via Instagram
                self.send_message(
                    recipient_id=conversation.external_id,
                    text=response['reply']
                )
                
                conversation.state = ConversationState.AWAITING_USER
                conversation.save()
                
        except Exception as e:
            logger.exception(f"Error processing with AI: {e}")
    
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
