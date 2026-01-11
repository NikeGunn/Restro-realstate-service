"""
AI Service - Core AI processing logic.
"""
import json
import logging
import time
from typing import Dict, Any, Optional, List

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
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
        
        # Get vertical-specific context
        vertical_context = self._get_vertical_context()

        business_type = self.organization.business_type
        business_name = self.organization.name
        location_name = self.location.name if self.location else "Main Location"
        
        # Base prompt
        prompt = f"""You are an AI assistant (NOT a human) for {business_name}, a {business_type} business.
You are currently helping customers at the {location_name} location.

CRITICAL GREETING RULE - MUST FOLLOW:
When a customer says "hello", "hi", "hey", or greets you in ANY way, you MUST respond with this EXACT format:
"Hello! I'm [AI Name], your AI assistant for {business_name}. How can I help you today?"

Examples of CORRECT greeting responses:
- "Hello! I'm AI Assistant, your AI assistant for {business_name}. How can I help you today?"
- "Hi there! I'm your AI assistant for {business_name}. What can I help you with today?"
- "Hello! I'm the AI assistant at {business_name}. How may I assist you?"

NEVER respond with just "Hello! How can I assist you today?" - You MUST identify yourself as AI and mention the business name.

IMPORTANT RULES:
1. ALWAYS identify yourself as an AI assistant in greetings
2. ALWAYS mention the business name "{business_name}" when greeting
3. Only answer questions using the provided knowledge base information below
4. If you don't know the answer or are uncertain, say "I'll connect you with a team member who can help you better"
5. Never make up information or hallucinate facts
6. Be friendly, professional, and concise
7. Always respond in JSON format with the following structure:
   {{
     "content": "Your response to the customer",
     "confidence": 0.0-1.0,
     "intent": "category of the question",
     "escalate": true/false,
     "escalate_reason": "reason if escalate is true",
     "extracted_data": {{}}
   }}

EXAMPLE GREETING RESPONSE (when user says "Hello"):
{{
  "content": "Hello! I'm AI Assistant, your AI assistant for {business_name}. How can I help you today?",
  "confidence": 1.0,
  "intent": "greeting",
  "escalate": false,
  "escalate_reason": "",
  "extracted_data": {{}}
}}

KNOWLEDGE BASE:
{knowledge}
"""
        
        # Add vertical-specific instructions
        if business_type == 'restaurant':
            prompt += self._get_restaurant_prompt(vertical_context)
        elif business_type == 'real_estate':
            prompt += self._get_realestate_prompt(vertical_context)
        
        prompt += """
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
- lead_capture: Customer providing contact info
- other: Anything else

If the customer seems frustrated, has a complaint, or requests to speak to someone, set escalate to true.
"""
        return prompt
    
    def _get_vertical_context(self) -> Dict[str, Any]:
        """Get vertical-specific context based on business type."""
        context = {}
        
        if self.organization.business_type == 'restaurant':
            context = self._get_restaurant_context()
        elif self.organization.business_type == 'real_estate':
            context = self._get_realestate_context()
        
        return context
    
    def _get_restaurant_context(self) -> Dict[str, Any]:
        """Get restaurant-specific context."""
        context = {
            'menu': [],
            'specials': [],
            'hours': [],
        }
        
        try:
            from apps.restaurant.models import MenuCategory, DailySpecial, OpeningHours
            
            # Get menu categories with items
            categories = MenuCategory.objects.filter(
                organization=self.organization,
                is_active=True
            ).prefetch_related('items')
            
            if self.location:
                categories = categories.filter(
                    Q(location=self.location) | Q(location__isnull=True)
                )
            
            for cat in categories[:10]:  # Limit categories
                items = []
                for item in cat.items.filter(is_active=True, is_available=True)[:20]:
                    items.append({
                        'name': item.name,
                        'description': item.description[:100] if item.description else '',
                        'price': float(item.price),
                        'dietary': item.dietary_info,
                    })
                if items:
                    context['menu'].append({
                        'category': cat.name,
                        'items': items
                    })
            
            # Get today's specials
            today = timezone.now().date()
            specials = DailySpecial.objects.filter(
                organization=self.organization,
                start_date__lte=today,
                end_date__gte=today,
                is_active=True
            )
            if self.location:
                specials = specials.filter(
                    Q(location=self.location) | Q(location__isnull=True)
                )
            
            for special in specials[:5]:
                if special.is_available_today:
                    context['specials'].append({
                        'name': special.name,
                        'description': special.description[:100],
                        'price': float(special.price),
                        'original_price': float(special.original_price) if special.original_price else None,
                    })
            
            # Get opening hours
            if self.location:
                hours = OpeningHours.objects.filter(location=self.location)
                for h in hours:
                    context['hours'].append({
                        'day': h.get_day_of_week_display(),
                        'open': str(h.open_time) if h.open_time else None,
                        'close': str(h.close_time) if h.close_time else None,
                        'closed': h.is_closed,
                    })
                    
        except Exception as e:
            logger.warning(f"Error getting restaurant context: {e}")
        
        return context
    
    def _get_realestate_context(self) -> Dict[str, Any]:
        """Get real estate-specific context."""
        context = {
            'featured_properties': [],
            'property_types': [],
            'areas': [],
        }
        
        try:
            from apps.realestate.models import PropertyListing
            
            # Get featured/active properties
            properties = PropertyListing.objects.filter(
                organization=self.organization,
                status=PropertyListing.Status.ACTIVE,
                is_published=True
            ).order_by('-is_featured', '-created_at')[:10]
            
            for prop in properties:
                context['featured_properties'].append({
                    'title': prop.title,
                    'type': prop.get_listing_type_display(),
                    'property_type': prop.get_property_type_display(),
                    'price': float(prop.price),
                    'city': prop.city,
                    'bedrooms': prop.bedrooms,
                    'bathrooms': float(prop.bathrooms) if prop.bathrooms else None,
                    'sqft': prop.square_feet,
                })
            
            # Get unique property types and areas
            context['property_types'] = list(
                PropertyListing.objects.filter(
                    organization=self.organization,
                    status=PropertyListing.Status.ACTIVE
                ).values_list('property_type', flat=True).distinct()
            )
            
            context['areas'] = list(
                PropertyListing.objects.filter(
                    organization=self.organization,
                    status=PropertyListing.Status.ACTIVE
                ).values_list('city', flat=True).distinct()[:10]
            )
            
        except Exception as e:
            logger.warning(f"Error getting real estate context: {e}")
        
        return context
    
    def _get_restaurant_prompt(self, context: Dict[str, Any]) -> str:
        """Generate restaurant-specific prompt section."""
        prompt = """
RESTAURANT-SPECIFIC CAPABILITIES:
You can help customers with:
1. Menu questions - answer about dishes, prices, ingredients, dietary options
2. Opening hours - tell customers when the restaurant is open
3. Reservations/Bookings - collect booking information (date, time, party size, name, phone)
4. Daily specials - inform about current promotions

GREETING EXAMPLES FOR RESTAURANT:
- "Hello! I'm your AI dining assistant for [Restaurant Name]. I can help you with our menu, hours, or make a reservation. What would you like to know?"
- "Hi there! I'm the AI assistant at [Restaurant Name]. How can I help you today - menu questions, reservations, or something else?"

FOR BOOKING REQUESTS:
When a customer wants to make a reservation, collect this information:
- Preferred date
- Preferred time  
- Party size (number of guests)
- Customer name
- Contact phone number

Include collected booking data in the "extracted_data" field like:
{
  "extracted_data": {
    "booking_intent": true,
    "date": "2025-01-15",
    "time": "19:00",
    "party_size": 4,
    "customer_name": "John Smith",
    "customer_phone": "555-1234"
  }
}

If any required booking info is missing, ask for it in a friendly way.
If the restaurant might be fully booked or it's a large party (8+), escalate to human.

"""
        
        # Add menu context
        if context.get('menu'):
            prompt += "\nCURRENT MENU:\n"
            for cat in context['menu']:
                prompt += f"\n{cat['category']}:\n"
                for item in cat['items']:
                    dietary = ', '.join(k for k, v in item['dietary'].items() if v) if item['dietary'] else ''
                    prompt += f"  - {item['name']}: ${item['price']:.2f}"
                    if dietary:
                        prompt += f" ({dietary})"
                    prompt += "\n"
        
        # Add specials
        if context.get('specials'):
            prompt += "\nTODAY'S SPECIALS:\n"
            for special in context['specials']:
                prompt += f"  - {special['name']}: ${special['price']:.2f}"
                if special['original_price']:
                    prompt += f" (was ${special['original_price']:.2f})"
                prompt += f"\n    {special['description']}\n"
        
        # Add hours
        if context.get('hours'):
            prompt += "\nOPENING HOURS:\n"
            for h in context['hours']:
                if h['closed']:
                    prompt += f"  {h['day']}: Closed\n"
                else:
                    prompt += f"  {h['day']}: {h['open']} - {h['close']}\n"
        
        return prompt
    
    def _get_realestate_prompt(self, context: Dict[str, Any]) -> str:
        """Generate real estate-specific prompt section."""
        prompt = """
REAL ESTATE-SPECIFIC CAPABILITIES:
You can help customers with:
1. Property searches - help find properties matching their criteria
2. Property information - answer questions about specific listings
3. Lead qualification - collect buyer/renter information
4. Appointment scheduling - schedule property viewings

GREETING EXAMPLES FOR REAL ESTATE:
- "Hello! I'm your AI property assistant for [Company Name]. I can help you find properties, answer questions, or schedule a viewing. What are you looking for today?"
- "Hi there! I'm the AI assistant at [Company Name]. Are you looking to buy, rent, or sell a property?"

FOR LEAD QUALIFICATION:
When a customer shows interest, collect this information:
- Intent: Buy, Rent, or Sell?
- Budget range (min/max)
- Preferred areas/neighborhoods
- Property type preference (house, apartment, etc.)
- Number of bedrooms needed
- Timeline (when do they need to move?)
- Name and contact phone

Include collected lead data in the "extracted_data" field like:
{
  "extracted_data": {
    "lead_intent": "buy",
    "budget_min": 300000,
    "budget_max": 500000,
    "preferred_areas": ["Downtown", "Midtown"],
    "property_type": "house",
    "bedrooms": 3,
    "timeline": "3 months",
    "customer_name": "Jane Doe",
    "customer_phone": "555-5678"
  }
}

FOR HIGH-INTENT LEADS (ready to buy, pre-approved, specific property interest), set escalate to true.

"""
        
        # Add featured properties
        if context.get('featured_properties'):
            prompt += "\nFEATURED PROPERTIES:\n"
            for prop in context['featured_properties'][:5]:
                prompt += f"  - {prop['title']}\n"
                prompt += f"    {prop['type']} | {prop['property_type']} | ${prop['price']:,.0f}\n"
                prompt += f"    {prop['city']}"
                if prop['bedrooms']:
                    prompt += f" | {prop['bedrooms']} bed"
                if prop['bathrooms']:
                    prompt += f" | {prop['bathrooms']} bath"
                if prop['sqft']:
                    prompt += f" | {prop['sqft']:,} sqft"
                prompt += "\n"
        
        # Add available areas
        if context.get('areas'):
            prompt += f"\nAVAILABLE AREAS: {', '.join(context['areas'])}\n"
        
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
                'extracted_data': parsed.get('extracted_data', {}),
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
                'extracted_data': {},
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
