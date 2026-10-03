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
from . import vocab

logger = logging.getLogger(__name__)

VIEWING_START = time(10, 0)
VIEWING_END = time(19, 0)
MAX_DAYS_AHEAD = 90
SEARCH_LIMIT = 5
GENERIC_ANYWHERE = {'anywhere', 'any', 'all', 'everywhere', 'all areas', 'any area', 'kahi pani', 'jaha pani', 'जहाँ पनि'}

# Per-market conventions, chosen from the org's primary location country. Data-driven so
# a Nepal agency, a Hong Kong agency and anyone else each get the right money/time/words.
MARKETS = {
    'nepal': {
        'name': 'Nepal', 'tz': 'Asia/Kathmandu', 'currency': 'Rs', 'lakh_crore': True,
        'territory': {'nepal', 'whole nepal', 'all nepal', 'नेपाल', 'nepal bhari', 'sabai thau'},
    },
    'hong kong': {
        'name': 'Hong Kong', 'tz': 'Asia/Hong_Kong', 'currency': 'HK$', 'lakh_crore': False,
        'territory': {'hong kong', 'hongkong', 'hk', 'h.k.', '香港', '全港'},
    },
    'india': {
        'name': 'India', 'tz': 'Asia/Kolkata', 'currency': '₹', 'lakh_crore': True,
        'territory': {'india', 'all india', 'bharat'},
    },
    'usa': {
        'name': 'USA', 'tz': 'America/New_York', 'currency': '$', 'lakh_crore': False,
        'territory': {'usa', 'us', 'united states', 'america'},
    },
}
# Same aliases the dashboard accepts (frontend/src/lib/money.ts).
MARKET_ALIASES = {'united states': 'usa', 'us': 'usa', 'u.s.': 'usa', 'hk': 'hong kong', 'np': 'nepal'}
DEFAULT_MARKET = {'name': '', 'tz': 'UTC', 'currency': '$', 'lakh_crore': False, 'territory': set()}


def market_for(organization) -> Dict[str, Any]:
    from apps.accounts.models import Location

    loc = (Location.objects.filter(organization=organization, is_active=True)
           .order_by('-is_primary').values('country', 'timezone').first()) or {}
    country = (loc.get('country') or '').strip().lower()
    country = MARKET_ALIASES.get(country, country)
    market = dict(MARKETS.get(country, DEFAULT_MARKET))
    tz = loc.get('timezone') or ''
    # The location's own zone wins — unless it is the untouched model default
    # (America/New_York) on a market we know, e.g. a Nepal branch never edited.
    if tz and (country not in MARKETS or tz != 'America/New_York'):
        try:
            ZoneInfo(tz)
            market['tz'] = tz
        except Exception:
            logger.warning("Invalid timezone %r on location for org %s", tz, organization)
    return market


def _group_lakh(n: int) -> str:
    """18500000 -> '1,85,00,000' (South Asian digit grouping)."""
    s = str(abs(n))
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ','.join(parts + [tail])


def format_money(value, market: Dict[str, Any]) -> str:
    amount = int(value) if value == int(value) else float(value)
    cur = market['currency']
    if market.get('lakh_crore') and isinstance(amount, int):
        text = f"{cur} {_group_lakh(amount)}"
        if amount >= 10_000_000:
            text += f" ({amount / 10_000_000:g} crore)"
        elif amount >= 100_000:
            text += f" ({amount / 100_000:g} lakh)"
        return text
    return f"{cur}{amount:,}" if isinstance(amount, int) else f"{cur}{amount:,.2f}"


def _listing_summary(p: PropertyListing, market: Dict[str, Any]) -> Dict[str, Any]:
    price = format_money(p.price, market)
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
        'province': p.state,
        'bedrooms': p.bedrooms,
        'bathrooms': float(p.bathrooms) if p.bathrooms is not None else None,
        'size_sqft': p.square_feet,
        'land_size_sqft': p.lot_size,
        'highlights': (p.features or [])[:5],
    }


class RealEstateTools:
    def __init__(self, conversation):
        self.conversation = conversation
        self.organization = conversation.organization
        self.market = market_for(self.organization)
        self.tz = ZoneInfo(self.market['tz'])
        self.actions: List[Dict[str, Any]] = []   # successful side-effects this turn
        self.escalation: Dict[str, Any] = {}

    # ------------------------------------------------------------------ read
    def _active_listings(self):
        return PropertyListing.objects.filter(
            organization=self.organization, status=PropertyListing.Status.ACTIVE, is_published=True,
        )

    def _filtered(self, c: Dict[str, Any]):
        qs = self._active_listings()
        if c.get('listing_type') == 'rent':
            qs = qs.filter(listing_type__in=['rent', 'lease'])
        elif c.get('listing_type') == 'sale':
            qs = qs.filter(listing_type='sale')
        if c.get('property_type'):
            qs = qs.filter(property_type=c['property_type'])
        if c.get('area'):
            a = c['area']
            qs = qs.filter(Q(city__icontains=a) | Q(neighborhood__icontains=a) | Q(address_line1__icontains=a)
                           | Q(title__icontains=a) | Q(state__icontains=a))
        if c.get('min_price'):
            qs = qs.filter(price__gte=Decimal(str(c['min_price'])))
        if c.get('max_price'):
            qs = qs.filter(price__lte=Decimal(str(c['max_price'])))
        if c.get('min_bedrooms'):
            qs = qs.filter(bedrooms__gte=int(c['min_bedrooms']))
        if c.get('words'):
            # ANY word may match (OR): "attached bathroom wifi" should not need all three.
            any_word = Q()
            for w in c['words'][:6]:
                any_word |= (Q(title__icontains=w) | Q(description__icontains=w) | Q(neighborhood__icontains=w)
                             | Q(features__icontains=w) | Q(amenities__icontains=w))
            qs = qs.filter(any_word)
        return qs

    def search_properties(self, listing_type: str = '', property_type: str = '', area: str = '',
                          min_price: float = None, max_price: float = None,
                          min_bedrooms: int = None, keywords: str = '', sort: str = 'best_match') -> Dict[str, Any]:
        valid_types = {c for c, _ in PropertyListing.PropertyType.choices}
        words, kw_type, kw_listing = vocab.split_keywords(keywords)
        # "jagga" / "kotha" / "ghar" may arrive in any field — map them to the real enums.
        ptype = vocab.normalize_property_type(property_type, valid_types) or kw_type
        if property_type and not ptype:
            words += vocab.tokens(property_type)  # unknown type word: search it as text instead
        ltype = vocab.normalize_listing_type(listing_type) or kw_listing
        area = vocab.normalize_area(area)
        if area.lower() in GENERIC_ANYWHERE | self.market['territory']:
            area = ''  # "anywhere in Nepal" is not a district filter
        criteria = {'listing_type': ltype, 'property_type': ptype, 'area': area, 'min_price': min_price,
                    'max_price': max_price, 'min_bedrooms': min_bedrooms, 'words': words}

        # Relaxation ladder: never answer "nothing" while the agency has something close.
        # Least important criteria are dropped first; the type the customer asked for goes last.
        relaxed: List[str] = []
        qs = self._filtered(criteria)
        for key in ('words', 'min_bedrooms', 'min_price', 'max_price', 'area', 'listing_type', 'property_type'):
            if qs.exists():
                break
            if criteria.get(key):
                criteria[key] = None
                relaxed.append(key)
                qs = self._filtered(criteria)

        total = qs.count()
        ordering = {'price_asc': ('price',), 'price_desc': ('-price',), 'newest': ('-created_at',)}.get(
            sort, ('-is_featured', 'price'))
        results = [_listing_summary(p, self.market) for p in qs.order_by(*ordering)[:SEARCH_LIMIT]]
        asked = ', '.join(str(v) for v in (ltype, ptype, area,
                          f"min {min_bedrooms} bed" if min_bedrooms else '',
                          f"max {format_money(max_price, self.market)}" if max_price else '', ' '.join(words)) if v)
        if asked:
            self._remember(f"Searched for: {asked}")
        out = {'ok': True, 'exact_match': not relaxed, 'total_matches': total, 'results': results,
               'interpreted_as': {'listing_type': ltype or 'any', 'property_type': ptype or 'any',
                                  'area': area or 'anywhere'}}
        if relaxed:
            out['relaxed_criteria'] = relaxed
            out['note'] = ('Nothing matched every criterion. These are the CLOSEST real listings after dropping: '
                           + ', '.join(relaxed) + '. Say so honestly (e.g. "nothing in X under your budget, '
                           'closest is ...") — never present them as exact matches.')
        if not results:
            out['available_districts'] = sorted(set(self._active_listings().values_list('city', flat=True)))
            out['note'] = 'The agency has no active listings at all right now. Offer to save their requirement.'
        return out

    def get_portfolio_overview(self) -> Dict[str, Any]:
        """What the agency offers, grouped — for "what do you have?" / "land kaha kaha cha?"."""
        groups: Dict[str, Dict[str, Any]] = {}
        for p in self._active_listings().order_by('price'):
            key = f"{p.get_property_type_display()} for {'rent' if p.listing_type in ('rent', 'lease') else 'sale'}"
            g = groups.setdefault(key, {'count': 0, 'districts': set(), 'prices': []})
            g['count'] += 1
            g['districts'].add(p.city)
            g['prices'].append(p.price)
        overview = []
        for key, g in sorted(groups.items(), key=lambda kv: -kv[1]['count']):
            lo, hi = min(g['prices']), max(g['prices'])
            rng = format_money(lo, self.market) if lo == hi else \
                f"{format_money(lo, self.market)} – {format_money(hi, self.market)}"
            overview.append({'category': key, 'listings': g['count'], 'districts': sorted(g['districts']),
                             'price_range': rng})
        return {'ok': True, 'total_active_listings': sum(g['count'] for g in groups.values()),
                'categories': overview}

    def get_property_details(self, reference: str) -> Dict[str, Any]:
        p = self._active_listings().filter(reference_number__iexact=(reference or '').strip()).first()
        if not p:
            return {'ok': False, 'error': f'No active listing with reference {reference!r}.'}
        data = _listing_summary(p, self.market)
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
            appointment_date__gte=self.now().date(),
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
            bits.append(f"budget up to {format_money(lead.budget_max, self.market)}")
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
        now = self.now()
        if datetime.combine(d, t, self.tz) < now + timedelta(hours=1):
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
    def now(self) -> datetime:
        return datetime.now(self.tz)

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
            'get_portfolio_overview': self.get_portfolio_overview,
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
    _fn('search_properties', 'Search this agency\'s ACTIVE listings. Call before recommending or quoting any property. '
        'Never returns empty while the agency has stock: if nothing matches exactly it returns the closest '
        'listings with exact_match=false and relaxed_criteria.', {
        'listing_type': {'type': 'string', 'enum': ['sale', 'rent']},
        'property_type': {'type': 'string', 'enum': [c for c, _ in PropertyListing.PropertyType.choices],
                          'description': 'jagga/plot/ropani/aana = land · kotha = room · flat/BHK = apartment · '
                                         'ghar = house · shutter/pasal = retail'},
        'area': {'type': 'string', 'description': 'City, area or tole, e.g. "Baneshwor", "Lalitpur", "Pokhara Lakeside"'},
        'min_price': {'type': 'number', 'description': 'Plain number in local currency (monthly rent for rentals). 1 lakh = 100000, 1 crore = 10000000'},
        'max_price': {'type': 'number', 'description': 'Plain number in local currency (monthly rent for rentals). 1 lakh = 100000, 1 crore = 10000000'},
        'min_bedrooms': {'type': 'integer'},
        'keywords': {'type': 'string', 'description': 'e.g. "sea view pet"'},
        'sort': {'type': 'string', 'enum': ['best_match', 'price_asc', 'price_desc', 'newest'],
                 'description': 'Use price_asc for "cheap/affordable/student/budget" requests instead of inventing a max_price'},
    }),
    _fn('get_portfolio_overview', 'Everything this agency offers right now, grouped by type with districts and '
        'price ranges. Use for broad questions: "what do you have?", "jagga kaha kaha cha?", "which areas?".', {}),
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
