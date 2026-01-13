"""
AI Service - Core AI processing logic.
Supports multilingual conversations: English, Simplified Chinese, Traditional Chinese.
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
from .language_service import LanguageService, LanguageCode, detect_language

logger = logging.getLogger(__name__)


class AIService:
    """
    Service for processing messages with AI.
    Uses OpenAI API with knowledge base context.
    Supports multilingual conversations (English, Simplified Chinese, Traditional Chinese).
    """

    CONFIDENCE_THRESHOLD = getattr(settings, 'AI_CONFIDENCE_THRESHOLD', 0.7)
    MAX_CONTEXT_MESSAGES = getattr(settings, 'AI_MAX_CONTEXT_MESSAGES', 10)

    def __init__(self, conversation: Conversation):
        self.conversation = conversation
        self.organization = conversation.organization
        self.location = conversation.location
        self.client = None
        self.detected_language = LanguageCode.ENGLISH  # Default language

        if settings.OPENAI_API_KEY:
            self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
    
    def _detect_and_set_language(self, user_message: str) -> str:
        """
        Detect the language of the user message and update conversation if needed.
        Returns the detected language code.
        """
        detected = detect_language(user_message)
        self.detected_language = detected
        
        # Update conversation language if it has changed or not set
        current_lang = getattr(self.conversation, 'detected_language', None)
        if current_lang != detected:
            try:
                self.conversation.detected_language = detected
                self.conversation.save(update_fields=['detected_language'])
                logger.info(f"Updated conversation {self.conversation.id} language to: {detected}")
            except Exception as e:
                # Field might not exist yet (before migration)
                logger.debug(f"Could not update conversation language: {e}")
        
        return detected

    def process_message(self, user_message: str) -> Dict[str, Any]:
        """
        Process a user message and generate AI response.
        Automatically detects language and responds in the same language.

        Returns:
            Dict with keys: content, confidence, intent, metadata, needs_handoff, handoff_reason, language
        """
        start_time = time.time()
        
        # Detect user's language first
        detected_lang = self._detect_and_set_language(user_message)
        logger.info(f"Processing message in language: {detected_lang}")

        # If no OpenAI key, return handoff response in detected language
        if not self.client:
            return self._create_handoff_response(
                LanguageService.get_handoff_message(detected_lang),
                "no_api_key",
                0.0
            )

        try:
            # Build context with language awareness
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
            
            # Add language to response
            parsed['language'] = detected_lang

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
                language=detected_lang,
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
                language=detected_lang,
            )
            return self._create_handoff_response(
                LanguageService.get_error_message(detected_lang),
                "ai_error",
                0.0
            )

    def _build_system_prompt(self) -> str:
        """Build the system prompt with knowledge base context and language awareness."""
        # Get knowledge base
        knowledge = self._get_knowledge_context()
        
        # Get vertical-specific context
        vertical_context = self._get_vertical_context()

        business_type = self.organization.business_type
        business_name = self.organization.name
        location_name = self.location.name if self.location else "Main Location"
        
        # Get language-specific greeting
        greeting_text = LanguageService.get_greeting_for_language(self.detected_language, business_name)
        handoff_text = LanguageService.get_handoff_message(self.detected_language)
        language_instruction = LanguageService.get_language_instruction(self.detected_language)
        language_display = LanguageService.get_language_display_name(self.detected_language)
        
        # Base prompt with multilingual support
        prompt = f"""You are an AI assistant (NOT a human) for {business_name}, a {business_type} business.
You are currently helping customers at the {location_name} location.

🌍 MULTILINGUAL SUPPORT - CRITICAL RULES:
==========================================
{language_instruction}

The customer's detected language is: {language_display}
ALL your responses MUST be in {language_display}.

DO NOT mix languages.
DO NOT respond in English if the customer writes in Chinese.
DO NOT respond in Chinese if the customer writes in English.
MATCH the customer's language EXACTLY.
==========================================

🚨 CRITICAL GREETING RULE - THIS IS MANDATORY - NO EXCEPTIONS:
==========================================
When a customer greets you (hello, hi, hey, 你好, 您好, 嗨, etc.), you MUST ALWAYS respond with:
"{greeting_text}"

CORRECT greeting response (use this exact format):
{{"content": "{greeting_text}", "confidence": 1.0, "intent": "greeting", "escalate": false}}

==========================================

IMPORTANT RULES:
1. 🚨 RULE #1 (HIGHEST PRIORITY): ALWAYS respond in the same language as the customer
2. For ANY greeting, ALWAYS include "I'm AI Assistant" (or equivalent in customer's language)
3. Only answer questions using the provided knowledge base information below
4. If you don't know the answer or are uncertain, say "{handoff_text}"
5. Never make up information or hallucinate facts
6. Be friendly, professional, and concise
7. Always respond in JSON format with the following structure:
   {{
     "content": "Your response to the customer IN THEIR LANGUAGE",
     "confidence": 0.0-1.0,
     "intent": "category of the question",
     "escalate": true/false,
     "escalate_reason": "reason if escalate is true",
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
            'customer_bookings': [],
            'customer_phone': self.conversation.customer_phone if self.conversation else None,
            'channel': str(self.conversation.channel) if self.conversation else 'website',
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
            
            # Get customer's existing bookings (for WhatsApp/returning customers)
            if self.conversation and self.conversation.customer_phone:
                from apps.restaurant.models import Booking
                customer_bookings = Booking.objects.filter(
                    organization=self.organization,
                    customer_phone=self.conversation.customer_phone,
                    status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED]
                ).order_by('booking_date', 'booking_time')[:5]
                
                for booking in customer_bookings:
                    context['customer_bookings'].append({
                        'confirmation_code': booking.confirmation_code,
                        'date': str(booking.booking_date),
                        'time': str(booking.booking_time),
                        'party_size': booking.party_size,
                        'status': booking.status,
                        'customer_name': booking.customer_name,
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
        """Generate restaurant-specific prompt section with multilingual support."""
        # Get language-specific booking prompts
        lang = self.detected_language
        booking_intro = LanguageService.get_template(lang, 'booking_intro')
        booking_date = LanguageService.get_template(lang, 'booking_date')
        booking_time = LanguageService.get_template(lang, 'booking_time')
        booking_party = LanguageService.get_template(lang, 'booking_party_size')
        booking_name = LanguageService.get_template(lang, 'booking_name')
        booking_phone = LanguageService.get_template(lang, 'booking_phone')
        
        # Get customer info from context
        customer_phone = context.get('customer_phone', '')
        channel = context.get('channel', 'website')
        customer_bookings = context.get('customer_bookings', [])
        
        # Determine if phone is already known (WhatsApp/Instagram)
        phone_known = bool(customer_phone) and channel in ['whatsapp', 'instagram']
        
        prompt = f"""
RESTAURANT-SPECIFIC CAPABILITIES:
You can help customers with:
1. Menu questions - answer about dishes, prices, ingredients, dietary options
2. Opening hours - tell customers when the restaurant is open
3. Reservations/Bookings - CREATE new bookings, VIEW existing bookings, CANCEL bookings
4. Daily specials - inform about current promotions
5. Booking management - check reservation status, provide booking details, cancel reservations

REMEMBER: Always respond in the customer's language ({LanguageService.get_language_display_name(lang)})

"""
        
        # Add phone context for WhatsApp/Instagram
        if phone_known:
            prompt += f"""
📱 CHANNEL INFO: This customer is contacting via {channel.upper()}.
   Customer phone: {customer_phone}
   🚨 DO NOT ask for phone number - use the phone above automatically for bookings!
   
"""
        
        # Add existing bookings context
        if customer_bookings:
            prompt += """
📅 CUSTOMER'S EXISTING RESERVATIONS:
"""
            for b in customer_bookings:
                prompt += f"""  - Confirmation: {b['confirmation_code']}
    Date: {b['date']} at {b['time']}
    Party size: {b['party_size']} guests
    Name: {b['customer_name']}
    Status: {b['status']}
"""
            prompt += """
When the customer asks about their reservation, booking details, or wants to cancel:
- Use the booking information above to answer their questions
- Provide the confirmation code and details
- For cancellations, include cancel_booking_code in extracted_data

"""
        
        prompt += f"""
FOR NEW BOOKING REQUESTS:
When a customer wants to make a NEW reservation, collect this information:
- Preferred date ("{booking_date}") - Accept "today", "tonight", "tomorrow", or specific dates
- Preferred time ("{booking_time}") - Accept formats like "7pm", "19:00", "12:30 PM"
- Party size ("{booking_party}")
- Customer name ("{booking_name}")"""
        
        if not phone_known:
            prompt += f"""
- Contact phone ("{booking_phone}")"""
        
        prompt += f"""

🚨 CRITICAL BOOKING RULE - WHEN ALL INFO IS COLLECTED:
When you have collected ALL required booking information, you MUST include the data in "extracted_data":

{{
  "content": "Your confirmation message to the customer",
  "confidence": 0.95,
  "intent": "booking",
  "extracted_data": {{
    "booking_intent": true,
    "date": "today",
    "time": "16:00",
    "party_size": 5,
    "customer_name": "Neha Bhagat",
    "customer_phone": "{customer_phone if phone_known else '9705651002'}"
  }}
}}

"""
        if phone_known:
            prompt += f"""⚠️ IMPORTANT: For {channel.upper()} customers, ALWAYS use "{customer_phone}" as customer_phone!
"""
        
        prompt += """
🚨 FOR BOOKING QUERIES (view reservation, check booking, what's my reservation):
When customer asks about their existing booking, provide the details from their reservations above.
If they have no reservations, tell them they don't have any active bookings.

🚨 FOR CANCELLATION REQUESTS:
When customer wants to cancel a booking:
1. If they have bookings listed above, confirm which one they want to cancel
2. Include the cancellation in extracted_data:

{
  "content": "Your cancellation confirmation message",
  "confidence": 0.95,
  "intent": "booking_cancel",
  "extracted_data": {
    "cancel_booking_code": "RES123ABC"
  }
}

IMPORTANT: 
- "booking_intent" MUST be set to true when confirming a NEW booking
- "cancel_booking_code" should contain the confirmation code to cancel
- Track and accumulate booking info across messages in the conversation
- For date, use "today", "tonight", "tomorrow" or actual date
- For time, use 24-hour format like "16:00" or "19:00"

If the restaurant might be fully booked or it's a large party (8+), escalate to human.

"""
        
        # Add menu context
        if context.get('menu'):
            prompt += "\nCURRENT MENU:\n"
            for cat in context['menu']:
                prompt += f"\n{cat['category']}:\n"
                for item in cat['items']:
                    # dietary can be a list of strings like ["vegetarian", "vegan"] or a dict
                    dietary_info = item.get('dietary', [])
                    if isinstance(dietary_info, list):
                        dietary = ', '.join(dietary_info) if dietary_info else ''
                    elif isinstance(dietary_info, dict):
                        dietary = ', '.join(k for k, v in dietary_info.items() if v) if dietary_info else ''
                    else:
                        dietary = ''
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
        """Generate real estate-specific prompt section with multilingual support."""
        lang = self.detected_language
        property_intro = LanguageService.get_template(lang, 'property_intro')
        lead_budget = LanguageService.get_template(lang, 'lead_budget')
        lead_area = LanguageService.get_template(lang, 'lead_area')
        lead_timeline = LanguageService.get_template(lang, 'lead_timeline')
        
        prompt = f"""
REAL ESTATE-SPECIFIC CAPABILITIES:
You can help customers with:
1. Property searches - help find properties matching their criteria
2. Property information - answer questions about specific listings
3. Lead qualification - collect buyer/renter information
4. Appointment scheduling - schedule property viewings

REMEMBER: Always respond in the customer's language ({LanguageService.get_language_display_name(lang)})

FOR LEAD QUALIFICATION:
When a customer shows interest in buying, renting, or learning about properties, collect this information:
- Intent: "{property_intro}" (buy, rent, sell, or invest)
- Budget: "{lead_budget}" (e.g., $300,000 - $500,000)
- Preferred areas: "{lead_area}" (neighborhoods/cities)
- Property type preference (house, apartment, condo, etc.)
- Number of bedrooms needed
- Timeline: "{lead_timeline}" (when they want to move)
- Name and contact phone

🚨 CRITICAL LEAD CAPTURE RULE - WHEN KEY INFO IS COLLECTED:
When you have collected the customer's intent, name, and phone number (minimum required),
you MUST include the lead data in "extracted_data" to capture the lead:

{{
  "content": "Your confirmation message to the customer",
  "confidence": 0.95,
  "intent": "lead_capture",
  "extracted_data": {{
    "lead_intent": "buy",
    "budget_min": 300000,
    "budget_max": 500000,
    "preferred_areas": ["Downtown", "Midtown"],
    "property_type": "house",
    "bedrooms": 3,
    "timeline": "3 months",
    "customer_name": "Jane Doe",
    "customer_phone": "555-5678",
    "customer_email": "jane@example.com"
  }}
}}

FOR APPOINTMENT/VIEWING SCHEDULING:
When a customer wants to schedule a property viewing or meeting, collect:
- Preferred date
- Preferred time
- Property they want to see (if specific)
- Name and phone (if not already collected)

🚨 CRITICAL APPOINTMENT RULE - WHEN SCHEDULING INFO IS COMPLETE:
When you have collected date, time, name, and phone, include appointment data:

{{
  "content": "Your appointment confirmation message",
  "confidence": 0.95,
  "intent": "appointment",
  "extracted_data": {{
    "appointment_intent": true,
    "appointment_date": "tomorrow",
    "appointment_time": "2:00 PM",
    "appointment_type": "viewing",
    "property_reference": "PROP123456",
    "customer_name": "Jane Doe",
    "customer_phone": "555-5678"
  }}
}}

IMPORTANT:
- "lead_intent" should be the intent type: "buy", "rent", "sell", "invest", or "general"
- "appointment_intent" MUST be set to true when confirming an appointment
- You can include BOTH lead_intent AND appointment_intent in the same response if customer is both interested and scheduling a viewing
- Track and accumulate customer info across messages in the conversation
- For dates, use customer's words like "today", "tomorrow", or actual date
- For high-intent leads (ready to buy, pre-approved, specific property interest), set escalate to true

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
                'language': self.detected_language,
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
                'language': self.detected_language,
            }

    def _create_handoff_response(
        self,
        message: str,
        reason: str,
        confidence: float
    ) -> Dict[str, Any]:
        """Create a handoff response in the detected language."""
        return {
            'content': message,
            'confidence': confidence,
            'intent': 'handoff',
            'metadata': {},
            'needs_handoff': True,
            'handoff_reason': reason,
            'language': self.detected_language,
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
        language: str = "en",
    ):
        """Log the AI interaction with language info."""
        try:
            AILog.objects.create(
                organization=self.organization,
                conversation=self.conversation,
                prompt=prompt,
                context={
                    'location': str(self.location.id) if self.location else None,
                    'language': language,
                },
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
