"""
Booking Service - Handles creating bookings from AI extracted data.
Used when customers make reservations through WhatsApp, website widget, etc.
"""
import logging
import re
from datetime import datetime, date, time, timedelta
from typing import Optional, Dict, Any, Tuple

from django.utils import timezone
from django.db.models import Q

from apps.accounts.models import Organization, Location
from apps.messaging.models import Conversation
from .models import Booking

logger = logging.getLogger(__name__)


class BookingService:
    """
    Service for creating bookings from AI-extracted data.
    Handles natural language date/time parsing and validation.
    """
    
    def __init__(self, organization: Organization, conversation: Optional[Conversation] = None):
        self.organization = organization
        self.conversation = conversation
        self.location = self._get_default_location()
    
    def _get_default_location(self) -> Optional[Location]:
        """Get the default/primary location for the organization."""
        # First try to get from conversation
        if self.conversation and self.conversation.location:
            return self.conversation.location
        
        # Get primary location
        location = Location.objects.filter(
            organization=self.organization,
            is_primary=True,
            is_active=True
        ).first()
        
        # Fallback to any active location
        if not location:
            location = Location.objects.filter(
                organization=self.organization,
                is_active=True
            ).first()
        
        return location
    
    def create_booking_from_extracted_data(
        self, 
        extracted_data: Dict[str, Any],
        source: str = 'whatsapp'
    ) -> Tuple[Optional[Booking], str]:
        """
        Create a booking from AI-extracted data.
        
        Args:
            extracted_data: Dictionary containing booking info from AI
            source: Source of the booking (whatsapp, website, etc.)
            
        Returns:
            Tuple of (Booking or None, message)
        """
        if not extracted_data.get('booking_intent'):
            return None, "No booking intent detected"
        
        # For WhatsApp/Instagram, use conversation phone if not provided in extracted_data
        if not extracted_data.get('customer_phone') and self.conversation:
            if self.conversation.customer_phone:
                extracted_data['customer_phone'] = self.conversation.customer_phone
                logger.info(f"Using conversation phone for booking: {self.conversation.customer_phone}")
        
        # Check if we have all required fields
        required_fields = ['date', 'time', 'party_size', 'customer_name', 'customer_phone']
        missing_fields = []
        
        for field in required_fields:
            if not extracted_data.get(field):
                missing_fields.append(field)
        
        if missing_fields:
            logger.info(f"Booking incomplete - missing fields: {missing_fields}")
            return None, f"Missing required fields: {', '.join(missing_fields)}"
        
        try:
            # Parse date
            booking_date = self._parse_date(extracted_data.get('date', ''))
            if not booking_date:
                logger.warning(f"Could not parse date: {extracted_data.get('date')}")
                return None, f"Could not parse date: {extracted_data.get('date')}"
            
            # Parse time
            booking_time = self._parse_time(extracted_data.get('time', ''))
            if not booking_time:
                logger.warning(f"Could not parse time: {extracted_data.get('time')}")
                return None, f"Could not parse time: {extracted_data.get('time')}"
            
            # Get party size
            party_size = int(extracted_data.get('party_size', 2))
            
            # Get customer info
            customer_name = extracted_data.get('customer_name', 'Guest')
            customer_phone = extracted_data.get('customer_phone', '')
            customer_email = extracted_data.get('customer_email', '')
            special_requests = extracted_data.get('special_requests', '')
            
            # Check if we have a location
            if not self.location:
                logger.error(f"No location found for organization {self.organization.name}")
                return None, "No location configured for this restaurant"
            
            # Check for duplicate bookings
            existing_booking = Booking.objects.filter(
                organization=self.organization,
                customer_phone=customer_phone,
                booking_date=booking_date,
                booking_time=booking_time,
                status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED]
            ).first()
            
            if existing_booking:
                logger.info(f"Duplicate booking found: {existing_booking.confirmation_code}")
                return existing_booking, f"Booking already exists: {existing_booking.confirmation_code}"
            
            # Create the booking
            booking = Booking.objects.create(
                organization=self.organization,
                location=self.location,
                conversation=self.conversation,
                booking_date=booking_date,
                booking_time=booking_time,
                party_size=party_size,
                customer_name=customer_name,
                customer_phone=customer_phone,
                customer_email=customer_email,
                special_requests=special_requests,
                source=self._map_source(source),
                status=Booking.Status.PENDING
            )
            
            # Auto-confirm if settings allow
            try:
                settings = self.location.booking_settings
                if settings.auto_confirm:
                    booking.confirm()
                    logger.info(f"Booking auto-confirmed: {booking.confirmation_code}")
            except Exception:
                # No settings, default to auto-confirm
                booking.confirm()
                logger.info(f"Booking auto-confirmed (default): {booking.confirmation_code}")
            
            logger.info(
                f"✅ Booking created: {booking.confirmation_code} - "
                f"{customer_name}, {party_size} guests, {booking_date} at {booking_time}"
            )
            
            return booking, f"Booking created successfully: {booking.confirmation_code}"
            
        except Exception as e:
            logger.exception(f"Error creating booking: {e}")
            return None, f"Error creating booking: {str(e)}"
    
    def _parse_date(self, date_str: str) -> Optional[date]:
        """
        Parse date from various formats including natural language.
        Handles: today, tonight, tomorrow, YYYY-MM-DD, MM/DD/YYYY, etc.
        """
        if not date_str:
            return None
        
        date_str_lower = date_str.lower().strip()
        today = timezone.now().date()
        
        # Natural language dates
        if date_str_lower in ['today', 'tonight', 'now', 'this evening']:
            return today
        
        if date_str_lower in ['tomorrow', 'tmrw', 'tmr']:
            return today + timedelta(days=1)
        
        if date_str_lower in ['day after tomorrow', 'day after tmrw']:
            return today + timedelta(days=2)
        
        # Handle "next [day]" patterns
        day_names = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6,
            'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6
        }
        
        for day_name, weekday in day_names.items():
            if day_name in date_str_lower:
                days_ahead = weekday - today.weekday()
                if days_ahead <= 0:  # Target day already happened this week
                    days_ahead += 7
                return today + timedelta(days=days_ahead)
        
        # Try standard date formats
        date_formats = [
            '%Y-%m-%d',      # 2025-01-12
            '%m/%d/%Y',      # 01/12/2025
            '%d/%m/%Y',      # 12/01/2025
            '%m-%d-%Y',      # 01-12-2025
            '%d-%m-%Y',      # 12-01-2025
            '%B %d, %Y',     # January 12, 2025
            '%B %d %Y',      # January 12 2025
            '%b %d, %Y',     # Jan 12, 2025
            '%b %d %Y',      # Jan 12 2025
            '%d %B %Y',      # 12 January 2025
            '%d %b %Y',      # 12 Jan 2025
        ]
        
        for fmt in date_formats:
            try:
                parsed = datetime.strptime(date_str.strip(), fmt).date()
                return parsed
            except ValueError:
                continue
        
        # Try to extract date from more complex strings like "January 12th" or "12th January"
        month_names = {
            'january': 1, 'february': 2, 'march': 3, 'april': 4,
            'may': 5, 'june': 6, 'july': 7, 'august': 8,
            'september': 9, 'october': 10, 'november': 11, 'december': 12,
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'jun': 6, 'jul': 7,
            'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
        }
        
        # Find day number
        day_match = re.search(r'(\d{1,2})(?:st|nd|rd|th)?', date_str_lower)
        if day_match:
            day = int(day_match.group(1))
            
            # Find month
            for month_name, month_num in month_names.items():
                if month_name in date_str_lower:
                    year = today.year
                    try:
                        parsed_date = date(year, month_num, day)
                        # If date is in the past, assume next year
                        if parsed_date < today:
                            parsed_date = date(year + 1, month_num, day)
                        return parsed_date
                    except ValueError:
                        continue
        
        logger.warning(f"Could not parse date: {date_str}")
        return None
    
    def _parse_time(self, time_str: str) -> Optional[time]:
        """
        Parse time from various formats.
        Handles: HH:MM, H:MM, HH:MM AM/PM, etc.
        """
        if not time_str:
            return None
        
        time_str_lower = time_str.lower().strip()
        
        # Remove common words
        time_str_clean = time_str_lower.replace('at', '').replace('around', '').strip()
        
        # Standard time formats
        time_formats = [
            '%H:%M',        # 14:30
            '%H:%M:%S',     # 14:30:00
            '%I:%M %p',     # 2:30 PM
            '%I:%M%p',      # 2:30PM
            '%I %p',        # 2 PM
            '%I%p',         # 2PM
        ]
        
        for fmt in time_formats:
            try:
                parsed = datetime.strptime(time_str_clean.upper(), fmt).time()
                return parsed
            except ValueError:
                continue
        
        # Try to extract time components manually
        # Match patterns like "12:30", "12:30 pm", "12.30", "1230"
        patterns = [
            r'(\d{1,2})[:\.](\d{2})\s*(am|pm|a\.m\.|p\.m\.)?',  # 12:30 pm
            r'(\d{1,2})\s*(am|pm|a\.m\.|p\.m\.)',               # 2 pm
            r'(\d{3,4})',                                       # 1230
        ]
        
        for pattern in patterns:
            match = re.search(pattern, time_str_lower)
            if match:
                groups = match.groups()
                
                if len(groups) >= 2 and groups[1] and groups[1].isdigit():
                    # Pattern like 12:30
                    hour = int(groups[0])
                    minute = int(groups[1])
                    meridiem = groups[2] if len(groups) > 2 else None
                elif len(groups) >= 2 and groups[1]:
                    # Pattern like 2 pm
                    hour = int(groups[0])
                    minute = 0
                    meridiem = groups[1]
                elif len(groups) == 1 and len(groups[0]) >= 3:
                    # Pattern like 1230
                    time_num = groups[0]
                    if len(time_num) == 3:
                        hour = int(time_num[0])
                        minute = int(time_num[1:3])
                    else:
                        hour = int(time_num[0:2])
                        minute = int(time_num[2:4])
                    meridiem = None
                else:
                    continue
                
                # Handle AM/PM
                if meridiem:
                    meridiem = meridiem.replace('.', '').strip()
                    if meridiem in ['pm', 'p'] and hour < 12:
                        hour += 12
                    elif meridiem in ['am', 'a'] and hour == 12:
                        hour = 0
                
                # Validate hour and minute
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    return time(hour, minute)
        
        logger.warning(f"Could not parse time: {time_str}")
        return None
    
    def _map_source(self, source: str) -> str:
        """Map source string to Booking.Source choice."""
        source_map = {
            'whatsapp': Booking.Source.WHATSAPP,
            'website': Booking.Source.WEBSITE,
            'widget': Booking.Source.WEBSITE,
            'instagram': Booking.Source.OTHER,  # Instagram uses OTHER since there's no dedicated source
            'phone': Booking.Source.PHONE,
            'walk_in': Booking.Source.WALK_IN,
        }
        return source_map.get(source.lower(), Booking.Source.OTHER)


def process_booking_from_ai_response(
    organization: Organization,
    conversation: Optional[Conversation],
    ai_response: Dict[str, Any],
    source: str = 'whatsapp'
) -> Optional[Booking]:
    """
    Convenience function to process booking from AI response.
    Called from WhatsApp service, widget service, etc.
    
    Args:
        organization: The organization
        conversation: The conversation (optional)
        ai_response: The full AI response dict containing extracted_data
        source: Source of the booking
        
    Returns:
        Booking object if created, None otherwise
    """
    extracted_data = ai_response.get('extracted_data', {})
    
    # Check if this is a booking intent with complete data
    if not extracted_data.get('booking_intent'):
        return None
    
    # Check if we have all required fields for booking
    required_fields = ['date', 'time', 'party_size', 'customer_name', 'customer_phone']
    for field in required_fields:
        if not extracted_data.get(field):
            logger.debug(f"Booking incomplete - missing {field}")
            return None
    
    service = BookingService(organization, conversation)
    booking, message = service.create_booking_from_extracted_data(extracted_data, source)
    
    if booking:
        logger.info(f"✅ Booking processed: {message}")
    else:
        logger.info(f"Booking not created: {message}")
    
    return booking
