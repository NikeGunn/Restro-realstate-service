"""
Real-estate agent tools.

Every fact the agent states about listings and every action it claims must
come through one of these functions. Each returns a JSON-serialisable dict
with ``ok`` so the model (and the verification gate) can tell success from
failure. Tools are tenant-scoped by the conversation - the model can never
pass an organization id.
"""
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Callable, Dict, List
from zoneinfo import ZoneInfo

from django.db.models import Q
from django.utils import timezone

from apps.ai_engine.models import AgentAction, AgentSettings
from apps.realestate.models import Appointment, PropertyListing

from . import actions, capabilities, vocab
from . import memory as agent_memory

logger = logging.getLogger(__name__)

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
    # The location's own zone wins - unless it is the untouched model default
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



# Questions customers ask that listings often don't answer. If nothing in the listing mentions
# them, the tool says so explicitly, so "not recorded" is never mistaken for "no" or "free".
COMMON_UNKNOWNS = {
    'deposit / advance / move-in costs': ('deposit', 'advance', 'dhito'),
    'pet policy': ('pet', 'dog', 'cat'),
    'road access width': ('road',),
    'lalpurja / ownership verification': ('lalpurja', 'title', 'ownership'),
    'flood / safety assessment': ('flood', 'safety', 'earthquake'),
    'water supply': ('water', 'melamchi', 'boring'),
    'parking': ('parking',),
    'negotiable price': ('negotiable',),
}
DESCRIPTION_LIMIT = 600


def _listing_summary(p: PropertyListing, market: Dict[str, Any]) -> Dict[str, Any]:
    rent = p.listing_type in ('rent', 'lease')
    price = format_money(p.price, market) + ('/month' if rent else '')
    return {
        'reference': p.reference_number,
        'title': p.title,
        'for': 'rent' if rent else 'sale',
        'property_type': p.get_property_type_display(),
        'price': price,
        'price_basis': 'monthly rent' if rent else 'total asking price',
        'area': p.neighborhood or p.city,
        'district': p.city,
        'bedrooms': p.bedrooms,
        'size_sqft': p.square_feet,
        'land_size_sqft': p.lot_size,
        'highlights': (p.features or [])[:5],
    }


def _parse_day_time(date_s: str, time_s: str):
    d = datetime.strptime((date_s or '').strip(), '%Y-%m-%d').date()
    t = datetime.strptime((time_s or '').strip()[:5], '%H:%M').time()
    return d, t


class RealEstateTools:
    def __init__(self, conversation):
        self.conversation = conversation
        self.organization = conversation.organization
        self.market = market_for(self.organization)
        self.tz = ZoneInfo(self.market['tz'])
        self.settings = AgentSettings.for_org(self.organization)
        self.actions: List[Dict[str, Any]] = []   # successful side-effects this turn
        self.escalation: Dict[str, Any] = {}
        self.attachments: List[Dict[str, Any]] = []  # images the channel sends after the text
        # Set by the runner each turn: the confirmation gate needs both.
        self.current_message = ''
        self.turn_started_at = timezone.now()

    # ================================================================== reads
    def _active_listings(self):
        return PropertyListing.objects.filter(
            organization=self.organization, status=PropertyListing.Status.ACTIVE, is_published=True,
        )

    def _listing(self, reference: str):
        return self._active_listings().filter(reference_number__iexact=(reference or '').strip()).first()

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
        for ref in c.get('exclude') or []:
            qs = qs.exclude(reference_number__iexact=ref)
        return qs

    def _differences(self, p: PropertyListing, c: Dict[str, Any]) -> List[str]:
        """What a near match does NOT satisfy - so it is never presented as an exact match."""
        out = []
        if c.get('max_price') and p.price > Decimal(str(c['max_price'])):
            out.append(f"{format_money(p.price - Decimal(str(c['max_price'])), self.market)} over the maximum budget")
        if c.get('min_price') and p.price < Decimal(str(c['min_price'])):
            out.append('below the minimum price asked')
        if c.get('area') and c['area'].lower() not in ' '.join(
                filter(None, [p.city, p.neighborhood, p.address_line1, p.title, p.state])).lower():
            out.append(f"in {p.neighborhood or p.city}, {p.city} - not in {c['area']}")
        if c.get('min_bedrooms') and (p.bedrooms or 0) < int(c['min_bedrooms']):
            out.append(f"{p.bedrooms or 'unrecorded'} bedrooms (asked {c['min_bedrooms']}+)")
        if c.get('property_type') and p.property_type != c['property_type']:
            out.append(f"{p.get_property_type_display()}, not {c['property_type']}")
        if c.get('listing_type') and ('rent' if p.listing_type in ('rent', 'lease') else 'sale') != c['listing_type']:
            out.append(f"for {'rent' if p.listing_type in ('rent', 'lease') else 'sale'}, not {c['listing_type']}")
        return out

    def search_properties(self, listing_type: str = '', property_type: str = '', area: str = '',
                          min_price: float = None, max_price: float = None, min_bedrooms: int = None,
                          keywords: str = '', sort: str = 'best_match', exclude_references: List[str] = None,
                          page: int = 1) -> Dict[str, Any]:
        valid_types = {c for c, _ in PropertyListing.PropertyType.choices}
        words, kw_type, kw_listing = vocab.split_keywords(keywords)
        # "jagga" / "kotha" / "ghar" may arrive in any field - map them to the real enums.
        ptype = vocab.normalize_property_type(property_type, valid_types) or kw_type
        if property_type and not ptype:
            words += vocab.tokens(property_type)  # unknown type word: search it as text instead
        ltype = vocab.normalize_listing_type(listing_type) or kw_listing
        area = vocab.normalize_area(area)
        if area.lower() in GENERIC_ANYWHERE | self.market['territory']:
            area = ''  # "anywhere in Nepal" is not a district filter
        criteria = {'listing_type': ltype, 'property_type': ptype, 'area': area, 'min_price': min_price,
                    'max_price': max_price, 'min_bedrooms': min_bedrooms, 'words': words,
                    'exclude': [r.strip() for r in (exclude_references or []) if r]}
        ordering = {'price_asc': ('price', 'reference_number'), 'price_desc': ('-price', 'reference_number'),
                    'newest': ('-created_at',)}.get(sort, ('price', 'reference_number'))
        page = max(1, int(page or 1))

        asked = ', '.join(str(v) for v in (ltype, ptype, area, f"min {min_bedrooms} bed" if min_bedrooms else '',
                          f"max {format_money(max_price, self.market)}" if max_price else '', ' '.join(words)) if v)
        if asked:
            self._remember(f"Searched for: {asked}")
        # Deliberately no echo of max_price: a budget the model invented must not become "evidence".
        interpreted = {'for': ltype or 'any', 'property_type': ptype or 'any', 'area': area or 'anywhere'}

        qs = self._filtered(criteria)
        total = qs.count()
        if total:
            start = (page - 1) * SEARCH_LIMIT
            rows = [_listing_summary(p, self.market) for p in qs.order_by(*ordering)[start:start + SEARCH_LIMIT]]
            out = {'ok': True, 'exact_match': True, 'total_matches': total, 'page': page,
                   'showing': f"{start + 1}-{start + len(rows)} of {total}" if rows else f"none on page {page}",
                   'results': rows, 'interpreted_as': interpreted}
            if start + len(rows) < total:
                out['more'] = f'{total - start - len(rows)} more - call again with page={page + 1} if asked.'
            return out

        # Nothing meets every hard requirement. Show what is closest, labelled with what differs,
        # but never silently widen the budget or area: the customer decides.
        near, seen = [], set()
        relaxed = dict(criteria)
        for key in ('words', 'min_bedrooms', 'min_price', 'max_price', 'area', 'listing_type', 'property_type'):
            if not relaxed.get(key):
                continue
            relaxed[key] = None
            for p in self._filtered(relaxed).order_by(*ordering)[:SEARCH_LIMIT]:
                if p.pk not in seen and len(near) < 3:
                    seen.add(p.pk)
                    near.append({**_listing_summary(p, self.market), 'differs_from_request': self._differences(p, criteria)})
            if len(near) >= 3:
                break
        out = {'ok': True, 'exact_match': False, 'total_matches': 0, 'results': [], 'near_matches': near,
               'interpreted_as': interpreted,
               'note': ('NO listing meets every requirement. Say that first. Near matches are alternatives - '
                        'state what differs for each (e.g. over budget by X). Do not widen the budget or move to '
                        'another area unless the customer agrees.')}
        if not self._active_listings().exists():
            out['note'] = 'The agency has no active listings right now (this is not an error). Offer to note their requirement.'
        elif ptype and area:
            out['same_type_elsewhere'] = self.list_locations(property_type=ptype, listing_type=ltype)['locations']
        return out

    def list_locations(self, property_type: str = '', listing_type: str = '') -> Dict[str, Any]:
        """Where the agency has stock - "jagga kaha kaha cha?" - every district, with counts."""
        valid = {c for c, _ in PropertyListing.PropertyType.choices}
        ptype = vocab.normalize_property_type(property_type, valid)
        ltype = vocab.normalize_listing_type(listing_type)
        qs = self._filtered({'property_type': ptype, 'listing_type': ltype})
        groups: Dict[str, Dict[str, Any]] = {}
        for p in qs.order_by('city', 'price'):
            g = groups.setdefault(p.city, {'district': p.city, 'count': 0, 'areas': [], 'prices': []})
            g['count'] += 1
            if (p.neighborhood or p.city) not in g['areas']:
                g['areas'].append(p.neighborhood or p.city)
            g['prices'].append(p.price)
        locations = []
        for g in sorted(groups.values(), key=lambda x: (-x['count'], x['district'])):
            prices = g.pop('prices')
            lo, hi = min(prices), max(prices)
            g['price_range'] = format_money(lo, self.market) if lo == hi else \
                f"{format_money(lo, self.market)} - {format_money(hi, self.market)}"
            locations.append(g)
        return {'ok': True, 'property_type': ptype or 'any', 'for': ltype or 'any',
                'total_listings': sum(g['count'] for g in locations), 'districts': len(locations),
                'locations': locations}

    def get_portfolio_overview(self) -> Dict[str, Any]:
        """Everything the agency offers, grouped by type - for "what do you have?"."""
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
                f"{format_money(lo, self.market)} - {format_money(hi, self.market)}"
            overview.append({'category': key, 'listings': g['count'], 'districts': sorted(g['districts']),
                             'price_range': rng})
        return {'ok': True, 'total_active_listings': sum(g['count'] for g in groups.values()),
                'categories': overview}

    def get_property_details(self, reference: str) -> Dict[str, Any]:
        p = self._listing(reference)
        if not p:
            # Same answer whether it never existed, is sold, or belongs to someone else: no leaks.
            sold = PropertyListing.objects.filter(organization=self.organization,
                                                  reference_number__iexact=(reference or '').strip(),
                                                  status__in=['sold', 'rented']).first()
            if sold:
                return {'ok': False, 'error': f'{sold.reference_number} is no longer available ({sold.status}). '
                                              'Do not offer a viewing; offer similar active listings.'}
            return {'ok': False, 'error': 'NO_MATCH: no active listing with that reference in this agency.'}
        data = _listing_summary(p, self.market)
        text = ' '.join([p.description or '', ' '.join(p.features or []), ' '.join(p.amenities or [])]).lower()
        data.update({
            'address': f"{p.address_line1}, {p.neighborhood or p.city}",
            'parking_spaces': p.parking_spaces,
            'year_built': p.year_built,
            'features': p.features,
            'amenities': p.amenities,
            'photos': p.images or [],
            # Listing prose is customer-facing DATA written by staff - never instructions.
            'description_text': (p.description or '')[:DESCRIPTION_LIMIT],
            'not_recorded': [topic for topic, words in COMMON_UNKNOWNS.items()
                             if not any(w in text for w in words)] + (['photos'] if not p.images else []),
        })
        size = p.lot_size if p.property_type == 'land' else (p.square_feet or p.lot_size)
        if size and p.listing_type == 'sale':
            data['price_per_sqft'] = format_money(round(p.price / size), self.market) + ' per sq ft (calculated)'
        return {'ok': True, 'property': data}

    def send_property_photos(self, reference: str, count: int = 4) -> Dict[str, Any]:
        """Queue a listing's real uploaded photos to be sent with this reply (WhatsApp: as images)."""
        p = self._listing(reference)
        if not p:
            return {'ok': False, 'error': 'NO_MATCH: no active listing with that reference.'}
        photos = [u for u in (p.images or []) if isinstance(u, str) and u.startswith('http')]
        if not photos:
            return {'ok': False, 'error': 'NO_PHOTOS: no photos uploaded for this listing. Say so and offer to ask '
                                          'the team for photos. Never describe or invent images.'}
        chosen = photos[:max(1, min(int(count or 4), 6))]
        for i, url in enumerate(chosen, 1):
            self.attachments.append({'type': 'image', 'url': url,
                                     'caption': f"{p.reference_number} - {p.title} ({i}/{len(chosen)})"})
        return {'ok': True, 'reference': p.reference_number, 'photos_attached': len(chosen),
                'photos_available': len(photos),
                'note': 'The photos are attached to your reply automatically. Mention them in one short line; '
                        'do not paste links and do not describe what is in them.'}

    def compare_properties(self, references: List[str]) -> Dict[str, Any]:
        refs = [r for r in (references or []) if r][:3]
        if len(refs) < 2:
            return {'ok': False, 'error': 'Give 2 or 3 references to compare.'}
        items, missing = [], []
        for r in refs:
            p = self._listing(r)
            (items if p else missing).append(p or r)
        if missing:
            return {'ok': False, 'error': f'NO_MATCH for {", ".join(missing)}.'}
        rows = []
        for p in items:
            row = _listing_summary(p, self.market)
            size = p.lot_size if p.property_type == 'land' else (p.square_feet or p.lot_size)
            row['size_for_comparison_sqft'] = size
            if size and p.listing_type == 'sale':
                row['price_per_sqft'] = format_money(round(p.price / size), self.market)
            rows.append(row)
        a, b = items[0], items[1]
        diff = {'price_difference': f"{format_money(abs(a.price - b.price), self.market)} "
                                    f"({a.reference_number if a.price > b.price else b.reference_number} costs more)"}
        sa, sb = rows[0]['size_for_comparison_sqft'], rows[1]['size_for_comparison_sqft']
        if sa and sb:
            diff['size_difference_sqft'] = f"{abs(sa - sb):,} sq ft ({a.reference_number if sa > sb else b.reference_number} is larger)"
        return {'ok': True, 'listings': rows, 'differences': diff,
                'note': 'Only these recorded fields can be compared; anything else is not recorded.'}

    def get_viewing_slots(self, reference: str, date: str) -> Dict[str, Any]:
        p = self._listing(reference)
        if not p:
            return {'ok': False, 'error': 'NO_MATCH: no active listing with that reference.'}
        try:
            day = datetime.strptime((date or '').strip(), '%Y-%m-%d').date()
        except ValueError:
            return {'ok': False, 'error': 'date must be YYYY-MM-DD (use the CALENDAR).'}
        now = self.now()
        if day < now.date():
            return {'ok': False, 'error': f'{day} is in the past. Ask which future date they meant - do not guess.'}
        if day > now.date() + timedelta(days=self.settings.max_days_ahead):
            return {'ok': False, 'error': f'Viewings can be booked up to {self.settings.max_days_ahead} days ahead.'}
        slots = actions.viewing_slots(self.organization, p, day, now)
        return {'ok': True, 'reference': p.reference_number, 'date': day.isoformat(), 'weekday': day.strftime('%A'),
                'timezone': self.market['tz'], 'free_slots': slots,
                'note': 'Offer only these times.' if slots else 'No free slots that day; offer another date.'}

    def get_my_appointments(self) -> Dict[str, Any]:
        phone = self._phone('')
        if not phone:
            return {'ok': False, 'error': 'Customer phone unknown - ask for the phone number used to book.'}
        appts = Appointment.objects.filter(
            organization=self.organization, lead__phone=phone, status__in=actions.ACTIVE_APPT,
            appointment_date__gte=self.now().date(),
        ).select_related('property_listing').order_by('appointment_date', 'appointment_time')[:5]
        return {'ok': True, 'appointments': [self._appt(a) for a in appts]}

    # ================================================================= writes
    def save_lead(self, intent: str, name: str = '', phone: str = '', email: str = '',
                  budget_min: float = None, budget_max: float = None, areas: List[str] = None,
                  property_type: str = '', bedrooms: int = None, timeline: str = '',
                  property_reference: str = '', notes: str = '') -> Dict[str, Any]:
        from apps.realestate.lead_service import LeadService

        phone = self._phone(phone)
        name = (name or self.conversation.customer_name or '').strip()
        if not phone:
            return {'ok': False, 'error': 'Need the customer phone number to save the lead.'}
        if not name or name.lower() in ('whatsapp user', 'customer', 'guest', 'website visitor'):
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
        return {'ok': True, 'saved': 'inquiry recorded for the team', 'lead_reference': str(lead.id)[:8].upper(),
                'note': 'This is an inquiry, not an accepted offer, reservation or booking.'}

    def prepare_viewing(self, reference: str, date: str, time: str, weekday: str = '', name: str = '',
                        phone: str = '', appointment_type: str = 'viewing', notes: str = '') -> Dict[str, Any]:
        """Validate everything and create a PREVIEW. Nothing is booked until the customer confirms."""
        if not self.settings.bookings_enabled:
            return {'ok': False, 'error': 'UNSUPPORTED_CAPABILITY: this agency books viewings through the team. '
                                          'Offer to pass the request on (save_lead) or a human.'}
        p = self._listing(reference)
        if not p:
            return {'ok': False, 'error': 'NO_MATCH: no active listing with that reference. Search again.'}
        phone, name = self._phone(phone), (name or '').strip()
        if not phone:
            return {'ok': False, 'error': 'MISSING_FIELD phone: ask for a contact number for updates.'}
        if not name or name.lower() in ('whatsapp user', 'customer', 'guest', 'website visitor'):
            return {'ok': False, 'error': "MISSING_FIELD name: ask whose name the viewing should be under."}
        try:
            d, t = _parse_day_time(date, time)
        except ValueError:
            return {'ok': False, 'error': 'date must be YYYY-MM-DD and time HH:MM (24h).'}
        if weekday and weekday.strip().lower()[:3] != d.strftime('%a').lower():
            return {'ok': False, 'error': f'{d.isoformat()} is a {d:%A}, not {weekday}. Re-check the CALENDAR.'}
        slots = self.get_viewing_slots(p.reference_number, d.isoformat())
        if not slots.get('ok'):
            return slots
        if t.strftime('%H:%M') not in slots['free_slots']:
            return {'ok': False, 'error': 'SLOT_UNAVAILABLE', 'free_slots_that_day': slots['free_slots'],
                    'note': 'Tell the customer that time is not available and offer these. Do not pick one for them.'}
        payload = {
            'listing_id': str(p.id), 'reference': p.reference_number, 'title': p.title,
            'price_seen': format_money(p.price, self.market), 'date': d.isoformat(), 'weekday': d.strftime('%A'),
            'time': t.strftime('%H:%M'), 'timezone': self.market['tz'], 'name': name, 'phone': phone,
            'appointment_type': appointment_type or 'viewing', 'notes': (notes or '')[:300],
            'needs_staff_approval': self.settings.viewings_need_staff_approval,
        }
        action = actions.create_preview(self.conversation, AgentAction.Kind.BOOK_VIEWING, payload)
        return {'ok': True, 'preview_id': str(action.id), 'awaiting_customer_confirmation': True,
                'preview': {k: payload[k] for k in ('reference', 'title', 'date', 'weekday', 'time', 'timezone',
                                                     'name', 'needs_staff_approval')},
                'note': 'NOT booked yet. Show this preview and ask the customer to confirm.'
                        + (' Say it will be a REQUEST that staff must approve.' if payload['needs_staff_approval'] else '')}

    def prepare_cancellation(self, confirmation_code: str, reason: str = '') -> Dict[str, Any]:
        appt = self._owned_appointment(confirmation_code)
        if isinstance(appt, dict):
            return appt
        payload = {'appointment_id': str(appt.id), 'code': appt.confirmation_code, 'reason': (reason or '')[:200],
                   **{k: v for k, v in self._appt(appt).items() if k in ('date', 'weekday', 'time', 'property')}}
        action = actions.create_preview(self.conversation, AgentAction.Kind.CANCEL_APPOINTMENT, payload)
        return {'ok': True, 'preview_id': str(action.id), 'awaiting_customer_confirmation': True, 'preview': payload,
                'note': 'NOT cancelled yet. Ask the customer to confirm the cancellation.'}

    def prepare_reschedule(self, confirmation_code: str, date: str, time: str, weekday: str = '') -> Dict[str, Any]:
        appt = self._owned_appointment(confirmation_code)
        if isinstance(appt, dict):
            return appt
        try:
            d, t = _parse_day_time(date, time)
        except ValueError:
            return {'ok': False, 'error': 'date must be YYYY-MM-DD and time HH:MM (24h).'}
        if weekday and weekday.strip().lower()[:3] != d.strftime('%a').lower():
            return {'ok': False, 'error': f'{d.isoformat()} is a {d:%A}, not {weekday}. Re-check the CALENDAR.'}
        if appt.property_listing:
            slots = actions.viewing_slots(self.organization, appt.property_listing, d, self.now())
            if t.strftime('%H:%M') not in slots:
                return {'ok': False, 'error': 'SLOT_UNAVAILABLE', 'free_slots_that_day': slots}
        payload = {'appointment_id': str(appt.id), 'code': appt.confirmation_code,
                   'property': appt.property_listing.title if appt.property_listing else None,
                   'from': f"{appt.appointment_date:%A %Y-%m-%d} {appt.appointment_time:%H:%M}",
                   'to_date': d.isoformat(), 'to_weekday': d.strftime('%A'), 'to_time': t.strftime('%H:%M'),
                   'timezone': self.market['tz']}
        action = actions.create_preview(self.conversation, AgentAction.Kind.RESCHEDULE_APPOINTMENT, payload)
        return {'ok': True, 'preview_id': str(action.id), 'awaiting_customer_confirmation': True, 'preview': payload,
                'note': 'NOT moved yet. The original time stays booked until the customer confirms.'}

    def confirm_pending_action(self, preview_id: str = '') -> Dict[str, Any]:
        executors = {
            AgentAction.Kind.BOOK_VIEWING: self._execute_booking,
            AgentAction.Kind.CANCEL_APPOINTMENT: self._execute_cancel,
            AgentAction.Kind.RESCHEDULE_APPOINTMENT: self._execute_reschedule,
        }
        result = actions.confirm(self.conversation, preview_id, self.current_message, self.turn_started_at,
                                 lambda a: executors[a.kind](a))
        if result.get('ok'):
            r = result['receipt']
            tool = {'book_viewing': 'book_viewing', 'cancel_appointment': 'cancel_appointment',
                    'reschedule_appointment': 'book_viewing'}[r['action']]
            self.actions.append({'tool': tool, 'confirmation_code': r.get('code')})
        return result

    def decline_pending_action(self) -> Dict[str, Any]:
        action = actions.decline_pending(self.conversation)
        return {'ok': True, 'declined': bool(action),
                'note': 'Nothing was changed.' if action else 'There was no pending action.'}

    def remember_customer_fact(self, fact: str) -> Dict[str, Any]:
        try:
            agent_memory.remember(self.organization, 'customer', agent_memory.customer_key(self.conversation), fact)
        except ValueError as e:
            return {'ok': False, 'error': str(e)}
        return {'ok': True}

    def forget_my_preferences(self) -> Dict[str, Any]:
        """Customer asked us to forget their saved preferences/summary. Appointments and leads stay."""
        from apps.ai_engine.models import AgentMemory

        updated = AgentMemory.objects.filter(
            organization=self.organization, subject_type=AgentMemory.SubjectType.CUSTOMER,
            subject_key=agent_memory.customer_key(self.conversation),
        ).update(facts=[], summary='', summarized_until=None)
        self.actions.append({'tool': 'forget_my_preferences'})
        return {'ok': True, 'cleared': bool(updated),
                'note': 'Saved preferences and chat summary cleared. Existing appointments and inquiries are '
                        'not affected - say so.'}

    def escalate_to_human(self, reason: str) -> Dict[str, Any]:
        self.escalation = {'reason': (reason or 'customer_request')[:200]}
        return {'ok': True, 'note': 'Handoff request recorded for the team. Say you have passed it on; do NOT '
                                    'promise a response time or say someone is online now.'}

    # -------------------------------------------------------------- executors
    def _execute_booking(self, action) -> Dict[str, Any]:
        from apps.realestate.lead_service import AppointmentService

        pl = action.payload
        listing = actions.lock_listing(self.organization, pl['listing_id'])
        if format_money(listing.price, self.market) != pl['price_seen']:
            raise actions.ActionRejected(
                f"PRICE_CHANGED: the listed price is now {format_money(listing.price, self.market)} "
                f"(was {pl['price_seen']} when previewed). Nothing was booked; ask if they still want to view it.")
        d = datetime.strptime(pl['date'], '%Y-%m-%d').date()
        if pl['time'] not in actions.viewing_slots(self.organization, listing, d, self.now()):
            free = actions.viewing_slots(self.organization, listing, d, self.now())
            raise actions.ActionRejected(f"SLOT_TAKEN: {pl['time']} was just taken. Nothing was booked. "
                                         f"Free that day: {', '.join(free) or 'none'}.")
        appt, message = AppointmentService(self.organization, self.conversation).create_appointment_from_extracted_data({
            'appointment_intent': True, 'appointment_date': pl['date'], 'appointment_time': pl['time'],
            'appointment_type': pl['appointment_type'], 'customer_name': pl['name'], 'customer_phone': pl['phone'],
            'property_reference': pl['reference'], 'notes': pl.get('notes', ''),
        }, source=self._source())
        if not appt:
            raise actions.ActionRejected(f'BOOKING_FAILED: {message}. Nothing was booked.')
        if pl.get('needs_staff_approval') and appt.status == Appointment.Status.CONFIRMED:
            Appointment.objects.filter(pk=appt.pk).update(status=Appointment.Status.SCHEDULED, confirmed_at=None)
            appt.refresh_from_db()
        self._remember(f"Viewing {appt.confirmation_code} for {pl['title']} on {pl['weekday']} {pl['date']} "
                       f"{pl['time']} ({'awaiting staff approval' if pl.get('needs_staff_approval') else 'confirmed'})",
                       display_name=pl['name'])
        return {'action': 'book_viewing', 'code': appt.confirmation_code,
                'status': 'pending_staff_approval' if pl.get('needs_staff_approval') else 'confirmed',
                'reference': pl['reference'], 'property': pl['title'], 'date': pl['date'], 'weekday': pl['weekday'],
                'time': pl['time'], 'timezone': pl['timezone'], 'name': pl['name']}

    def _execute_cancel(self, action) -> Dict[str, Any]:
        appt = Appointment.objects.select_for_update().filter(
            organization=self.organization, id=action.payload['appointment_id']).first()
        if not appt or appt.status not in actions.ACTIVE_APPT:
            raise actions.ActionRejected('NOT_ACTIVE: that appointment is no longer active. Nothing changed.')
        appt.cancel(reason=action.payload.get('reason') or 'Cancelled by customer via chat')
        self._remember(f"Cancelled appointment {appt.confirmation_code}")
        return {'action': 'cancel_appointment', 'code': appt.confirmation_code, 'status': 'cancelled'}

    def _execute_reschedule(self, action) -> Dict[str, Any]:
        pl = action.payload
        appt = Appointment.objects.select_for_update(of=('self',)).filter(
            organization=self.organization, id=pl['appointment_id']).select_related('property_listing').first()
        if not appt or appt.status not in actions.ACTIVE_APPT:
            raise actions.ActionRejected('NOT_ACTIVE: that appointment is no longer active. Nothing changed.')
        d = datetime.strptime(pl['to_date'], '%Y-%m-%d').date()
        if appt.property_listing:
            actions.lock_listing(self.organization, appt.property_listing_id)
            if pl['to_time'] not in actions.viewing_slots(self.organization, appt.property_listing, d, self.now()):
                raise actions.ActionRejected(f"SLOT_TAKEN: {pl['to_time']} is no longer free. The original "
                                             f"appointment ({pl['from']}) is unchanged.")
        appt.appointment_date = d
        appt.appointment_time = datetime.strptime(pl['to_time'], '%H:%M').time()
        appt.save(update_fields=['appointment_date', 'appointment_time', 'updated_at'])
        self._remember(f"Moved {appt.confirmation_code} to {pl['to_weekday']} {pl['to_date']} {pl['to_time']}")
        return {'action': 'reschedule_appointment', 'code': appt.confirmation_code, 'status': appt.status,
                'date': pl['to_date'], 'weekday': pl['to_weekday'], 'time': pl['to_time'], 'timezone': pl['timezone']}

    # ---------------------------------------------------------------- helpers
    def _owned_appointment(self, code: str):
        """Only the customer who booked (same verified channel phone) may change an appointment."""
        phone = ''.join(ch for ch in (self.conversation.customer_phone or '') if ch.isdigit())
        appt = Appointment.objects.filter(
            organization=self.organization, confirmation_code__iexact=(code or '').strip(),
            status__in=actions.ACTIVE_APPT,
        ).select_related('lead', 'property_listing').first()
        if not appt or not phone or ''.join(ch for ch in appt.lead.phone if ch.isdigit()) != phone:
            # Same answer for "doesn't exist" and "not yours": a reference is not proof of identity.
            return {'ok': False, 'error': 'NOT_AUTHORIZED_OR_NOT_FOUND: no active appointment with that code '
                                          'for this customer. Do not reveal anything about it.'}
        return appt

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

    def _appt(self, a: Appointment) -> Dict[str, Any]:
        from apps.realestate.appointment_notifications import timing
        return {
            # Date alone is not enough: "today 11:00" at 13:51 has already happened.
            'timing': timing(a, now=self.now(), tz=self.tz),
            'confirmation_code': a.confirmation_code,
            'date': a.appointment_date.isoformat(),
            'weekday': a.appointment_date.strftime('%A'),
            'time': a.appointment_time.strftime('%H:%M'),
            'type': a.get_appointment_type_display(),
            'property': a.property_listing.title if a.property_listing else None,
            'property_reference': a.property_listing.reference_number if a.property_listing else None,
            'status': 'confirmed' if a.status == Appointment.Status.CONFIRMED else 'awaiting staff approval',
        }

    def registry(self) -> Dict[str, Callable[..., Dict[str, Any]]]:
        allowed = capabilities.allowed_tools(self.organization, self.settings)
        tools = {
            'search_properties': self.search_properties,
            'list_locations': self.list_locations,
            'get_portfolio_overview': self.get_portfolio_overview,
            'get_property_details': self.get_property_details,
            'send_property_photos': self.send_property_photos,
            'compare_properties': self.compare_properties,
            'get_viewing_slots': self.get_viewing_slots,
            'get_my_appointments': self.get_my_appointments,
            'save_lead': self.save_lead,
            'prepare_viewing': self.prepare_viewing,
            'prepare_cancellation': self.prepare_cancellation,
            'prepare_reschedule': self.prepare_reschedule,
            'confirm_pending_action': self.confirm_pending_action,
            'decline_pending_action': self.decline_pending_action,
            'remember_customer_fact': self.remember_customer_fact,
            'forget_my_preferences': self.forget_my_preferences,
            'escalate_to_human': self.escalate_to_human,
        }
        return {k: v for k, v in tools.items() if k in allowed}

    def schemas(self) -> List[Dict[str, Any]]:
        allowed = capabilities.allowed_tools(self.organization, self.settings)
        return [s for s in TOOL_SCHEMAS if s['function']['name'] in allowed]


def _fn(name, description, properties, required=()):
    return {'type': 'function', 'function': {
        'name': name, 'description': description,
        'parameters': {'type': 'object', 'properties': properties, 'required': list(required)},
    }}


_DATE = {'type': 'string', 'description': 'YYYY-MM-DD from the CALENDAR'}
_TIME = {'type': 'string', 'description': 'HH:MM 24h, one of the free slots'}
_WEEKDAY = {'type': 'string', 'description': 'Weekday of that date from the CALENDAR - must match'}

TOOL_SCHEMAS = [
    _fn('search_properties', 'Search ACTIVE listings with the customer\'s filters (hard limits). Returns exact matches; '
        'if none, near_matches labelled with what differs. Never widens budget/area silently.', {
        'listing_type': {'type': 'string', 'enum': ['sale', 'rent']},
        'property_type': {'type': 'string', 'enum': [c for c, _ in PropertyListing.PropertyType.choices],
                          'description': 'jagga/plot/ropani/aana = land · kotha = room · flat/BHK = apartment · '
                                         'ghar = house · shutter/pasal = retail'},
        'area': {'type': 'string', 'description': 'District or area, e.g. "Biratnagar", "Baneshwor"'},
        'min_price': {'type': 'number', 'description': 'Plain number, local currency. 1 lakh = 100000, 1 crore = 10000000'},
        'max_price': {'type': 'number', 'description': 'HARD maximum the customer stated (monthly rent for rentals)'},
        'min_bedrooms': {'type': 'integer'},
        'keywords': {'type': 'string', 'description': 'Must-haves, e.g. "parking wifi attached bathroom"'},
        'sort': {'type': 'string', 'enum': ['best_match', 'price_asc', 'price_desc', 'newest'],
                 'description': 'price_asc for "cheap/sasto/student"'},
        'exclude_references': {'type': 'array', 'items': {'type': 'string'},
                               'description': 'Listings the customer said not to show'},
        'page': {'type': 'integer', 'description': 'Next page when the customer asks for more'},
    }),
    _fn('list_locations', 'Every district where the agency has active stock of a type, with counts and price ranges. '
        'Use for "kaha kaha / where / which areas / kun kun thau" questions.', {
        'property_type': {'type': 'string'}, 'listing_type': {'type': 'string', 'enum': ['sale', 'rent']},
    }),
    _fn('get_portfolio_overview', 'Everything the agency offers, grouped by type with districts and price ranges.', {}),
    _fn('get_property_details', 'Full recorded details of one listing, incl. photos and `not_recorded` topics.',
        {'reference': {'type': 'string'}}, ['reference']),
    _fn('send_property_photos', 'Send the real uploaded photos of a listing ("photo pathaunu", "can I see pictures?").',
        {'reference': {'type': 'string'}, 'count': {'type': 'integer', 'description': 'max 6, default 4'}},
        ['reference']),
    _fn('compare_properties', 'Side-by-side recorded facts and computed differences for 2-3 listings.',
        {'references': {'type': 'array', 'items': {'type': 'string'}}}, ['references']),
    _fn('get_viewing_slots', 'Free viewing times for a listing on a date. Call before offering or preparing a time.',
        {'reference': {'type': 'string'}, 'date': _DATE}, ['reference', 'date']),
    _fn('get_my_appointments', 'This customer\'s upcoming appointments (their own only).', {}),
    _fn('save_lead', 'Record an inquiry / callback / seller listing request / non-binding interest for the team. '
        'Only when the customer asked for follow-up.', {
        'intent': {'type': 'string', 'enum': ['buy', 'rent', 'sell', 'invest', 'general']},
        'name': {'type': 'string'}, 'phone': {'type': 'string', 'description': 'Only if not on WhatsApp'},
        'email': {'type': 'string'}, 'budget_min': {'type': 'number'}, 'budget_max': {'type': 'number'},
        'areas': {'type': 'array', 'items': {'type': 'string'}}, 'property_type': {'type': 'string'},
        'bedrooms': {'type': 'integer'}, 'timeline': {'type': 'string'},
        'property_reference': {'type': 'string'}, 'notes': {'type': 'string'},
    }, ['intent']),
    _fn('prepare_viewing', 'Step 1 of booking: validate and create a PREVIEW (not a booking). Then show it and ask '
        'the customer to confirm.', {
        'reference': {'type': 'string'}, 'date': _DATE, 'time': _TIME, 'weekday': _WEEKDAY,
        'name': {'type': 'string'}, 'phone': {'type': 'string', 'description': 'Only if not on WhatsApp'},
        'appointment_type': {'type': 'string', 'enum': ['viewing', 'virtual_tour', 'consultation']},
        'notes': {'type': 'string'},
    }, ['reference', 'date', 'time', 'weekday', 'name']),
    _fn('prepare_cancellation', 'Step 1 of cancelling the customer\'s own appointment: creates a preview.',
        {'confirmation_code': {'type': 'string'}, 'reason': {'type': 'string'}}, ['confirmation_code']),
    _fn('prepare_reschedule', 'Step 1 of moving the customer\'s own appointment to a free slot: creates a preview.',
        {'confirmation_code': {'type': 'string'}, 'date': _DATE, 'time': _TIME, 'weekday': _WEEKDAY},
        ['confirmation_code', 'date', 'time', 'weekday']),
    _fn('confirm_pending_action', 'Step 2: execute the pending preview. ONLY when the customer\'s latest message is a '
        'plain yes to that preview. Returns the receipt to report.', {'preview_id': {'type': 'string'}}),
    _fn('decline_pending_action', 'The customer said no / keep it to the pending preview.', {}),
    _fn('remember_customer_fact', 'Persist a durable preference (not listing facts) for future chats.',
        {'fact': {'type': 'string'}}, ['fact']),
    _fn('forget_my_preferences', 'The customer asked you to forget their saved preferences / memory.', {}),
    _fn('escalate_to_human', 'Hand the conversation to staff (explicit request, complaint, negotiation, legal/tax, '
        'repeated failure).', {'reason': {'type': 'string'}}, ['reason']),
]
