"""
Twilio WhatsApp Service.

Drop-in alternative to the Meta WhatsApp Cloud API integration. Designed for
zero-friction setup via Twilio's WhatsApp Sandbox so customers don't have to
go through Meta's Business verification.

Twilio differences vs. Meta:
- Webhook is application/x-www-form-urlencoded, not JSON
- Signature header is X-Twilio-Signature, HMAC-SHA1 over (url + sorted params)
- Phone numbers are prefixed with `whatsapp:` (e.g. whatsapp:+14155238886)
- Outbound is via REST API: POST /Accounts/{sid}/Messages.json (basic auth)
"""
import base64
import hashlib
import hmac
import logging
from typing import Optional, Dict, Any

import requests
from django.conf import settings

from apps.messaging.models import (
    Conversation, Message, Channel, ConversationState, MessageSender
)
from apps.accounts.models import Organization
from apps.ai_engine.services import AIService
from .models import TwilioConfig, ManagerNumber

logger = logging.getLogger(__name__)


class TwilioService:
    """Service for Twilio WhatsApp integration."""

    API_BASE = "https://api.twilio.com/2010-04-01"

    def __init__(self, config: TwilioConfig):
        self.config = config
        self.organization = config.organization

    @classmethod
    def get_for_organization(cls, organization: Organization) -> Optional['TwilioService']:
        try:
            config = TwilioConfig.objects.get(organization=organization, is_active=True)
            return cls(config)
        except TwilioConfig.DoesNotExist:
            return None

    # ---------- signature verification ----------

    def verify_webhook_signature(self, url: str, params: Dict[str, str], signature: str) -> bool:
        """
        Verify X-Twilio-Signature.

        Algorithm (per Twilio docs):
          1. Take the full request URL (including query string)
          2. If POST form-encoded, sort POST params alphabetically by key
             and append each `key + value` to the URL string
          3. HMAC-SHA1 with auth_token as the key, base64-encode the digest
          4. Compare to header
        """
        auth_token = self.config.auth_token
        if not auth_token:
            logger.warning("Twilio auth_token not configured - skipping signature verification")
            return True

        data = url
        for key in sorted(params.keys()):
            data += key + params[key]

        digest = hmac.new(
            auth_token.encode('utf-8'),
            data.encode('utf-8'),
            hashlib.sha1
        ).digest()
        expected = base64.b64encode(digest).decode('utf-8')

        is_valid = hmac.compare_digest(expected, signature or '')
        if not is_valid:
            logger.error(
                "Twilio webhook signature mismatch: expected=%s received=%s url=%s",
                expected[:20] + '...', (signature or '')[:20] + '...', url
            )
        else:
            logger.info("Twilio webhook signature verified")
        return is_valid

    # ---------- inbound webhook ----------

    @staticmethod
    def _strip_whatsapp_prefix(phone: str) -> str:
        """Convert 'whatsapp:+14155238886' -> '+14155238886', keep as-is otherwise."""
        if phone and phone.startswith('whatsapp:'):
            return phone[len('whatsapp:'):]
        return phone or ''

    def process_webhook(self, params: Dict[str, str]) -> bool:
        """Process Twilio inbound webhook (form-encoded params as a dict)."""
        try:
            # Status callback (delivery receipt) — has MessageStatus, no Body
            if params.get('MessageStatus') and not params.get('Body') and not params.get('NumMedia'):
                self._handle_status_update(params)
                return True

            from_phone = self._strip_whatsapp_prefix(params.get('From', ''))
            body = params.get('Body', '') or ''
            num_media = int(params.get('NumMedia', '0') or '0')
            wa_message_id = params.get('MessageSid', '')
            sender_name = params.get('ProfileName', '') or 'WhatsApp User'

            # Media-only → placeholder content
            if not body and num_media > 0:
                media_type = params.get('MediaContentType0', 'media').split('/')[0].upper()
                body = f"[{media_type}] Media message received"

            if not from_phone:
                logger.warning("Twilio webhook missing From: %s", params)
                return False

            # Manager handling (reuse same ManagerNumber registry as Meta WhatsApp)
            manager = ManagerNumber.get_by_phone(from_phone, self.organization)
            if manager:
                logger.info("📢 Twilio manager message from %s (%s)", manager.name, from_phone)
                self._handle_manager_message(manager, body, wa_message_id)
                return True

            conversation = self._get_or_create_conversation(from_phone, sender_name)

            message = Message.objects.create(
                conversation=conversation,
                sender=MessageSender.CUSTOMER,
                content=body,
                channel_message_id=wa_message_id,
                ai_metadata={
                    'provider': 'twilio',
                    'sender_phone': from_phone,
                    'num_media': num_media,
                }
            )

            if conversation.state not in [ConversationState.HUMAN_HANDOFF]:
                conversation.state = ConversationState.AI_HANDLING
                conversation.save()
                self._process_with_ai(conversation, message)

            logger.info("Twilio message received from %s: %s", from_phone, body[:50])
            return True
        except Exception as e:
            logger.exception("Error processing Twilio webhook: %s", e)
            return False

    def _handle_status_update(self, params: Dict[str, str]):
        wa_message_id = params.get('MessageSid', '')
        status_type = params.get('MessageStatus', '')
        try:
            message = Message.objects.get(channel_message_id=wa_message_id)
            if message.ai_metadata is None:
                message.ai_metadata = {}
            message.ai_metadata['delivery_status'] = status_type
            message.save()
        except Message.DoesNotExist:
            pass

    def _handle_manager_message(self, manager: ManagerNumber, content: str, wa_message_id: str):
        from .manager_service import ManagerService
        try:
            service = ManagerService(self.organization)
            result = service.process_manager_message(manager, content)
            response_text = result.get('response_text', 'Message received')
            self.send_message(manager.phone_number, response_text)
            logger.info("✅ Twilio manager command processed: %s", result.get('actions_taken', []))
        except Exception as e:
            logger.exception("Error processing Twilio manager message: %s", e)
            self.send_message(
                manager.phone_number,
                f"❌ Error processing your command: {str(e)[:100]}"
            )

    def _get_or_create_conversation(self, phone: str, name: str) -> Conversation:
        conversation = Conversation.objects.filter(
            organization=self.organization,
            channel=Channel.WHATSAPP,  # Twilio is still the WhatsApp channel
            customer_phone=phone,
            state__in=[
                ConversationState.NEW,
                ConversationState.AI_HANDLING,
                ConversationState.AWAITING_USER,
                ConversationState.HUMAN_HANDOFF,
            ]
        ).first()

        if not conversation:
            conversation = Conversation.objects.create(
                organization=self.organization,
                channel=Channel.WHATSAPP,
                customer_name=name,
                customer_phone=phone,
                state=ConversationState.NEW,
                customer_metadata={'provider': 'twilio'},
            )
        return conversation

    def _process_with_ai(self, conversation: Conversation, message: Message):
        try:
            ai_service = AIService(conversation)
            if not ai_service.client:
                logger.error("OpenAI client not initialized - check OPENAI_API_KEY")
                return

            response = ai_service.process_message(message.content)
            if not response:
                logger.error("No response from AI service")
                return

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
                    'language': response.get('language', 'en'),
                    'provider': 'twilio',
                }
            )

            if response.get('needs_handoff', False):
                from apps.handoff.services import create_alert_from_ai_response
                alert = create_alert_from_ai_response(
                    conversation=conversation,
                    ai_response=response,
                    user_message=message.content
                )
                if alert:
                    conversation.state = ConversationState.HUMAN_HANDOFF
                    conversation.save()

            sent_id = self.send_message(conversation.customer_phone, response['content'])
            if sent_id:
                ai_message.channel_message_id = sent_id
                ai_message.save()

            conversation.state = ConversationState.AWAITING_USER
            conversation.save()
        except Exception as e:
            logger.exception("Error processing Twilio message with AI: %s", e)

    # ---------- outbound ----------

    def send_message(self, to: str, text: str) -> Optional[str]:
        """Send a WhatsApp text message via Twilio. Returns the MessageSid."""
        if not self.config.is_active:
            logger.error("Twilio config is_active=False for %s", self.organization.name)
            return None
        if not (self.config.account_sid and self.config.auth_token and self.config.from_number):
            logger.error("Twilio config missing credentials for %s", self.organization.name)
            return None

        # Twilio expects whatsapp: prefix on both From and To
        to_e164 = to if to.startswith('+') else f"+{to.lstrip('+')}"
        to_full = to_e164 if to_e164.startswith('whatsapp:') else f"whatsapp:{to_e164}"
        from_full = (
            self.config.from_number
            if self.config.from_number.startswith('whatsapp:')
            else f"whatsapp:{self.config.from_number}"
        )

        url = f"{self.API_BASE}/Accounts/{self.config.account_sid}/Messages.json"
        try:
            response = requests.post(
                url,
                data={'From': from_full, 'To': to_full, 'Body': text},
                auth=(self.config.account_sid, self.config.auth_token),
                timeout=30,
            )
            response.raise_for_status()
            sid = response.json().get('sid')
            logger.info("Twilio message sent to %s: %s", to_full, sid)
            return sid
        except requests.exceptions.RequestException as e:
            detail = ''
            if hasattr(e, 'response') and e.response is not None:
                try:
                    detail = e.response.json()
                except Exception:
                    detail = e.response.text
            logger.exception("Failed to send Twilio message: %s | %s", e, detail)
            return None

    # ---------- credential verification ----------

    def verify_credentials(self) -> bool:
        """Hit the Twilio Account API to confirm SID + token are valid."""
        if not (self.config.account_sid and self.config.auth_token):
            return False
        try:
            url = f"{self.API_BASE}/Accounts/{self.config.account_sid}.json"
            response = requests.get(
                url,
                auth=(self.config.account_sid, self.config.auth_token),
                timeout=10,
            )
            return response.ok
        except Exception as e:
            logger.error("Twilio credential verification error: %s", e)
            return False
