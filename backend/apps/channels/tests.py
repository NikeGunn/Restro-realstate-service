"""
Tests for the Twilio WhatsApp integration.
"""
import base64
import hashlib
import hmac
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client

from apps.accounts.models import Organization
from apps.messaging.models import Conversation, Message, Channel, MessageSender
from apps.channels.models import TwilioConfig, WebhookLog
from apps.channels.twilio_service import TwilioService


def twilio_signature(auth_token: str, url: str, params: dict) -> str:
    """Replicate Twilio's request-signing algorithm for tests."""
    data = url
    for key in sorted(params.keys()):
        data += key + params[key]
    digest = hmac.new(auth_token.encode(), data.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


class TwilioServiceSignatureTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Sig Org")
        self.config = TwilioConfig.objects.create(
            organization=self.org,
            account_sid="ACtestsid",
            auth_token="testtoken",
            from_number="+14155238886",
            is_active=True,
        )
        self.service = TwilioService(self.config)

    def test_valid_signature_passes(self):
        url = "https://example.com/api/webhooks/twilio/"
        params = {"From": "whatsapp:+15551234567", "Body": "hi", "MessageSid": "SMx"}
        sig = twilio_signature("testtoken", url, params)
        self.assertTrue(self.service.verify_webhook_signature(url, params, sig))

    def test_invalid_signature_fails(self):
        url = "https://example.com/api/webhooks/twilio/"
        params = {"From": "whatsapp:+15551234567", "Body": "hi"}
        self.assertFalse(self.service.verify_webhook_signature(url, params, "deadbeef"))

    def test_missing_token_skips_verification(self):
        self.config.auth_token = ""
        self.config.save()
        service = TwilioService(self.config)
        # Skipping verification returns True so dev environments work
        self.assertTrue(service.verify_webhook_signature("u", {}, "anything"))


class TwilioServiceInboundTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Inbound Org")
        self.config = TwilioConfig.objects.create(
            organization=self.org,
            account_sid="ACtestsid",
            auth_token="testtoken",
            from_number="+14155238886",
            is_active=True,
        )

    def test_strip_whatsapp_prefix(self):
        self.assertEqual(
            TwilioService._strip_whatsapp_prefix("whatsapp:+15551234567"),
            "+15551234567"
        )
        self.assertEqual(TwilioService._strip_whatsapp_prefix("+15551234567"), "+15551234567")
        self.assertEqual(TwilioService._strip_whatsapp_prefix(""), "")

    @patch("apps.channels.twilio_service.AIService")
    @patch.object(TwilioService, "send_message", return_value="SMresp123")
    def test_inbound_creates_conversation_and_routes_to_ai(self, mock_send, mock_ai_cls):
        mock_ai = MagicMock()
        mock_ai.client = object()  # truthy
        mock_ai.process_message.return_value = {
            "content": "Hello, how can I help?",
            "confidence": 0.9,
            "intent": "greeting",
            "language": "en",
            "needs_handoff": False,
        }
        mock_ai_cls.return_value = mock_ai

        params = {
            "From": "whatsapp:+15551234567",
            "To": "whatsapp:+14155238886",
            "Body": "Hello",
            "MessageSid": "SMabc",
            "ProfileName": "Test User",
            "NumMedia": "0",
        }
        ok = TwilioService(self.config).process_webhook(params)
        self.assertTrue(ok)

        conversation = Conversation.objects.filter(
            organization=self.org,
            channel=Channel.WHATSAPP,
            customer_phone="+15551234567",
        ).first()
        self.assertIsNotNone(conversation)

        customer_msg = Message.objects.filter(conversation=conversation, sender=MessageSender.CUSTOMER).first()
        self.assertEqual(customer_msg.content, "Hello")
        self.assertEqual(customer_msg.channel_message_id, "SMabc")

        ai_msg = Message.objects.filter(conversation=conversation, sender=MessageSender.AI).first()
        self.assertEqual(ai_msg.content, "Hello, how can I help?")
        mock_send.assert_called_once_with("+15551234567", "Hello, how can I help?")

    def test_status_update_path(self):
        # Create a message to update
        conv = Conversation.objects.create(
            organization=self.org,
            channel=Channel.WHATSAPP,
            customer_phone="+15551234567",
        )
        msg = Message.objects.create(
            conversation=conv,
            sender=MessageSender.AI,
            content="x",
            channel_message_id="SMstatus",
        )
        params = {"MessageSid": "SMstatus", "MessageStatus": "delivered"}
        TwilioService(self.config).process_webhook(params)
        msg.refresh_from_db()
        self.assertEqual(msg.ai_metadata.get("delivery_status"), "delivered")


class TwilioServiceOutboundTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Outbound Org")
        self.config = TwilioConfig.objects.create(
            organization=self.org,
            account_sid="ACtestsid",
            auth_token="testtoken",
            from_number="+14155238886",
            is_active=True,
        )

    @patch("apps.channels.twilio_service.requests.post")
    def test_send_message_posts_to_twilio_with_basic_auth(self, mock_post):
        mock_post.return_value.ok = True
        mock_post.return_value.json.return_value = {"sid": "SMsentid"}
        mock_post.return_value.raise_for_status = lambda: None

        sid = TwilioService(self.config).send_message("+15551234567", "hi there")
        self.assertEqual(sid, "SMsentid")

        args, kwargs = mock_post.call_args
        self.assertIn("Accounts/ACtestsid/Messages.json", args[0])
        self.assertEqual(kwargs["auth"], ("ACtestsid", "testtoken"))
        self.assertEqual(kwargs["data"]["From"], "whatsapp:+14155238886")
        self.assertEqual(kwargs["data"]["To"], "whatsapp:+15551234567")
        self.assertEqual(kwargs["data"]["Body"], "hi there")

    def test_send_message_short_circuits_when_inactive(self):
        self.config.is_active = False
        self.config.save()
        with patch("apps.channels.twilio_service.requests.post") as mock_post:
            sid = TwilioService(self.config).send_message("+15551234567", "x")
        self.assertIsNone(sid)
        mock_post.assert_not_called()


class AIResponseRecoveryTest(TestCase):
    """The robust JSON parser must never leak a raw `{"content": ...` envelope."""

    def setUp(self):
        from apps.ai_engine.services import AIService
        self.recover = AIService._recover_content_from_broken_json

    def test_recovers_truncated_envelope(self):
        # The exact failure mode that hit production: max_tokens cut the response
        broken = '{"content": "Here is our menu:\\n\\n*Appetizer:*\\n- Aludum: $60.00\\n- Chicken'
        recovered = self.recover(broken)
        self.assertIsNotNone(recovered)
        self.assertIn("Here is our menu:", recovered)
        self.assertIn("Aludum", recovered)
        self.assertNotIn('"content"', recovered)
        self.assertNotIn('\\n', recovered)  # backslash-n must be unescaped

    def test_recovers_complete_envelope(self):
        recovered = self.recover('{"content": "hello world", "intent": "greeting"}')
        # complete JSON would normally be parsed via json.loads upstream; the
        # recovery path should still extract just the content
        self.assertEqual(recovered, "hello world")

    def test_returns_none_for_non_json(self):
        self.assertIsNone(self.recover("just plain text"))
        self.assertIsNone(self.recover(""))
        self.assertIsNone(self.recover("{not json"))

    def test_handles_unicode_escapes(self):
        recovered = self.recover('{"content": "Caf\\u00e9 open!')
        self.assertEqual(recovered, "Café open!")


class FastPathGreetingTest(TestCase):
    """Greetings should bypass OpenAI and reply instantly."""

    def setUp(self):
        from apps.messaging.models import Conversation, Channel
        from apps.ai_engine.services import AIService
        self.AIService = AIService

        self.org = Organization.objects.create(name="FastPath Resto")
        self.conversation = Conversation.objects.create(
            organization=self.org,
            channel=Channel.WHATSAPP,
            customer_phone="+15551234567",
        )

    def _service(self):
        s = self.AIService(self.conversation)
        # Force English so we don't depend on language detection here
        s.detected_language = 'en'
        return s

    def test_hi_triggers_fast_path(self):
        s = self._service()
        result = s._fast_path_greeting("hi", 'en')
        self.assertIsNotNone(result)
        self.assertEqual(result['intent'], 'greeting')
        self.assertEqual(result['metadata']['source'], 'fast_path')
        self.assertIn('FastPath Resto', result['content'])

    def test_common_variants_all_trigger(self):
        s = self._service()
        for greeting in ['Hi', 'HELLO', 'hey!', 'good morning', 'hye', 'Namaste']:
            self.assertIsNotNone(
                s._fast_path_greeting(greeting, 'en'),
                f"expected fast-path for {greeting!r}",
            )

    def test_chinese_greeting_returns_chinese_reply(self):
        s = self._service()
        result = s._fast_path_greeting("你好", 'zh-CN')
        self.assertIsNotNone(result)
        self.assertIn('你好', result['content'])
        self.assertIn('FastPath Resto', result['content'])

    def test_real_question_does_not_trigger_fast_path(self):
        s = self._service()
        for question in [
            "Can you share me your menu?",
            "What time do you open?",
            "I want to book a table for 4",
            "hi can I make a booking",  # starts with hi but is a real question
        ]:
            self.assertIsNone(
                s._fast_path_greeting(question, 'en'),
                f"fast-path should NOT trigger for {question!r}",
            )

    def test_long_message_does_not_trigger(self):
        s = self._service()
        long_msg = "hi" * 20
        self.assertIsNone(s._fast_path_greeting(long_msg, 'en'))

    def test_empty_returns_none(self):
        s = self._service()
        self.assertIsNone(s._fast_path_greeting("", 'en'))
        self.assertIsNone(s._fast_path_greeting("   ", 'en'))


class TwilioWebhookViewTest(TestCase):
    """Smoke test for the webhook URL: routes to the right org by To-number."""

    def setUp(self):
        self.org = Organization.objects.create(name="Webhook Org")
        self.config = TwilioConfig.objects.create(
            organization=self.org,
            account_sid="ACtestsid",
            auth_token="testtoken",
            from_number="+14155238886",
            is_active=True,
        )
        self.client = Client()

    @patch("apps.channels.twilio_service.AIService")
    @patch.object(TwilioService, "send_message", return_value="SMout")
    def test_webhook_post_routes_to_org(self, _send, mock_ai_cls):
        mock_ai = MagicMock()
        mock_ai.client = object()
        mock_ai.process_message.return_value = {
            "content": "hi", "confidence": 0.9, "intent": "g",
            "language": "en", "needs_handoff": False,
        }
        mock_ai_cls.return_value = mock_ai

        # No X-Twilio-Signature → service skips verification, but the view
        # only verifies when the header is present, so this is fine.
        response = self.client.post(
            "/api/webhooks/twilio/",
            data={
                "From": "whatsapp:+15551234567",
                "To": "whatsapp:+14155238886",
                "Body": "Hello",
                "MessageSid": "SMabc",
                "ProfileName": "T",
                "NumMedia": "0",
            },
        )
        self.assertEqual(response.status_code, 200)
        # WebhookLog created and processed
        log = WebhookLog.objects.filter(source=WebhookLog.Source.TWILIO).order_by("-created_at").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.organization_id, self.org.id)
        self.assertTrue(log.is_processed)
