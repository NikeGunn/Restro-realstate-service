"""
Real-estate agent tools.

Every fact the agent states about listings and every action it claims must
come through one of these functions. Each returns a JSON-serialisable dict
with ``ok`` so the model (and the verification gate) can tell success from
failure. Tools are tenant-scoped by the conversation — the model can never
pass an organization id.
"""
import logging
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Callable, Dict, List
from zoneinfo import ZoneInfo

from django.db.models import Q

from apps.realestate.models import Appointment, Lead, PropertyListing

from . import memory as agent_memory

logger = logging.getLogger(__name__)

HK_TZ = ZoneInfo('Asia/Hong_Kong')
VIEWING_START = time(10, 0)
VIEWING_END = time(19, 0)
MAX_DAYS_AHEAD = 90
SEARCH_LIMIT = 5
WHOLE_TERRITORY = {'hong kong', 'hongkong', 'hk', 'h.k.', '香港', '全港', 'anywhere', 'any', 'all', 'everywhere', 'all areas'}


def hk_now() -> datetime:
    return datetime.now(HK_TZ)


def _money(value) -> str:
    return f"{int(value):,}" if value == int(value) else f"{value:,.2f}"


def _listing_summary(p: PropertyListing) -> Dict[str, Any]:
    price = f"HK${_money(p.price)}"
    if p.listing_type in ('rent', 'lease'):
        price += f"/{p.rent_period or 'month'}".replace('monthly', 'month')
    return {
        'reference': p.reference_number,
        'title': p.title,
        'listing_type': p.get_listing_type_display(),
        'property_type': p.get_property_type_display(),
        'price': price,
        'area': p.neighborhood or p.city,
        'district': p.city,
        'bedrooms': p.bedrooms,
        'bathrooms': float(p.bathrooms) if p.bathrooms is not None else None,
        'size_sqft': p.square_feet,
        'highlights': (p.features or [])[:4],
    }


class RealEstateTools:
    def __init__(self, conversation):
        self.conversation = conversation
        self.organization = conversation.organization
        self.actions: List[Dict[str, Any]] = []   # successful side-effects this turn
        self.escalation: Dict[str, Any] = {}

    # ------------------------------------------------------------------ read
    def _active_listings(self):
        return PropertyListing.objects.filter(
            organization=self.organization, status=PropertyListing.Status.ACTIVE, is_published=True,
        )

    def search_properties(self, listing_type: str = '', property_type: str = '', area: str = '',
                          min_price: float = None, max_price: float = None,
                          min_bedrooms: int = None, keywords: str = '', sort: str = 'best_match') -> Dict[str, Any]:
        qs = self._active_listings()
        lt = (listing_type or '').lower()
        if lt in ('rent', 'lease'):
            qs = qs.filter(listing_type__in=['rent', 'lease'])
        elif lt in ('sale', 'buy'):
            qs = qs.filter(listing_type='sale')
        if property_type:
            qs = qs.filter(property_type=property_type.lower())
        area = (area or '').strip()
        if area.lower() in WHOLE_TERRITORY:
            area = ''  # "anywhere in Hong Kong" is not a district filter
        if area:
            qs = qs.filter(Q(city__icontains=area) | Q(neighborhood__icontains=area)
                           | Q(address_line1__icontains=area) | Q(title__icontains=area)
                           | Q(state__icontains=area))
        if min_price:
            qs = qs.filter(price__gte=Decimal(str(min_price)))
        if max_price:
            qs = qs.filter(price__lte=Decimal(str(max_price)))
        if min_bedrooms:
            qs = qs.filter(bedrooms__gte=int(min_bedrooms))
        if keywords:
            for word in keywords.split()[:4]:
                qs = qs.filter(Q(title__icontains=word) | Q(description__icontains=word))
        total = qs.count()
        ordering = {'price_asc': ('price',), 'price_desc': ('-price',), 'newest': ('-created_at',)}.get(
            sort, ('-is_featured', 'price'))
        results = [_listing_summary(p) for p in qs.order_by(*ordering)[:SEARCH_LIMIT]]
        criteria = ', '.join(str(v) for v in (listing_type, property_type, area,
                             f"min {min_bedrooms} bed" if min_bedrooms else '',
                             f"max HK${int(max_price):,}" if max_price else '', keywords) if v)
        if criteria:
            self._remember(f"Searched for: {criteria}")
        out = {'ok': True, 'total_matches': total, 'results': results}
        if not results:
            out['available_districts'] = sorted(set(self._active_listings().values_list('city', flat=True)))
            out['note'] = 'No listing matches these criteria. Do not invent one; offer alternatives from a wider search.'
        return out

    def get_property_details(self, reference: str) -> Dict[str, Any]:
        p = self._active_listings().filter(reference_number__iexact=(reference or '').strip()).first()
        if not p:
            return {'ok': False, 'error': f'No active listing with reference {reference!r}.'}
        data = _listing_summary(p)
        data.update({
            'description': p.description,
            'address': f"{p.address_line1}, {p.neighborhood or p.city}",
            'year_built': p.year_built,
            'parking_spaces': p.parking_spaces,
            'features': p.features,
            'amenities': p.amenities,
            'virtual_tour_available': True,
        })
        return {'ok': True, 'property': data}

    def get_my_appointments(self) -> Dict[str, Any]:
        phone = self._phone('')
        if not phone:
            return {'ok': False, 'error': 'Customer phone unknown — ask for the phone number used to book.'}
        appts = Appointment.objects.filter(
            organization=self.organization, lead__phone=phone,
            status__in=[Appointment.Status.SCHEDULED, Appointment.Status.CONFIRMED],
            appointment_date__gte=hk_now().date(),
        ).select_related('property_listing').order_by('appointment_date', 'appointment_time')[:5]
        return {'ok': True, 'appointments': [self._appt(a) for a in appts]}

    # ----------------------------------------------------------------- write
    def save_lead(self, intent: str, name: str = '', phone: str = '', email: str = '',
                  budget_min: float = None, budget_max: float = None, areas: List[str] = None,
                  property_type: str = '', bedrooms: int = None, timeline: str = '',
                  property_reference: str = '', notes: str = '') -> Dict[str, Any]:
        from apps.realestate.lead_service import LeadService

        phone = self._phone(phone)
        name = (name or self.conversation.customer_name or '').strip()
        if not phone:
            return {'ok': False, 'error': 'Need the customer phone number to save the lead.'}
        if not name or name.lower() in ('whatsapp user', 'customer', 'guest'):
            return {'ok': False, 'error': "Need the customer's name to save the lead."}
        data = {
            'lead_intent': intent or 'general', 'customer_name': name, 'customer_phone': phone,
            'customer_email': email, 'budget_min': budget_min, 'budget_max': budget_max,
            'preferred_areas': areas or [], 'property_type': property_type, 'bedrooms': bedrooms,
            'timeline': timeline, 'property_reference': property_reference, 'notes': notes,
        }
        data = {k: v for k, v in data.items() if v not in (None, '', [])}
        lead, message = LeadService(self.organization, self.conversation).create_lead_from_extracted_data(
            data, source=self._source(),
        )
        if not lead:
            return {'ok': False, 'error': message}
        self.actions.append({'tool': 'save_lead', 'lead_id': str(lead.id)})
        bits = [f"Wants to {lead.intent}"]
        if lead.budget_max:
            bits.append(f"budget up to HK${int(lead.budget_max):,}")
        if lead.preferred_areas:
            bits.append("areas: " + ", ".join(lead.preferred_areas))
        if lead.timeline:
            bits.append(f"timeline: {lead.timeline}")
        self._remember("; ".join(bits), display_name=name)
        return {'ok': True, 'lead_id': str(lead.id), 'lead_score': lead.lead_score, 'priority': lead.priority}

    def book_viewing(self, date: str, time: str, weekday: str = '', name: str = '', phone: str = '',
                     property_reference: str = '', appointment_type: str = 'viewing',
                     notes: str = '') -> Dict[str, Any]:
        from apps.realestate.lead_service import AppointmentService

        phone = self._phone(phone)
        name = (name or self.conversation.customer_name or '').strip()
        if not phone:
            return {'ok': False, 'error': 'Need the customer phone number to book.'}
        if not name or name.lower() in ('whatsapp user', 'customer', 'guest'):
            return {'ok': False, 'error': "Need the customer's name to book."}
        try:
            d = datetime.strptime(date.strip(), '%Y-%m-%d').date()
            t = datetime.strptime(time.strip()[:5], '%H:%M').time()
        except (ValueError, AttributeError):
            return {'ok': False, 'error': 'date must be YYYY-MM-DD and time HH:MM (24h).'}
        if weekday and weekday.strip().lower()[:3] != d.strftime('%a').lower():
            return {'ok': False, 'error': f'{d.isoformat()} is a {d:%A}, not {weekday}. Re-check the CALENDAR and pass the correct date.'}
        now = hk_now()
        if datetime.combine(d, t, HK_TZ) < now + timedelta(hours=1):
            return {'ok': False, 'error': f'That time is in the past or under 1 hour away (now {now:%Y-%m-%d %H:%M}). Ask for a later slot.'}
        if d > now.date() + timedelta(days=MAX_DAYS_AHEAD):
            return {'ok': False, 'error': f'We book up to {MAX_DAYS_AHEAD} days ahead.'}
        if not (VIEWING_START <= t <= VIEWING_END):
            return {'ok': False, 'error': 'Viewings run 10:00-19:00. Ask for a time in that window.'}

        listing = None
        if property_reference:
            listing = self._active_listings().filter(reference_number__iexact=property_reference.strip()).first()
            if not listing:
                return {'ok': False, 'error': f'No active listing {property_reference!r}. Search again.'}
            clash = Appointment.objects.filter(
                organization=self.organization, property_listing=listing, appointment_date=d,
                appointment_time=t,
                status__in=[Appointment.Status.SCHEDULED, Appointment.Status.CONFIRMED],
            ).exclude(lead__phone=phone).exists()
            if clash:
                return {'ok': False, 'error': 'That slot is already taken for this property. Offer 1 hour earlier or later.'}

        data = {
            'appointment_intent': True, 'appointment_date': d.isoformat(), 'appointment_time': t.strftime('%H:%M'),
            'appointment_type': appointment_type or 'viewing', 'customer_name': name, 'customer_phone': phone,
            'property_reference': listing.reference_number if listing else '', 'notes': notes,
        }
        appt, message = AppointmentService(self.organization, self.conversation).create_appointment_from_extracted_data(
            data, source=self._source(),
        )
        if not appt:
            return {'ok': False, 'error': message}
        self.actions.append({'tool': 'book_viewing', 'confirmation_code': appt.confirmation_code})
        self._remember(f"Booked {appt.get_appointment_type_display().lower()} {appt.confirmation_code} for "
                       f"{appt.property_listing.title if appt.property_listing else 'a consultation'} on "
                       f"{appt.appointment_date:%a %Y-%m-%d} {appt.appointment_time:%H:%M}", display_name=name)
        return {'ok': True, 'appointment': self._appt(appt)}

    def cancel_appointment(self, confirmation_code: str, reason: str = '') -> Dict[str, Any]:
        phone = self._phone('')
        appt = Appointment.objects.filter(
            organization=self.organization, confirmation_code__iexact=(confirmation_code or '').strip(),
            status__in=[Appointment.Status.SCHEDULED, Appointment.Status.CONFIRMED],
        ).select_related('lead').first()
        if not appt or (phone and appt.lead.phone != phone):
            return {'ok': False, 'error': 'No active appointment with that code for this customer.'}
        appt.cancel(reason=reason or 'Cancelled by customer via chat')
        self.actions.append({'tool': 'cancel_appointment', 'confirmation_code': appt.confirmation_code})
        self._remember(f"Cancelled appointment {appt.confirmation_code}")
        return {'ok': True, 'cancelled': appt.confirmation_code}

    def remember_customer_fact(self, fact: str) -> Dict[str, Any]:
        try:
            agent_memory.remember(self.organization, 'customer', agent_memory.customer_key(self.conversation), fact)
        except ValueError as e:
            return {'ok': False, 'error': str(e)}
        return {'ok': True}

    def escalate_to_human(self, reason: str) -> Dict[str, Any]:
        self.escalation = {'reason': (reason or 'customer_request')[:200]}
        return {'ok': True, 'note': 'A human agent has been notified. Tell the customer an agent will reply shortly.'}

    # --------------------------------------------------------------- helpers
    def _remember(self, fact: str, display_name: str = ''):
        try:
            agent_memory.remember(self.organization, 'customer', agent_memory.customer_key(self.conversation),
                                  fact, display_name=display_name)
        except Exception:
            logger.exception("Could not write customer memory")

    def _phone(self, given: str) -> str:
        raw = (self.conversation.customer_phone or given or '').strip()
        digits = ''.join(ch for ch in raw if ch.isdigit())
        return digits if len(digits) >= 7 else ''

    def _source(self) -> str:
        return str(self.conversation.channel or 'website')

    @staticmethod
    def _appt(a: Appointment) -> Dict[str, Any]:
        return {
            'confirmation_code': a.confirmation_code,
            'date': a.appointment_date.isoformat(),
            'weekday': a.appointment_date.strftime('%A'),
            'time': a.appointment_time.strftime('%H:%M'),
            'type': a.get_appointment_type_display(),
            'property': a.property_listing.title if a.property_listing else None,
            'property_reference': a.property_listing.reference_number if a.property_listing else None,
            'status': a.status,
        }

    def registry(self) -> Dict[str, Callable[..., Dict[str, Any]]]:
        return {
            'search_properties': self.search_properties,
            'get_property_details': self.get_property_details,
            'get_my_appointments': self.get_my_appointments,
            'save_lead': self.save_lead,
            'book_viewing': self.book_viewing,
            'cancel_appointment': self.cancel_appointment,
            'remember_customer_fact': self.remember_customer_fact,
            'escalate_to_human': self.escalate_to_human,
        }


def _fn(name, description, properties, required=()):
    return {'type': 'function', 'function': {
        'name': name, 'description': description,
        'parameters': {'type': 'object', 'properties': properties, 'required': list(required)},
    }}


TOOL_SCHEMAS = [
    _fn('search_properties', 'Search this agency\'s ACTIVE listings. Call before recommending or quoting any property.', {
        'listing_type': {'type': 'string', 'enum': ['sale', 'rent']},
        'property_type': {'type': 'string', 'enum': [c for c, _ in PropertyListing.PropertyType.choices]},
        'area': {'type': 'string', 'description': 'District or neighbourhood, e.g. "Wan Chai"'},
        'min_price': {'type': 'number', 'description': 'HKD (monthly rent for rentals)'},
        'max_price': {'type': 'number', 'description': 'HKD (monthly rent for rentals)'},
        'min_bedrooms': {'type': 'integer'},
        'keywords': {'type': 'string', 'description': 'e.g. "sea view pet"'},
        'sort': {'type': 'string', 'enum': ['best_match', 'price_asc', 'price_desc', 'newest'],
                 'description': 'Use price_asc for "cheap/affordable/student/budget" requests instead of inventing a max_price'},
    }),
    _fn('get_property_details', 'Full details of one listing by reference code (e.g. PROP123456).',
        {'reference': {'type': 'string'}}, ['reference']),
    _fn('get_my_appointments', 'List this customer\'s upcoming viewings/appointments.', {}),
    _fn('save_lead', 'Create or update this customer\'s lead record. Call when you know intent + name; call again as details arrive.', {
        'intent': {'type': 'string', 'enum': ['buy', 'rent', 'sell', 'invest', 'general']},
        'name': {'type': 'string'}, 'phone': {'type': 'string', 'description': 'Only if not on WhatsApp'},
        'email': {'type': 'string'}, 'budget_min': {'type': 'number'}, 'budget_max': {'type': 'number'},
        'areas': {'type': 'array', 'items': {'type': 'string'}}, 'property_type': {'type': 'string'},
        'bedrooms': {'type': 'integer'}, 'timeline': {'type': 'string'},
        'property_reference': {'type': 'string'}, 'notes': {'type': 'string'},
    }, ['intent']),
    _fn('book_viewing', 'Book a property viewing / consultation. Only claim it is booked if this returns ok=true. In the same turn also call save_lead with everything known (intent, budget, areas).', {
        'date': {'type': 'string', 'description': 'YYYY-MM-DD (resolve relative dates against today)'},
        'time': {'type': 'string', 'description': 'HH:MM 24h, between 10:00 and 19:00'},
        'weekday': {'type': 'string', 'description': 'Weekday of that date from the CALENDAR, e.g. "Saturday" — must match'},
        'name': {'type': 'string'}, 'phone': {'type': 'string', 'description': 'Only if not on WhatsApp'},
        'property_reference': {'type': 'string'},
        'appointment_type': {'type': 'string', 'enum': ['viewing', 'virtual_tour', 'consultation']},
        'notes': {'type': 'string'},
    }, ['date', 'time', 'weekday']),
    _fn('cancel_appointment', 'Cancel one of this customer\'s appointments by confirmation code.',
        {'confirmation_code': {'type': 'string'}, 'reason': {'type': 'string'}}, ['confirmation_code']),
    _fn('remember_customer_fact', 'Persist a durable fact/preference about this customer for future conversations.',
        {'fact': {'type': 'string', 'description': 'Short third-person fact, e.g. "Has a dog; needs pet-friendly"'}}, ['fact']),
    _fn('escalate_to_human', 'Hand the conversation to a human agent (explicit request, complaint, price negotiation, legal/tax advice, repeated tool failure).',
        {'reason': {'type': 'string'}}, ['reason']),
]
