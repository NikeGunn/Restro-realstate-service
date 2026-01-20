"""
Lead & Appointment Service - Handles creating leads and appointments from AI extracted data.
Used when customers interact through WhatsApp, website widget, Instagram, etc.
"""
import logging
import re
from datetime import datetime, date, time, timedelta
from typing import Optional, Dict, Any, Tuple
from decimal import Decimal

from django.utils import timezone
from django.db.models import Q

from apps.accounts.models import Organization, Location
from apps.messaging.models import Conversation
from .models import Lead, Appointment, PropertyListing

logger = logging.getLogger(__name__)


class LeadService:
    """
    Service for creating leads from AI-extracted data.
    Handles lead qualification and scoring.
    """
    
    def __init__(self, organization: Organization, conversation: Optional[Conversation] = None):
        self.organization = organization
        self.conversation = conversation
        self.location = self._get_default_location()
    
    def _get_default_location(self) -> Optional[Location]:
        """Get the default/primary location for the organization."""
        if self.conversation and self.conversation.location:
            return self.conversation.location
        
        location = Location.objects.filter(
            organization=self.organization,
            is_primary=True,
            is_active=True
        ).first()
        
        if not location:
            location = Location.objects.filter(
                organization=self.organization,
                is_active=True
            ).first()
        
        return location
    
    def create_lead_from_extracted_data(
        self, 
        extracted_data: Dict[str, Any],
        source: str = 'whatsapp'
    ) -> Tuple[Optional[Lead], str]:
        """
        Create a lead from AI-extracted data.
        
        CRITICAL: Checks for active override status (closed/unavailable) before accepting leads.
        This prevents lead acceptance when the office/agency is marked as closed.
        
        Args:
            extracted_data: Dictionary containing lead info from AI
            source: Source of the lead (whatsapp, website, instagram, etc.)
            
        Returns:
            Tuple of (Lead or None, message)
        """
        if not extracted_data.get('lead_intent'):
            return None, "No lead intent detected"
        
        # CRITICAL: Check for active closure/unavailability overrides BEFORE accepting lead
        from apps.channels.models import TemporaryOverride
        
        active_overrides = TemporaryOverride.get_active_overrides(
            self.organization,
            override_type=TemporaryOverride.OverrideType.HOURS
        )
        
        if active_overrides.exists():
            override = active_overrides.first()
            
            # CRITICAL: Check for OPEN keywords FIRST
            open_keywords = ['open', 'opening', 'reopening', 'back', 'available', 'accepting', 'now open']
            is_open_message = any(
                keyword in override.processed_content.lower() or 
                keyword in override.original_message.lower()
                for keyword in open_keywords
            )
            
            # If override says "we are OPEN", don't block leads
            if is_open_message:
                logger.info(f"✅ Override indicates OPEN status - allowing leads: {override.processed_content[:50]}")
                # Don't block - continue with lead
            else:
                # Check for closure keywords
                closure_keywords = ['closed', 'closing', 'not open', 'unavailable', 'not accepting', 'office closed']
                is_closed = any(
                    keyword in override.processed_content.lower() or 
                    keyword in override.original_message.lower()
                    for keyword in closure_keywords
                )
                
                if is_closed:
                    logger.warning(
                        f"🚫 Blocking lead attempt - office is CLOSED. "
                        f"Override: {override.processed_content[:100]}"
                    )
                    return None, f"Cannot accept leads: {override.processed_content}"
        
        # Also check availability overrides
        availability_overrides = TemporaryOverride.get_active_overrides(
            self.organization,
            override_type=TemporaryOverride.OverrideType.AVAILABILITY
        )
        
        if availability_overrides.exists():
            logger.warning(
                f"🚫 Blocking lead - availability override active: "
                f"{availability_overrides.first().processed_content[:100]}"
            )
            return None, f"Cannot accept leads: {availability_overrides.first().processed_content}"
        
        # Check if we have minimum required fields (name and phone)
        customer_name = extracted_data.get('customer_name', '')
        customer_phone = extracted_data.get('customer_phone', '')
        
        if not customer_name or not customer_phone:
            logger.info(f"Lead incomplete - missing name or phone")
            return None, "Missing required fields: name and phone"
        
        try:
            # Parse intent
            intent = self._parse_intent(extracted_data.get('lead_intent', 'general'))
            
            # Parse budget
            budget_min, budget_max = self._parse_budget(extracted_data)
            
            # Get preferred areas
            preferred_areas = extracted_data.get('preferred_areas', [])
            if isinstance(preferred_areas, str):
                preferred_areas = [area.strip() for area in preferred_areas.split(',')]
            
            # Get property type preferences
            property_type = extracted_data.get('property_type', '')
            preferred_property_types = []
            if property_type:
                if isinstance(property_type, list):
                    preferred_property_types = property_type
                else:
                    preferred_property_types = [property_type]
            
            # Get bedrooms
            bedrooms = extracted_data.get('bedrooms')
            bedrooms_min = None
            bedrooms_max = None
            if bedrooms:
                if isinstance(bedrooms, int):
                    bedrooms_min = bedrooms
                elif isinstance(bedrooms, str):
                    try:
                        bedrooms_min = int(bedrooms.replace('+', ''))
                    except ValueError:
                        pass
            
            # Get timeline
            timeline = extracted_data.get('timeline', '')
            
            # Get email if provided
            customer_email = extracted_data.get('customer_email', '')
            
            # Check for duplicate leads (same phone, same org, recent)
            recent_cutoff = timezone.now() - timedelta(hours=24)
            existing_lead = Lead.objects.filter(
                organization=self.organization,
                phone=customer_phone,
                created_at__gte=recent_cutoff
            ).first()
            
            if existing_lead:
                # Update existing lead with new info if available
                updated = self._update_existing_lead(existing_lead, extracted_data)
                if updated:
                    logger.info(f"Updated existing lead: {existing_lead.id}")
                    return existing_lead, f"Lead updated: {existing_lead.name}"
                return existing_lead, f"Lead already exists: {existing_lead.name}"
            
            # Find matching property if mentioned
            property_listing = self._find_matching_property(extracted_data)
            
            # Create the lead
            lead = Lead.objects.create(
                organization=self.organization,
                location=self.location,
                conversation=self.conversation,
                property_listing=property_listing,
                name=customer_name,
                email=customer_email,
                phone=customer_phone,
                intent=intent,
                source=self._map_source(source),
                budget_min=budget_min,
                budget_max=budget_max,
                preferred_areas=preferred_areas,
                preferred_property_types=preferred_property_types,
                bedrooms_min=bedrooms_min,
                bedrooms_max=bedrooms_max,
                timeline=timeline,
                qualification_data=extracted_data,
                notes=f"Lead captured via {source} chat"
            )
            
            # Calculate lead score
            lead.calculate_score()
            
            logger.info(
                f"✅ Lead created: {lead.id} - "
                f"{customer_name}, Intent: {intent}, "
                f"Budget: {budget_min}-{budget_max}, Score: {lead.lead_score}"
            )
            
            return lead, f"Lead created successfully for {customer_name}"
            
        except Exception as e:
            logger.exception(f"Error creating lead: {e}")
            return None, f"Error creating lead: {str(e)}"
    
    def _update_existing_lead(self, lead: Lead, extracted_data: Dict[str, Any]) -> bool:
        """Update existing lead with new extracted data."""
        updated = False
        
        # Update budget if not set
        if not lead.budget_min and not lead.budget_max:
            budget_min, budget_max = self._parse_budget(extracted_data)
            if budget_min or budget_max:
                lead.budget_min = budget_min
                lead.budget_max = budget_max
                updated = True
        
        # Update preferred areas if not set
        if not lead.preferred_areas:
            areas = extracted_data.get('preferred_areas', [])
            if areas:
                if isinstance(areas, str):
                    areas = [a.strip() for a in areas.split(',')]
                lead.preferred_areas = areas
                updated = True
        
        # Update timeline if not set
        if not lead.timeline and extracted_data.get('timeline'):
            lead.timeline = extracted_data['timeline']
            updated = True
        
        # Update email if not set
        if not lead.email and extracted_data.get('customer_email'):
            lead.email = extracted_data['customer_email']
            updated = True
        
        if updated:
            # Merge qualification data
            lead.qualification_data.update(extracted_data)
            lead.save()
            lead.calculate_score()
        
        return updated
    
    def _parse_intent(self, intent_str: str) -> str:
        """Parse intent string to Lead.IntentType."""
        intent_lower = intent_str.lower()
        
        if 'buy' in intent_lower or 'purchase' in intent_lower:
            return Lead.IntentType.BUY
        elif 'rent' in intent_lower or 'lease' in intent_lower:
            return Lead.IntentType.RENT
        elif 'sell' in intent_lower:
            return Lead.IntentType.SELL
        elif 'invest' in intent_lower:
            return Lead.IntentType.INVEST
        else:
            return Lead.IntentType.GENERAL
    
    def _parse_budget(self, extracted_data: Dict[str, Any]) -> Tuple[Optional[Decimal], Optional[Decimal]]:
        """Parse budget from extracted data."""
        budget_min = extracted_data.get('budget_min')
        budget_max = extracted_data.get('budget_max')
        
        # Handle single budget value
        budget = extracted_data.get('budget')
        if budget and not budget_max:
            budget_max = budget
        
        # Convert to Decimal
        try:
            if budget_min:
                if isinstance(budget_min, str):
                    # Remove currency symbols and commas
                    budget_min = re.sub(r'[^\d.]', '', budget_min)
                budget_min = Decimal(str(budget_min))
        except:
            budget_min = None
        
        try:
            if budget_max:
                if isinstance(budget_max, str):
                    budget_max = re.sub(r'[^\d.]', '', budget_max)
                budget_max = Decimal(str(budget_max))
        except:
            budget_max = None
        
        return budget_min, budget_max
    
    def _find_matching_property(self, extracted_data: Dict[str, Any]) -> Optional[PropertyListing]:
        """Find a matching property based on extracted data."""
        property_ref = extracted_data.get('property_reference')
        property_id = extracted_data.get('property_id')
        property_title = extracted_data.get('property_title')
        
        if property_id:
            try:
                return PropertyListing.objects.get(
                    id=property_id,
                    organization=self.organization
                )
            except PropertyListing.DoesNotExist:
                pass
        
        if property_ref:
            try:
                return PropertyListing.objects.get(
                    reference_number__iexact=property_ref,
                    organization=self.organization
                )
            except PropertyListing.DoesNotExist:
                pass
        
        if property_title:
            prop = PropertyListing.objects.filter(
                organization=self.organization,
                title__icontains=property_title,
                status=PropertyListing.Status.ACTIVE
            ).first()
            if prop:
                return prop
        
        return None
    
    def _map_source(self, source: str) -> str:
        """Map source string to Lead.Source choice."""
        source_map = {
            'whatsapp': Lead.Source.WHATSAPP,
            'website': Lead.Source.WEBSITE,
            'widget': Lead.Source.WEBSITE,
            'instagram': Lead.Source.OTHER,
            'phone': Lead.Source.PHONE,
            'email': Lead.Source.EMAIL,
            'referral': Lead.Source.REFERRAL,
            'walk_in': Lead.Source.WALK_IN,
        }
        return source_map.get(source.lower(), Lead.Source.OTHER)


class AppointmentService:
    """
    Service for creating appointments from AI-extracted data.
    """
    
    def __init__(self, organization: Organization, conversation: Optional[Conversation] = None):
        self.organization = organization
        self.conversation = conversation
        self.location = self._get_default_location()
    
    def _get_default_location(self) -> Optional[Location]:
        """Get the default/primary location for the organization."""
        if self.conversation and self.conversation.location:
            return self.conversation.location
        
        return Location.objects.filter(
            organization=self.organization,
            is_primary=True,
            is_active=True
        ).first()
    
    def create_appointment_from_extracted_data(
        self,
        extracted_data: Dict[str, Any],
        lead: Optional[Lead] = None,
        source: str = 'whatsapp'
    ) -> Tuple[Optional[Appointment], str]:
        """
        Create an appointment from AI-extracted data.
        
        CRITICAL: Checks for active override status (closed/unavailable) before creating appointments.
        This prevents appointment confirmations when the office/agency is marked as closed.
        
        Args:
            extracted_data: Dictionary containing appointment info from AI
            lead: Optional existing lead (if not provided, will try to find/create one)
            source: Source of the appointment
            
        Returns:
            Tuple of (Appointment or None, message)
        """
        if not extracted_data.get('appointment_intent'):
            return None, "No appointment intent detected"
        
        # CRITICAL: Check for active closure/unavailability overrides BEFORE accepting appointment
        from apps.channels.models import TemporaryOverride
        
        active_overrides = TemporaryOverride.get_active_overrides(
            self.organization,
            override_type=TemporaryOverride.OverrideType.HOURS
        )
        
        if active_overrides.exists():
            override = active_overrides.first()
            
            # CRITICAL: Check for OPEN keywords FIRST
            open_keywords = ['open', 'opening', 'reopening', 'back', 'available', 'accepting', 'now open']
            is_open_message = any(
                keyword in override.processed_content.lower() or 
                keyword in override.original_message.lower()
                for keyword in open_keywords
            )
            
            # If override says "we are OPEN", don't block appointments
            if is_open_message:
                logger.info(f"✅ Override indicates OPEN status - allowing appointments: {override.processed_content[:50]}")
                # Don't block - continue with appointment
            else:
                # Check for closure keywords
                closure_keywords = ['closed', 'closing', 'not open', 'unavailable', 'not accepting', 'office closed']
                is_closed = any(
                    keyword in override.processed_content.lower() or 
                    keyword in override.original_message.lower()
                    for keyword in closure_keywords
                )
                
                if is_closed:
                    logger.warning(
                        f"🚫 Blocking appointment attempt - office is CLOSED. "
                        f"Override: {override.processed_content[:100]}"
                    )
                    return None, f"Cannot schedule appointments: {override.processed_content}"
        
        # Also check availability overrides
        availability_overrides = TemporaryOverride.get_active_overrides(
            self.organization,
            override_type=TemporaryOverride.OverrideType.AVAILABILITY
        )
        
        if availability_overrides.exists():
            logger.warning(
                f"🚫 Blocking appointment - availability override active: "
                f"{availability_overrides.first().processed_content[:100]}"
            )
            return None, f"Cannot schedule appointments: {availability_overrides.first().processed_content}"
        
        # Check required fields
        appointment_date = extracted_data.get('appointment_date')
        appointment_time = extracted_data.get('appointment_time')
        
        if not appointment_date or not appointment_time:
            logger.info(f"Appointment incomplete - missing date or time")
            return None, "Missing required fields: date and time"
        
        try:
            # Parse date
            parsed_date = self._parse_date(appointment_date)
            if not parsed_date:
                return None, f"Could not parse date: {appointment_date}"
            
            # Parse time
            parsed_time = self._parse_time(appointment_time)
            if not parsed_time:
                return None, f"Could not parse time: {appointment_time}"
            
            # Get or create lead
            if not lead:
                customer_name = extracted_data.get('customer_name', 'Customer')
                customer_phone = extracted_data.get('customer_phone', '')
                
                if not customer_phone:
                    return None, "Missing customer phone for appointment"
                
                # Try to find existing lead
                lead = Lead.objects.filter(
                    organization=self.organization,
                    phone=customer_phone
                ).order_by('-created_at').first()
                
                # Create lead if not found
                if not lead:
                    lead = Lead.objects.create(
                        organization=self.organization,
                        location=self.location,
                        conversation=self.conversation,
                        name=customer_name,
                        phone=customer_phone,
                        email=extracted_data.get('customer_email', ''),
                        intent=Lead.IntentType.GENERAL,
                        source=self._map_source(source)
                    )
                    lead.calculate_score()
            
            # Find property if mentioned
            property_listing = self._find_property(extracted_data)
            
            # Determine appointment type
            appointment_type = self._parse_appointment_type(extracted_data)
            
            # Check for duplicate appointment
            existing = Appointment.objects.filter(
                organization=self.organization,
                lead=lead,
                appointment_date=parsed_date,
                appointment_time=parsed_time,
                status__in=[Appointment.Status.SCHEDULED, Appointment.Status.CONFIRMED]
            ).first()
            
            if existing:
                return existing, f"Appointment already exists: {existing.confirmation_code}"
            
            # Create the appointment
            appointment = Appointment.objects.create(
                organization=self.organization,
                location=self.location,
                lead=lead,
                property_listing=property_listing,
                conversation=self.conversation,
                appointment_type=appointment_type,
                appointment_date=parsed_date,
                appointment_time=parsed_time,
                duration_minutes=extracted_data.get('duration', 60),
                notes=extracted_data.get('notes', ''),
                status=Appointment.Status.SCHEDULED
            )
            
            # Auto-confirm
            appointment.confirm()
            
            logger.info(
                f"✅ Appointment created: {appointment.confirmation_code} - "
                f"Lead: {lead.name}, Date: {parsed_date} at {parsed_time}, "
                f"Type: {appointment_type}"
            )
            
            return appointment, f"Appointment created: {appointment.confirmation_code}"
            
        except Exception as e:
            logger.exception(f"Error creating appointment: {e}")
            return None, f"Error creating appointment: {str(e)}"
    
    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse date from various formats."""
        if not date_str:
            return None
        
        date_str_lower = date_str.lower().strip()
        today = timezone.now().date()
        
        # Natural language dates
        if date_str_lower in ['today', 'now']:
            return today
        if date_str_lower in ['tomorrow', 'tmrw', 'tmr']:
            return today + timedelta(days=1)
        
        # Day names
        day_names = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6,
        }
        
        for day_name, weekday in day_names.items():
            if day_name in date_str_lower:
                days_ahead = weekday - today.weekday()
                if days_ahead <= 0:
                    days_ahead += 7
                return today + timedelta(days=days_ahead)
        
        # Standard formats
        date_formats = ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%B %d, %Y', '%b %d, %Y']
        for fmt in date_formats:
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except ValueError:
                continue
        
        return None
    
    def _parse_time(self, time_str: str) -> Optional[time]:
        """Parse time from various formats."""
        if not time_str:
            return None
        
        time_str_clean = time_str.lower().strip().replace('at', '').strip()
        
        time_formats = ['%H:%M', '%I:%M %p', '%I:%M%p', '%I %p', '%I%p']
        
        for fmt in time_formats:
            try:
                return datetime.strptime(time_str_clean.upper(), fmt).time()
            except ValueError:
                continue
        
        # Try regex extraction
        match = re.search(r'(\d{1,2})[:\.]?(\d{2})?\s*(am|pm|a\.m\.|p\.m\.)?', time_str_clean, re.I)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2) or 0)
            meridiem = match.group(3)
            
            if meridiem:
                meridiem = meridiem.replace('.', '').lower()
                if meridiem == 'pm' and hour < 12:
                    hour += 12
                elif meridiem == 'am' and hour == 12:
                    hour = 0
            
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return time(hour, minute)
        
        return None
    
    def _parse_appointment_type(self, extracted_data: Dict[str, Any]) -> str:
        """Parse appointment type from extracted data."""
        apt_type = extracted_data.get('appointment_type', '').lower()
        
        if 'viewing' in apt_type or 'tour' in apt_type or 'visit' in apt_type:
            return Appointment.AppointmentType.VIEWING
        elif 'virtual' in apt_type:
            return Appointment.AppointmentType.VIRTUAL_TOUR
        elif 'consult' in apt_type:
            return Appointment.AppointmentType.CONSULTATION
        elif 'follow' in apt_type:
            return Appointment.AppointmentType.FOLLOW_UP
        elif 'meet' in apt_type:
            return Appointment.AppointmentType.MEETING
        
        # Default to viewing for property-related appointments
        if extracted_data.get('property_id') or extracted_data.get('property_reference'):
            return Appointment.AppointmentType.VIEWING
        
        return Appointment.AppointmentType.CONSULTATION
    
    def _find_property(self, extracted_data: Dict[str, Any]) -> Optional[PropertyListing]:
        """Find property based on extracted data."""
        property_id = extracted_data.get('property_id')
        property_ref = extracted_data.get('property_reference')
        
        if property_id:
            try:
                return PropertyListing.objects.get(id=property_id, organization=self.organization)
            except PropertyListing.DoesNotExist:
                pass
        
        if property_ref:
            try:
                return PropertyListing.objects.get(
                    reference_number__iexact=property_ref,
                    organization=self.organization
                )
            except PropertyListing.DoesNotExist:
                pass
        
        return None
    
    def _map_source(self, source: str) -> str:
        """Map source string to Lead.Source choice."""
        source_map = {
            'whatsapp': Lead.Source.WHATSAPP,
            'website': Lead.Source.WEBSITE,
            'instagram': Lead.Source.OTHER,
        }
        return source_map.get(source.lower(), Lead.Source.OTHER)


def process_realestate_from_ai_response(
    organization: Organization,
    conversation: Optional[Conversation],
    ai_response: Dict[str, Any],
    source: str = 'whatsapp'
) -> Dict[str, Any]:
    """
    Process real estate data from AI response.
    Creates leads and/or appointments as needed.
    
    Args:
        organization: The organization
        conversation: The conversation (optional)
        ai_response: The full AI response dict containing extracted_data
        source: Source of the interaction
        
    Returns:
        Dict with created lead and/or appointment info
    """
    result = {
        'lead': None,
        'appointment': None,
        'messages': []
    }
    
    extracted_data = ai_response.get('extracted_data', {})
    
    if not extracted_data:
        return result
    
    # Process lead if lead_intent is present
    if extracted_data.get('lead_intent'):
        lead_service = LeadService(organization, conversation)
        lead, message = lead_service.create_lead_from_extracted_data(extracted_data, source)
        result['lead'] = lead
        result['messages'].append(message)
        
        if lead:
            logger.info(f"✅ Lead processed: {message}")
    
    # Process appointment if appointment_intent is present
    if extracted_data.get('appointment_intent'):
        appointment_service = AppointmentService(organization, conversation)
        appointment, message = appointment_service.create_appointment_from_extracted_data(
            extracted_data, 
            lead=result.get('lead'),
            source=source
        )
        result['appointment'] = appointment
        result['messages'].append(message)
        
        if appointment:
            logger.info(f"✅ Appointment processed: {message}")
    
    return result
