"""
AI Service - Core AI processing logic.
"""
import json
import logging
import time
from typing import Dict, Any, Optional, List

from django.conf import settings
from django.db.models import Q
from openai import OpenAI

from apps.messaging.models import Conversation, Message, MessageSender
from apps.knowledge.models import KnowledgeBase, FAQ
from .models import AILog

logger = logging.getLogger(__name__)


class AIService:
    """
    Service for processing messages with AI.
    Uses OpenAI API with knowledge base context.
    """

    CONFIDENCE_THRESHOLD = getattr(settings, 'AI_CONFIDENCE_THRESHOLD', 0.7)
    MAX_CONTEXT_MESSAGES = getattr(settings, 'AI_MAX_CONTEXT_MESSAGES', 10)

    def __init__(self, conversation: Conversation):
        self.conversation = conversation
        self.organization = conversation.organization
        self.location = conversation.location
        self.client = None

        if settings.OPENAI_API_KEY:
            self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def process_message(self, user_message: str) -> Dict[str, Any]:
        """
        Process a user message and generate AI response.

        Returns:
            Dict with keys: content, confidence, intent, metadata, needs_handoff, handoff_reason
        """
        start_time = time.time()

        # If no OpenAI key, return handoff response
        if not self.client:
            return self._create_handoff_response(
                "I'll connect you with a team member who can help you better.",
                "no_api_key",
                0.0
            )

        try:
            # Build context
            system_prompt = self._build_system_prompt()
            messages = self._build_message_history(user_message)

            # Call OpenAI
            response = self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=messages,
                max_tokens=settings.OPENAI_MAX_TOKENS,
                temperature=settings.OPENAI_TEMPERATURE,
                response_format={"type": "json_object"},
            )

            # Parse response
            content = response.choices[0].message.content
            parsed = self._parse_ai_response(content)

            latency_ms = int((time.time() - start_time) * 1000)

            # Log the interaction
            self._log_interaction(
                prompt=user_message,
                response=parsed['content'],
                confidence=parsed['confidence'],
                intent=parsed['intent'],
                model=settings.OPENAI_MODEL,
                tokens=response.usage.total_tokens if response.usage else 0,
                latency_ms=latency_ms,
            )

            # Check if handoff needed
            if parsed['confidence'] < self.CONFIDENCE_THRESHOLD:
                parsed['needs_handoff'] = True
                parsed['handoff_reason'] = 'low_confidence'

            if parsed.get('escalate', False):
                parsed['needs_handoff'] = True
                parsed['handoff_reason'] = parsed.get('escalate_reason', 'ai_requested')

            return parsed

        except Exception as e:
            logger.exception(f"AI processing error: {e}")
            self._log_interaction(
                prompt=user_message,
                response="",
                confidence=0.0,
                intent="error",
                model=settings.OPENAI_MODEL,
                tokens=0,
                latency_ms=int((time.time() - start_time) * 1000),
                error=str(e),
            )
            return self._create_handoff_response(
                "I apologize, but I'm having trouble processing your request. Let me connect you with a team member.",
                "ai_error",
                0.0
            )

    def _build_system_prompt(self) -> str:
        """Build the system prompt with knowledge base context."""
        # Get knowledge base
        knowledge = self._get_knowledge_context()

        business_type = self.organization.business_type
        business_name = self.organization.name
        location_name = self.location.name if self.location else "Main Location"

        prompt = f"""You are a helpful AI assistant for {business_name}, a {business_type} business.
You are currently helping customers at the {location_name} location.

IMPORTANT RULES:
1. Only answer questions using the provided knowledge base information below.
2. If you don't know the answer or are uncertain, you MUST say "I'll connect you with a team member who can help you better."
3. Never make up information or hallucinate facts.
4. Be friendly, professional, and concise.
5. Always respond in JSON format with the following structure:
   {{
     "content": "Your response to the customer",
     "confidence": 0.0-1.0,
     "intent": "category of the question",
     "escalate": true/false,
     "escalate_reason": "reason if escalate is true"
   }}

KNOWLEDGE BASE:
{knowledge}

INTENT CATEGORIES:
- greeting: Hello, hi, etc.
- hours: Business hours questions
- location: Address, directions
- menu: Menu items, prices (for restaurants)
- booking: Reservations, appointments
- property: Property listings (for real estate)
- pricing: Prices, costs
- general: General questions
- complaint: Complaints or issues
- other: Anything else

If the customer seems frustrated, has a complaint, or requests to speak to someone, set escalate to true.
"""
        return prompt

    def _get_knowledge_context(self) -> str:
        """Get knowledge base context for the organization/location."""
        context_parts = []

        # Get knowledge base
        try:
            # Get location-specific knowledge first (overrides org-level)
            if self.location:
                kb = KnowledgeBase.objects.filter(
                    organization=self.organization,
                    location=self.location
                ).first()
                if kb:
                    context_parts.append(self._format_knowledge_base(kb))

            # Get org-level knowledge
            kb = KnowledgeBase.objects.filter(
                organization=self.organization,
                location__isnull=True
            ).first()
            if kb:
                context_parts.append(self._format_knowledge_base(kb))

            # Get FAQs from knowledge bases
            faqs = FAQ.objects.filter(
                knowledge_base__organization=self.organization,
                is_active=True
            )
            if self.location:
                faqs = faqs.filter(
                    Q(knowledge_base__location=self.location) | Q(knowledge_base__location__isnull=True)
                )

            if faqs.exists():
                faq_text = "\n\nFREQUENTLY ASKED QUESTIONS:\n"
                for faq in faqs[:20]:  # Limit FAQs
                    faq_text += f"\nQ: {faq.question}\nA: {faq.answer}\n"
                context_parts.append(faq_text)

        except Exception as e:
            logger.warning(f"Error getting knowledge context: {e}")

        if not context_parts:
            return "No specific knowledge base configured. Please help the customer with general inquiries and offer to connect them with a team member for specific questions."

        return "\n".join(context_parts)

    def _format_knowledge_base(self, kb: 'KnowledgeBase') -> str:
        """Format knowledge base for prompt."""
        parts = []

        if kb.business_description:
            parts.append(f"ABOUT US:\n{kb.business_description}")

        if kb.opening_hours:
            parts.append(f"\nOPENING HOURS:\n{json.dumps(kb.opening_hours, indent=2)}")

        if kb.contact_info:
            parts.append(f"\nCONTACT INFO:\n{json.dumps(kb.contact_info, indent=2)}")

        if kb.additional_info:
            parts.append(f"\nADDITIONAL INFO:\n{kb.additional_info}")

        return "\n".join(parts)

    def _build_message_history(self, current_message: str) -> List[Dict[str, str]]:
        """Build message history for context."""
        messages = [{"role": "system", "content": self._build_system_prompt()}]

        # Get recent messages
        recent_messages = self.conversation.messages.order_by('-created_at')[:self.MAX_CONTEXT_MESSAGES]
        recent_messages = list(reversed(recent_messages))

        for msg in recent_messages:
            role = "assistant" if msg.sender in [MessageSender.AI, MessageSender.HUMAN] else "user"
            messages.append({"role": role, "content": msg.content})

        # Add current message
        messages.append({"role": "user", "content": current_message})

        return messages

    def _parse_ai_response(self, content: str) -> Dict[str, Any]:
        """Parse AI response JSON."""
        try:
            parsed = json.loads(content)
            return {
                'content': parsed.get('content', content),
                'confidence': float(parsed.get('confidence', 0.5)),
                'intent': parsed.get('intent', 'other'),
                'escalate': parsed.get('escalate', False),
                'escalate_reason': parsed.get('escalate_reason', ''),
                'metadata': parsed,
                'needs_handoff': False,
                'handoff_reason': '',
            }
        except json.JSONDecodeError:
            # If not valid JSON, return as plain text with low confidence
            return {
                'content': content,
                'confidence': 0.5,
                'intent': 'other',
                'metadata': {},
                'needs_handoff': False,
                'handoff_reason': '',
            }

    def _create_handoff_response(
        self,
        message: str,
        reason: str,
        confidence: float
    ) -> Dict[str, Any]:
        """Create a handoff response."""
        return {
            'content': message,
            'confidence': confidence,
            'intent': 'handoff',
            'metadata': {},
            'needs_handoff': True,
            'handoff_reason': reason,
        }

    def _log_interaction(
        self,
        prompt: str,
        response: str,
        confidence: float,
        intent: str,
        model: str,
        tokens: int,
        latency_ms: int,
        error: str = "",
    ):
        """Log the AI interaction."""
        try:
            AILog.objects.create(
                organization=self.organization,
                conversation=self.conversation,
                prompt=prompt,
                context={'location': str(self.location.id) if self.location else None},
                response=response,
                confidence_score=confidence,
                intent=intent,
                model=model,
                tokens_used=tokens,
                processing_time=latency_ms / 1000.0,  # Convert ms to seconds
                error=error,
            )
        except Exception as e:
            logger.warning(f"Failed to log AI interaction: {e}")
