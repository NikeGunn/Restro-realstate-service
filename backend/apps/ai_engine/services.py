"""
AI Service - Core AI processing logic.
Supports multilingual conversations: English, Simplified Chinese, Traditional Chinese.
Includes temporary override support for manager updates.
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
        Checks for pending manager queries and temporary overrides.

        Returns:
            Dict with keys: content, confidence, intent, metadata, needs_handoff, handoff_reason, language
        """
        start_time = time.time()
        
        # Detect user's language first
        detected_lang = self._detect_and_set_language(user_message)
        logger.info(f"Processing message in language: {detected_lang}")
        
        # PRIORITY 1: Check for manager contact request (e.g., "Can you provide me manager number?")
        manager_contact_response = self._handle_manager_contact_request(user_message, detected_lang)
        if manager_contact_response:
            return manager_contact_response
        
        # Check if there's a pending manager query for this conversation
        pending_response = self._check_pending_manager_query()
        if pending_response:
            return {
                'content': pending_response,
                'confidence': 0.9,
                'intent': 'manager_response',
                'metadata': {'source': 'manager_query'},
                'needs_handoff': False,
                'handoff_reason': '',
                'language': detected_lang,
            }

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
                
                # Proactively escalate to manager and inform customer
                escalation_result = self._proactive_escalate_to_manager(
                    user_message, 
                    parsed, 
                    detected_lang
                )
                if escalation_result:
                    # Append escalation message to response
                    parsed['content'] += escalation_result
                    parsed['manager_notified'] = True
                    logger.info(f"🆘 Proactively escalated to manager for low confidence query")

            if parsed.get('escalate', False):
                parsed['needs_handoff'] = True
                parsed['handoff_reason'] = parsed.get('escalate_reason', 'ai_requested')
                
                # Also proactively escalate if AI explicitly requested
                if not parsed.get('manager_notified'):
                    escalation_result = self._proactive_escalate_to_manager(
                        user_message, 
                        parsed, 
                        detected_lang
                    )
                    if escalation_result:
                        parsed['content'] += escalation_result
                        parsed['manager_notified'] = True

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
        
        # Get temporary overrides from manager
        override_context = self._get_temporary_override_context()

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
"""

        # Add URGENT temporary overrides from manager (HIGHEST PRIORITY)
        if override_context:
            prompt += f"""
🚨🚨🚨 URGENT MANAGER UPDATES - HIGHEST PRIORITY 🚨🚨🚨
==========================================
{override_context}
==========================================
IMPORTANT: The above updates from management take PRIORITY over regular knowledge base.
If a customer asks about hours, availability, or related topics, USE THIS INFORMATION FIRST.
==========================================

"""
        else:
            # NO OVERRIDES - explicitly tell AI to ignore any previous closure messages
            prompt += f"""
✅ CURRENT STATUS - NO SPECIAL OVERRIDES ACTIVE
==========================================
There are NO temporary overrides or special closure notices currently active.
CRITICAL: If you see any previous messages in the conversation history about being "closed" or "not accepting bookings":
- IGNORE those messages - they were from a previous override that is now CANCELLED
- The restaurant is now operating under NORMAL hours (see knowledge base below)
- Respond based ONLY on the regular knowledge base, NOT on previous closure messages
==========================================

"""

        prompt += f"""
🚫 ANTI-HALLUCINATION RULES - STRICTLY FOLLOW:
==========================================
1. ONLY use information from the KNOWLEDGE BASE below
2. NEVER make up prices, hours, menu items, or any other facts
3. NEVER guess or assume information not explicitly provided
4. If you're unsure about ANYTHING, set confidence below 0.7 and escalate=true
5. When in doubt, say: "{handoff_text}"
==========================================

IMPORTANT RULES:
1. 🚨 RULE #1 (HIGHEST PRIORITY): ALWAYS respond in the same language as the customer
2. For ANY greeting, ALWAYS include "I'm AI Assistant" (or equivalent in customer's language)
3. Only answer questions using the provided knowledge base information below
4. If you don't know the answer or are uncertain, say "{handoff_text}" and set escalate=true
5. NEVER make up information or hallucinate facts - if not in knowledge base, escalate
6. Be friendly, professional, and concise
7. When escalating, set confidence below 0.7 so the manager is notified

CONFIDENCE SCORING GUIDELINES:
- 1.0: Perfect match in knowledge base (greetings, exact FAQ answers)
- 0.8-0.9: High confidence, clear answer from knowledge base
- 0.6-0.7: Moderate confidence, answer partially in knowledge base
- Below 0.6: Low confidence - MUST escalate to manager

Always respond in JSON format with the following structure:
{{
  "content": "Your response to the customer IN THEIR LANGUAGE",
  "confidence": 0.0-1.0,
  "intent": "category of the question",
  "escalate": true/false,
  "escalate_reason": "reason if escalate is true (e.g., 'not_in_knowledge_base', 'complex_question', 'need_manager_input')",
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
            
            # Get today's booking count for capacity awareness
            try:
                from apps.restaurant.models import Booking
                today = timezone.now().date()
                todays_bookings = Booking.objects.filter(
                    organization=self.organization,
                    booking_date=today,
                    status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED]
                )
                context['todays_booking_count'] = todays_bookings.count()
                context['todays_confirmed_guests'] = sum(b.party_size for b in todays_bookings)
                logger.info(f"📅 Today's bookings: {context['todays_booking_count']} ({context['todays_confirmed_guests']} guests)")
            except Exception as e:
                logger.warning(f"Error getting today's booking count: {e}")
                context['todays_booking_count'] = 0
                context['todays_confirmed_guests'] = 0
                    
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
        
        # Get today's booking status
        todays_booking_count = context.get('todays_booking_count', 0)
        todays_confirmed_guests = context.get('todays_confirmed_guests', 0)
        
        prompt = f"""
RESTAURANT-SPECIFIC CAPABILITIES:
You can help customers with:
1. Menu questions - answer about dishes, prices, ingredients, dietary options
2. Opening hours - tell customers when the restaurant is open
3. Reservations/Bookings - CREATE new bookings, VIEW existing bookings, CANCEL bookings
4. Daily specials - inform about current promotions
5. Booking management - check reservation status, provide booking details, cancel reservations

📊 TODAY'S BOOKING STATUS:
- Confirmed reservations today: {todays_booking_count}
- Total guests expected: {todays_confirmed_guests}
(Use this info to help manage expectations about availability)

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

    def _get_temporary_override_context(self) -> str:
        """
        Get active temporary overrides from manager messages.
        These take PRIORITY over regular knowledge base.
        """
        try:
            from apps.channels.models import TemporaryOverride
            from django.db import connection
            
            # Force fresh query - no caching
            overrides = TemporaryOverride.get_active_overrides(self.organization)
            
            # Log the query for debugging
            override_count = overrides.count()
            logger.info(f"📋 Override check for {self.organization.name}: found {override_count} active overrides")
            
            if override_count == 0:
                logger.info(f"📋 No active overrides - using normal knowledge base")
                return ""
            
            override_parts = []
            for override in overrides[:5]:  # Limit to 5 most important
                priority_emoji = {
                    'urgent': '🚨',
                    'high': '⚠️',
                    'medium': 'ℹ️',
                    'low': '📌'
                }.get(override.priority, 'ℹ️')
                
                override_text = f"{priority_emoji} {override.override_type.upper()}: {override.processed_content}"
                override_parts.append(override_text)
                
                # Detailed logging for debugging
                logger.info(
                    f"  📌 Override ID={override.id}, type={override.override_type}, "
                    f"active={override.is_active}, expires={override.expires_at}, "
                    f"content='{override.processed_content[:50]}...'"
                )
            
            result = "\n".join(override_parts)
            logger.info(f"📋 Applying {override_count} override(s) to AI context")
            return result
            
        except Exception as e:
            logger.warning(f"Error getting temporary overrides: {e}")
            return ""
    
    def _check_pending_manager_query(self) -> Optional[str]:
        """
        Check if there's a pending or answered manager query for this conversation.
        Returns response text if manager has answered, None otherwise.
        """
        try:
            from apps.channels.models import ManagerQuery
            
            # Check for answered queries that haven't been sent to customer
            answered_query = ManagerQuery.objects.filter(
                conversation=self.conversation,
                status=ManagerQuery.Status.ANSWERED,
                customer_response_sent=False
            ).first()
            
            if answered_query:
                # Return the manager's processed response
                answered_query.customer_response_sent = True
                answered_query.save()
                return answered_query.customer_response or answered_query.manager_response
            
            # Check for expired queries
            expired_query = ManagerQuery.objects.filter(
                conversation=self.conversation,
                status=ManagerQuery.Status.PENDING
            ).first()
            
            if expired_query and expired_query.is_expired:
                expired_query.mark_expired()
                # Return a polite message about manager unavailability
                return (
                    "I apologize for the wait. Unfortunately, I couldn't get a quick response from our team. "
                    f"For this specific question, you may want to contact us directly. "
                    "Is there anything else I can help you with?"
                )
            
            return None
            
        except Exception as e:
            logger.warning(f"Error checking pending manager query: {e}")
            return None
    
    def escalate_to_manager(self, user_message: str) -> Optional[str]:
        """
        Escalate a query to the manager via WhatsApp.
        Returns a "please wait" message if escalation successful, None otherwise.
        """
        try:
            from apps.channels.manager_service import ManagerService
            
            query = ManagerService.escalate_to_manager(
                organization=self.organization,
                conversation=self.conversation,
                customer_query=user_message,
                wait_minutes=5
            )
            
            if query:
                return (
                    "That's a great question! Let me quickly check with my team to get you the most accurate answer. "
                    "Please give me just a moment..."
                )
            
            return None
            
        except Exception as e:
            logger.warning(f"Error escalating to manager: {e}")
            return None

    def _handle_manager_contact_request(self, user_message: str, detected_lang: str) -> Optional[Dict[str, Any]]:
        """
        Detect and handle requests for manager contact information.
        Examples: "Can you give me manager number?", "I want to speak to manager", "Manager contact?"
        
        Also handles location responses when awaiting location for manager contact.
        
        Returns response dict if this is a manager contact request, None otherwise.
        """
        # Check if we're awaiting location for a previous manager contact request
        is_awaiting_location = (
            hasattr(self.conversation, 'customer_metadata') and 
            self.conversation.customer_metadata and
            self.conversation.customer_metadata.get('awaiting_location_for_manager', False)
        )
        
        if is_awaiting_location:
            # User is responding with location - try to match it and provide manager contact
            return self._handle_location_response(user_message, detected_lang)
        
        user_message_lower = user_message.lower()
        
        # Keywords indicating manager contact request
        contact_keywords = [
            'manager number', 'manager phone', 'manager contact',
            'contact manager', 'manager\'s number', 'manager\'s phone',
            'give me manager', 'provide manager', 'manager details',
            'speak to manager', 'talk to manager', 'reach manager',
            '经理电话', '经理号码', '联系经理',  # Simplified Chinese
            '經理電話', '經理號碼', '聯繫經理',  # Traditional Chinese
        ]
        
        is_manager_request = any(keyword in user_message_lower for keyword in contact_keywords)
        
        if not is_manager_request:
            return None
        
        logger.info(f"📞 Manager contact request detected: {user_message[:100]}")
        
        # Check if we have location info for this conversation
        if not self.conversation.location:
            # Ask for location first
            response = self._ask_for_location(detected_lang)
            
            # Store state in conversation metadata to handle next message
            if not hasattr(self.conversation, 'customer_metadata'):
                self.conversation.customer_metadata = {}
            self.conversation.customer_metadata['awaiting_location_for_manager'] = True
            self.conversation.save(update_fields=['customer_metadata'])
            
            return {
                'content': response,
                'confidence': 0.95,
                'intent': 'manager_contact_request_awaiting_location',
                'metadata': {'awaiting': 'location'},
                'needs_handoff': False,
                'handoff_reason': '',
                'language': detected_lang,
            }
        
        # We have location - provide manager contact
        return self._provide_manager_contact(detected_lang)
    
    def _handle_location_response(self, user_message: str, detected_lang: str) -> Dict[str, Any]:
        """
        Handle user's location response when they're asked for location to provide manager contact.
        Try to match the location name with available organization locations.
        """
        from apps.accounts.models import Location
        
        try:
            # Try to find matching location
            locations = Location.objects.filter(organization=self.organization, is_active=True)
            
            matched_location = None
            user_message_lower = user_message.lower()
            
            # Try to find location by name match
            for location in locations:
                if location.name.lower() in user_message_lower or user_message_lower in location.name.lower():
                    matched_location = location
                    logger.info(f"📍 Matched location: {location.name}")
                    break
            
            if matched_location:
                # Update conversation location
                self.conversation.location = matched_location
                self.conversation.save(update_fields=['location'])
                
                # Provide manager contact for this location
                return self._provide_manager_contact(detected_lang)
            else:
                # Couldn't match location - provide list of available locations or general manager
                return self._provide_general_manager_or_locations(locations, detected_lang)
                
        except Exception as e:
            logger.error(f"Error handling location response: {e}")
            # Fall back to providing any available manager
            return self._provide_manager_contact(detected_lang)
    
    def _provide_general_manager_or_locations(self, locations: list, detected_lang: str) -> Dict[str, Any]:
        """
        When location can't be matched, either list available locations or provide a general manager.
        """
        from apps.channels.manager_service import ManagerService
        
        # If there's only one location, use it
        if locations.count() == 1:
            self.conversation.location = locations.first()
            self.conversation.save(update_fields=['location'])
            return self._provide_manager_contact(detected_lang)
        
        # Try to get any available manager (without specific location)
        manager = ManagerService.get_nearest_manager(self.organization, None)
        
        if manager:
            response = self._format_manager_contact_response(
                manager.name,
                manager.phone_number,
                detected_lang
            )
            logger.info(f"📞 Provided general manager contact: {manager.name}")
            
            # Clear awaiting state
            if hasattr(self.conversation, 'customer_metadata') and self.conversation.customer_metadata:
                self.conversation.customer_metadata.pop('awaiting_location_for_manager', None)
                self.conversation.save(update_fields=['customer_metadata'])
            
            return {
                'content': response,
                'confidence': 0.9,
                'intent': 'manager_contact_provided',
                'metadata': {'manager': manager.name},
                'needs_handoff': False,
                'handoff_reason': '',
                'language': detected_lang,
            }
        
        # No manager available - list locations
        location_names = [loc.name for loc in locations[:5]]  # Max 5 locations
        location_list = ", ".join(location_names)
        
        responses = {
            'en': f"I couldn't identify your specific location. We have branches at: {location_list}. Could you please specify which location you're interested in, or I can provide our general contact information?",
            'zh-CN': f'我无法确定您的具体位置。我们在以下地点设有分店：{location_list}。能否请您明确您感兴趣的位置，或者我可以提供我们的一般联系信息？',
            'zh-TW': f'我無法確定您的具體位置。我們在以下地點設有分店：{location_list}。能否請您明確您感興趣的位置，或者我可以提供我們的一般聯絡資訊？',
        }
        
        return {
            'content': responses.get(detected_lang, responses['en']),
            'confidence': 0.85,
            'intent': 'location_clarification_needed',
            'metadata': {'locations': location_names},
            'needs_handoff': False,
            'handoff_reason': '',
            'language': detected_lang,
        }
    
    def _ask_for_location(self, detected_lang: str) -> str:
        """
        Ask customer for their location to provide nearest manager contact.
        """
        responses = {
            'en': "I'd be happy to provide you with our manager's contact information. To connect you with the nearest manager, could you please share your location or which of our branches you're interested in?",
            'zh-CN': '我很乐意为您提供我们经理的联系方式。为了为您联系最近的经理,能否请您分享您的位置或您感兴趣的分店？',
            'zh-TW': '我很樂意為您提供我們經理的聯絡方式。為了為您聯繫最近的經理,能否請您分享您的位置或您感興趣的分店？',
        }
        return responses.get(detected_lang, responses['en'])
    
    def _provide_manager_contact(self, detected_lang: str) -> Dict[str, Any]:
        """
        Provide manager contact information based on conversation location.
        """
        try:
            from apps.channels.manager_service import ManagerService
            
            # Use classmethod to get nearest manager
            manager = ManagerService.get_nearest_manager(
                self.organization, 
                self.conversation.location
            )
            
            if manager:
                response = self._format_manager_contact_response(
                    manager.name, 
                    manager.phone_number, 
                    detected_lang
                )
                logger.info(f"📞 Provided manager contact: {manager.name} - {manager.phone_number}")
            else:
                response = self._no_manager_available_response(detected_lang)
                logger.warning("📞 No manager available for contact request")
            
            # Clear awaiting state
            if hasattr(self.conversation, 'customer_metadata') and self.conversation.customer_metadata:
                self.conversation.customer_metadata.pop('awaiting_location_for_manager', None)
                self.conversation.save(update_fields=['customer_metadata'])
            
            return {
                'content': response,
                'confidence': 0.95,
                'intent': 'manager_contact_provided',
                'metadata': {'manager': manager.name if manager else None},
                'needs_handoff': False,
                'handoff_reason': '',
                'language': detected_lang,
            }
            
        except Exception as e:
            logger.error(f"Error providing manager contact: {e}")
            return {
                'content': self._no_manager_available_response(detected_lang),
                'confidence': 0.8,
                'intent': 'manager_contact_error',
                'metadata': {'error': str(e)},
                'needs_handoff': False,
                'handoff_reason': '',
                'language': detected_lang,
            }
    
    def _format_manager_contact_response(self, manager_name: str, phone: str, detected_lang: str) -> str:
        """
        Format the response with manager contact information.
        """
        responses = {
            'en': f"Certainly! You can contact {manager_name}, our manager, at {phone}. They will be happy to assist you with any questions or concerns. Feel free to call or message them directly.",
            'zh-CN': f'当然！您可以联系我们的经理{manager_name},电话：{phone}。他们很乐意为您解答任何问题或疑虑。请随时致电或直接发送消息。',
            'zh-TW': f'當然！您可以聯繫我們的經理{manager_name},電話：{phone}。他們很樂意為您解答任何問題或疑慮。請隨時致電或直接發送訊息。',
        }
        return responses.get(detected_lang, responses['en'])
    
    def _no_manager_available_response(self, detected_lang: str) -> str:
        """
        Response when no manager is available.
        """
        responses = {
            'en': "I apologize, but I'm currently unable to provide a specific manager contact. Please check our website or contact us through our general support channels, and we'll connect you with the right person.",
            'zh-CN': '抱歉,我目前无法提供特定经理的联系方式。请查看我们的网站或通过我们的一般支持渠道联系我们,我们会为您联系合适的人员。',
            'zh-TW': '抱歉,我目前無法提供特定經理的聯絡方式。請查看我們的網站或通過我們的一般支援渠道聯繫我們,我們會為您聯繫合適的人員。',
        }
        return responses.get(detected_lang, responses['en'])
    
    def _is_query_relevant_to_business(self, user_message: str, parsed_response: Dict[str, Any]) -> bool:
        """
        Check if the query is relevant to the business type (restaurant or real estate).
        This prevents escalating off-topic queries like "how to order nuclear bomb" or "buy electronics".
        
        Returns True if relevant to business, False if off-topic.
        """
        try:
            if not self.client:
                # If no AI client, default to considering it relevant (safe default)
                return True
            
            business_type = self.organization.business_type
            user_message_lower = user_message.lower()
            
            # Quick keyword check for obvious off-topic queries
            off_topic_keywords = [
                'nuclear', 'bomb', 'weapon', 'gun', 'explosive',
                'electronics store', 'buy phone', 'laptop', 'computer store',
                'car dealership', 'buy car', 'automobile',
                'clothing store', 'fashion', 'buy clothes',
                'pharmacy', 'medicine', 'drug store',
                'hardware store', 'tools',
                'toy store', 'game store',
                'illegal', 'drugs', 'narcotics'
            ]
            
            if any(keyword in user_message_lower for keyword in off_topic_keywords):
                logger.info(f"🚫 Detected off-topic query with keywords: {user_message[:100]}")
                return False
            
            # Use AI to check relevance for ambiguous cases
            business_context = {
                'restaurant': 'restaurant, food, dining, menu, booking, reservation, table, dish, cuisine, meal, drink, beverage',
                'real_estate': 'property, house, apartment, real estate, rent, buy, sell, home, listing, viewing, lease, mortgage'
            }
            
            context = business_context.get(business_type, '')
            
            prompt = f"""You are a query relevance checker for a {business_type} business.

Business context: {context}

Customer query: "{user_message}"

Is this query relevant to a {business_type} business?

Respond with JSON:
{{
    "is_relevant": true/false,
    "confidence": 0.0-1.0,
    "reason": "brief explanation"
}}

Consider relevant if:
- Directly about {business_type} services
- General customer service questions
- Location/hours/contact queries
- Greetings and small talk

Consider irrelevant if:
- About completely different industries
- Requesting illegal/inappropriate items
- Shopping for unrelated products/services"""
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            
            import json
            result = json.loads(response.choices[0].message.content)
            is_relevant = result.get('is_relevant', True)  # Default to True if unclear
            reason = result.get('reason', '')
            
            logger.info(f"📊 Relevance check: relevant={is_relevant}, reason={reason}")
            return is_relevant
            
        except Exception as e:
            logger.warning(f"Error checking query relevance: {e}")
            # Default to True (relevant) on error - safe default
            return True
    
    def _get_professional_off_topic_response(self, detected_lang: str) -> str:
        """
        Generate a professional response for off-topic queries.
        Similar to how big companies handle unrelated questions.
        """
        business_type = self.organization.business_type
        business_name = self.organization.name
        
        responses = {
            'en': {
                'restaurant': f"Thank you for reaching out to {business_name}. We specialize in dining experiences and restaurant services. For inquiries unrelated to our restaurant, we recommend contacting the appropriate service provider. How else may I assist you with your dining needs today?",
                'real_estate': f"Thank you for contacting {business_name}. We specialize in real estate services including property sales, rentals, and viewings. For inquiries outside our area of expertise, we recommend reaching out to the relevant service provider. How may I help you with your property needs?"
            },
            'zh-CN': {
                'restaurant': f"感谢您联系{business_name}。我们专注于餐饮体验和餐厅服务。对于与我们餐厅无关的咨询，我们建议您联系相应的服务提供商。我今天还能为您的用餐需求提供什么帮助吗？",
                'real_estate': f"感谢您联系{business_name}。我们专注于房地产服务，包括房产销售、租赁和看房。对于我们专业领域之外的咨询，我们建议您联系相关服务提供商。我可以如何帮助您满足房产需求？"
            },
            'zh-TW': {
                'restaurant': f"感謝您聯絡{business_name}。我們專注於餐飲體驗和餐廳服務。對於與我們餐廳無關的諮詢，我們建議您聯繫相應的服務提供商。我今天還能為您的用餐需求提供什麼幫助嗎？",
                'real_estate': f"感謝您聯絡{business_name}。我們專注於房地產服務，包括房產銷售、租賃和看房。對於我們專業領域之外的諮詢，我們建議您聯繫相關服務提供商。我可以如何幫助您滿足房產需求？"
            }
        }
        
        return responses.get(detected_lang, responses['en']).get(business_type, responses['en']['restaurant'])
    
    def _proactive_escalate_to_manager(
        self, 
        user_message: str, 
        parsed_response: Dict[str, Any],
        detected_lang: str
    ) -> Optional[str]:
        """
        Proactively escalate to manager when AI is unsure.
        This notifies the manager AND informs the customer they're waiting.
        
        ENHANCED: Now checks query relevance before escalating.
        Off-topic queries get professional responses instead of manager escalation.
        
        Returns a message to append to the customer response, or None.
        """
        try:
            from apps.channels.manager_service import ManagerService
            from apps.channels.models import ManagerNumber
            
            # STEP 1: Check if query is relevant to our business
            is_relevant = self._is_query_relevant_to_business(user_message, parsed_response)
            
            if not is_relevant:
                # Off-topic query - respond professionally without manager escalation
                logger.info(f"🚫 Off-topic query detected, responding without escalation: {user_message[:100]}")
                off_topic_response = self._get_professional_off_topic_response(detected_lang)
                
                # Override the parsed response content
                parsed_response['content'] = off_topic_response
                parsed_response['confidence'] = 0.95  # High confidence for off-topic response
                parsed_response['needs_handoff'] = False  # Don't escalate
                parsed_response['intent'] = 'off_topic'
                
                return None  # Don't add waiting message
            
            # STEP 2: Query is relevant - proceed with escalation
            # Check if there's an active manager who can respond
            manager = ManagerNumber.objects.filter(
                organization=self.organization,
                is_active=True,
                can_respond_queries=True
            ).first()
            
            if not manager:
                logger.info(f"No active manager for escalation in {self.organization.name}")
                return None
            
            # Build escalation context
            confidence = parsed_response.get('confidence', 0.5)
            intent = parsed_response.get('intent', 'unknown')
            escalate_reason = parsed_response.get('escalate_reason', 'low_confidence')
            
            # Escalate to manager
            query = ManagerService.escalate_to_manager(
                organization=self.organization,
                conversation=self.conversation,
                customer_query=user_message,
                wait_minutes=5
            )
            
            if query:
                logger.info(f"🆘 Escalated relevant query to manager: confidence={confidence}, reason={escalate_reason}")
                
                # Return language-appropriate waiting message
                waiting_messages = {
                    'en': "\n\n💬 I'm checking with our team to ensure I give you the most accurate answer. Please wait a moment...",
                    'zh-CN': "\n\n💬 我正在与我们的团队核实，以确保给您最准确的答复。请稍等...",
                    'zh-TW': "\n\n💬 我正在與我們的團隊核實，以確保給您最準確的答覆。請稍等..."
                }
                
                return waiting_messages.get(detected_lang, waiting_messages['en'])
            
            return None
            
        except Exception as e:
            logger.warning(f"Error in proactive escalation: {e}")
            return None

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
        """
        Build message history for context.
        CRITICAL FIX: Filters out old closure messages when no override is active
        to prevent AI from hallucinating based on stale conversation context.
        """
        messages = [{"role": "system", "content": self._build_system_prompt()}]

        # Get recent messages
        recent_messages = self.conversation.messages.order_by('-created_at')[:self.MAX_CONTEXT_MESSAGES]
        recent_messages = list(reversed(recent_messages))

        # Check if there are active overrides
        from apps.channels.models import TemporaryOverride
        has_active_override = TemporaryOverride.get_active_overrides(self.organization).exists()

        # Keywords that indicate closure messages
        closure_keywords = [
            'currently closed',
            'we are closed',
            "we're closed",
            'temporarily closed',
            'not open',
            'not accepting',
            'closed today',
            'apologize for any inconvenience',
            'will be open again',
            'during our regular hours'
        ]

        filtered_count = 0
        for msg in recent_messages:
            role = "assistant" if msg.sender in [MessageSender.AI, MessageSender.HUMAN] else "user"
            
            # CRITICAL: If no override is active, filter out old closure messages
            if not has_active_override and role == "assistant":
                # Check if this message contains closure keywords
                msg_lower = msg.content.lower()
                if any(keyword in msg_lower for keyword in closure_keywords):
                    logger.info(f"🔥 Filtering out stale closure message from history: '{msg.content[:100]}...'")
                    filtered_count += 1
                    continue  # Skip this message - don't add to history
            
            # Log what we're adding
            logger.debug(f"📋 Adding to history [{role}]: {msg.content[:80]}...")
            messages.append({"role": role, "content": msg.content})

        # Add current message
        messages.append({"role": "user", "content": current_message})

        logger.info(f"📝 Built message history with {len(messages)} messages (filtered: {filtered_count}, has_override: {has_active_override})")
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
        """
        Create a handoff response in the detected language.
        
        ENHANCED: Uses location-aware manager selection and professional messaging.
        """
        # Try to get enhanced handoff message with manager info
        try:
            from apps.channels.manager_service import ManagerService
            
            location = self.location
            manager = ManagerService.get_nearest_manager(self.organization, location)
            
            if manager:
                # Use enhanced handoff message with manager contact
                enhanced_message = ManagerService.get_enhanced_handoff_message(
                    self.organization,
                    manager,
                    self.detected_language
                )
                message = enhanced_message
                logger.info(f"✨ Using enhanced handoff message with manager {manager.name}")
            
        except Exception as e:
            logger.warning(f"Could not get enhanced handoff message: {e}")
            # Fall back to original message
        
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
