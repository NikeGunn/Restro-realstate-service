"""
Public, search-engine-friendly property site: kribaat.com/realestate/properties

Server-rendered by Django (not the React dashboard) so Google gets complete HTML, structured
data (JSON-LD), canonical URLs and a sitemap. Every page funnels to ONE conversion: a WhatsApp
chat with the agency's AI agent, with a pre-filled first message that names the listing
(reference + title + price) or the visitor's needs, so the agent starts grounded.

URLs (all GET, no auth):
  /realestate/properties/                               all listings (+ ?q, ?deal, ?type, ?max, ?sort)
  /realestate/properties/<category>/[<city>/]           SEO landing pages, e.g. land-for-sale/lalitpur/
  /realestate/properties/<prop123456>-<slug>/           listing detail (301 to the canonical slug)
  /realestate/properties/<prop123456>/chat/             count + redirect to wa.me (listing message)
  /realestate/properties/chat/                          count + redirect to wa.me (needs message)
  /sitemap.xml, /robots.txt
"""
from decimal import Decimal, InvalidOperation
import json
import logging
import re
from typing import Dict, List, Optional
from urllib.parse import quote, urlencode

from django.conf import settings
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.http import Http404, HttpResponse, HttpResponsePermanentRedirect, HttpResponseRedirect
from django.shortcuts import render
from django.utils.html import strip_tags
from django.utils.text import slugify
from django.views.decorators.http import require_GET

from apps.accounts.models import Organization
from apps.ai_engine.agent.tools import DEFAULT_MARKET, MARKET_ALIASES, MARKETS, format_money

from .models import PropertyListing

logger = logging.getLogger(__name__)

PUBLIC_STATUSES = (PropertyListing.Status.ACTIVE, PropertyListing.Status.COMING_SOON)
PAGE_SIZE = 18
REF_RE = re.compile(r'^(prop\d{6})(?:-[a-z0-9-]*)?$', re.I)

# Category landing pages: slug → (filters, H1 / title text, Nepali keyword for search snippets)
CATEGORIES: Dict[str, dict] = {
    'rooms-for-rent': dict(type='room', deal='rent', title='Rooms for rent', ne='कोठा भाडामा', short='Rooms'),
    'flats-for-rent': dict(type='apartment', deal='rent', title='Flats & apartments for rent', ne='फ्ल्याट भाडामा', short='Flats'),
    'houses-for-rent': dict(type='house', deal='rent', title='Houses for rent', ne='घर भाडामा', short='Houses to rent'),
    'houses-for-sale': dict(type='house', deal='sale', title='Houses for sale', ne='घर बिक्रीमा', short='Houses to buy'),
    'land-for-sale': dict(type='land', deal='sale', title='Land for sale', ne='जग्गा बिक्रीमा', short='Land'),
    'shops-for-rent': dict(type='retail', deal='rent', title='Shops & shutters for rent', ne='सटर भाडामा', short='Shops'),
    'offices-for-rent': dict(type='office', deal='rent', title='Office space for rent', ne='अफिस भाडामा', short='Offices'),
    'commercial': dict(type='commercial', deal='', title='Commercial property', ne='व्यापारिक', short='Commercial'),
}
TYPE_LABELS = {
    'room': 'Room', 'apartment': 'Flat', 'house': 'House', 'land': 'Land', 'retail': 'Shop / shutter',
    'office': 'Office', 'commercial': 'Commercial', 'condo': 'Condo', 'townhouse': 'Townhouse',
    'industrial': 'Industrial', 'other': 'Other',
}
WANT_WORDS = {  # needs form → natural first WhatsApp message
    'room': 'a room', 'apartment': 'a flat', 'house': 'a house', 'land': 'land', 'retail': 'a shop / shutter',
    'office': 'an office space', 'commercial': 'a commercial property',
}


# ----------------------------------------------------------------- tenant + market
def public_organization() -> Optional[Organization]:
    """The agency whose listings this site shows (configmap PUBLIC_LISTINGS_ORG = id or name)."""
    key = getattr(settings, 'PUBLIC_LISTINGS_ORG', '') or ''
    qs = Organization.objects.filter(business_type='real_estate', is_active=True)
    if key:
        org = qs.filter(id=key).first() if re.fullmatch(r'[0-9a-f-]{36}', key) else qs.filter(name=key).first()
        if org:
            return org
        logger.error("PUBLIC_LISTINGS_ORG=%s matches no active real-estate organization", key)
        return None
    # Unset (dev): the oldest real agency that has published listings; never an eval tenant.
    return (qs.exclude(name__startswith='EVAL').filter(property_listings__is_published=True)
            .order_by('created_at').distinct().first())


def market_of(listing) -> dict:
    country = (listing.country or '').strip().lower()
    return MARKETS.get(MARKET_ALIASES.get(country, country), DEFAULT_MARKET)


def price_text(listing) -> str:
    text = format_money(listing.price, market_of(listing))
    return text + ' / month' if listing.listing_type in ('rent', 'lease') else text


def short_price(listing) -> str:
    """'Rs 2.1 crore', 'Rs 8,000/mo' - for cards and messages."""
    m = market_of(listing)
    amount = int(listing.price)
    rent = listing.listing_type in ('rent', 'lease')
    if m.get('lakh_crore') and not rent and amount >= 100_000:
        if amount >= 10_000_000:
            return f"{m['currency']} {amount / 10_000_000:g} crore"
        return f"{m['currency']} {amount / 100_000:g} lakh"
    full = format_money(listing.price, m).split(' (')[0]
    return full + ('/mo' if rent else '')


# ---------------------------------------------------------------------- WhatsApp
def whatsapp_number(org: Organization) -> str:
    """Digits only (wa.me format). Override → WhatsApp Cloud API display number → org phone."""
    override = re.sub(r'\D', '', getattr(settings, 'PUBLIC_WHATSAPP_NUMBER', '') or '')
    if override:
        return override
    cache_key = f'public:wa-number:{org.id}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    number = ''
    try:
        from apps.channels.models import WhatsAppConfig
        cfg = WhatsAppConfig.objects.filter(organization=org, is_active=True).first()
        if cfg and cfg.phone_number_id and cfg.access_token:
            import requests
            version = getattr(settings, 'META_GRAPH_API_VERSION', 'v18.0')
            r = requests.get(f'https://graph.facebook.com/{version}/{cfg.phone_number_id}',
                             params={'fields': 'display_phone_number'},
                             headers={'Authorization': f'Bearer {cfg.access_token}'}, timeout=5)
            if r.ok:
                number = re.sub(r'\D', '', r.json().get('display_phone_number', ''))
            else:
                logger.warning("WhatsApp display number lookup failed: %s %s", r.status_code, r.text[:200])
    except Exception:
        logger.exception("WhatsApp display number lookup failed")
    number = number or re.sub(r'\D', '', org.phone or '')
    cache.set(cache_key, number, 24 * 3600 if number else 300)
    return number


def listing_message(listing, lang: str = 'en') -> str:
    from apps.ai_engine.agent.tone import no_dashes
    return no_dashes(_listing_message(listing, lang))


def _listing_message(listing, lang: str) -> str:
    ref, title, price = listing.reference_number, listing.title, short_price(listing)
    if lang == 'ne':
        return (f"Namaste! Malai {ref} - {title} ({price}) ma interest chha. "
                f"Yo ahile pani available chha? Photo ra viewing ko bare ma pani jannu chha. (kribaat.com bata)")
    return (f"Namaste! I'm interested in {ref} - {title} ({price}). "
            f"Is it still available? I'd like photos and to arrange a viewing. (via kribaat.com)")


def needs_message(want: str, deal: str, area: str, budget: str, lang: str = 'en') -> str:
    thing = WANT_WORDS.get(want, 'a property')
    area = area.strip()[:60]
    budget = re.sub(r'[^\d,. a-zA-Z]', '', budget)[:30].strip()
    if lang == 'ne':
        parts = [f"Namaste! Malai {area + ' ma ' if area else ''}{TYPE_LABELS.get(want, 'property').lower()}"
                 f"{' bhada ma' if deal == 'rent' else ' kinna' if deal == 'sale' else ''} chahiyo."]
        if budget:
            parts.append(f"Budget {budget} samma.")
        parts.append("Ke ke option chha? (kribaat.com bata)")
        return ' '.join(parts)
    verb = 'rent' if deal == 'rent' else 'buy' if deal == 'sale' else 'find'
    msg = f"Namaste! I'm looking to {verb} {thing}{' in ' + area if area else ''}."
    if budget:
        msg += f" My budget is up to {budget}."
    return msg + " What options do you have? (via kribaat.com)"


def wa_link(number: str, text: str) -> str:
    return f"https://wa.me/{number}?text={quote(text)}" if number else ''


def _once(request, kind: str, ref: str) -> bool:
    """Count one view/click per visitor per listing per hour (refresh-spam safe)."""
    ip = (request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR', ''))
    return cache.add(f'public:{kind}:{ref}:{ip}', 1, 3600)


# ------------------------------------------------------------------------ queries
def _base_qs(org):
    return (PropertyListing.objects.filter(organization=org, is_published=True, status__in=PUBLIC_STATUSES)
            .order_by('-is_featured', '-created_at'))


_DEVA_DIGITS = str.maketrans('०१२३४५६७८९', '0123456789')
_BUDGET_RE = re.compile(r'(\d+(?:\.\d+)?)\s*(crore|cr|करोड|lakhs?|lacs?|लाख|k|thousand|hajar|hazar|हजार)?\b', re.I)
_UNITS = {'crore': 10_000_000, 'cr': 10_000_000, 'करोड': 10_000_000, 'lakh': 100_000, 'lakhs': 100_000,
          'lac': 100_000, 'lacs': 100_000, 'लाख': 100_000, 'k': 1_000, 'thousand': 1_000, 'hajar': 1_000,
          'hazar': 1_000, 'हजार': 1_000}


def parse_budget(raw) -> Optional[Decimal]:
    """'15000', '15,000', 'Rs 15000', '50 lakh', '1.2 crore', '15k', '15 hajar', '५० लाख' -> amount.
    Unreadable input returns None (the filter is skipped and the page says so) - never a wrong number."""
    text = str(raw or '').translate(_DEVA_DIGITS).lower().replace(',', '')
    m = _BUDGET_RE.search(text)
    if not m:
        return None
    try:
        value = Decimal(m.group(1)) * _UNITS.get((m.group(2) or '').lower(), 1)
    except InvalidOperation:
        return None
    return value if value > 0 else None


def _area_groups(q: str):
    """'Chabahil, Lalitpur' / 'ktm or patan' -> [['Chabahil'], ['Lalitpur']]: any group may match,
    every word inside a group must. Type and rent/buy words ('kotha', 'bhada') are pulled out."""
    from apps.ai_engine.agent import vocab

    groups, ptype, deal = [], '', ''
    for part in re.split(r'[,/;|]+|\s+(?:or|wa|athawa|अथवा)\s+', q):
        words, t, d = vocab.split_keywords(part)
        ptype, deal = ptype or t, deal or d
        words = [vocab.normalize_area(w) for w in words]
        whole = vocab.normalize_area(part.strip().lower())
        if whole != part.strip().lower() and whole:      # a multi-word alias ("kathmandu valley")
            words = [whole]
        words = [w for w in words if w]
        if words:
            groups.append(words[:5])
    return groups, ptype, deal


def _apply_filters(qs, params: dict):
    q = (params.get('q') or '').strip()[:80]
    groups, q_type, q_deal = _area_groups(q) if q else ([], '', '')
    ptype = params.get('type') if params.get('type') in TYPE_LABELS else q_type
    if ptype:
        qs = qs.filter(property_type=ptype)
    deal = params.get('deal') or ('' if params.get('deal_set') else q_deal)
    if deal == 'rent':
        qs = qs.filter(listing_type__in=('rent', 'lease'))
    elif deal == 'sale':
        qs = qs.filter(listing_type='sale')
    if params.get('city'):
        c = params['city']
        qs = qs.filter(Q(city__iexact=c) | Q(neighborhood__iexact=c) | Q(state__iexact=c))
    if groups:
        any_group = Q()
        for words in groups:
            group = Q()
            for word in words:
                group &= (Q(title__icontains=word) | Q(neighborhood__icontains=word) | Q(city__icontains=word)
                          | Q(address_line1__icontains=word) | Q(state__icontains=word)
                          | Q(reference_number__iexact=word))
            any_group |= group
        qs = qs.filter(any_group)
    budget = parse_budget(params.get('max'))
    if budget:
        qs = qs.filter(price__lte=budget)
    sort = params.get('sort')
    if sort == 'price_asc':
        qs = qs.order_by('price')
    elif sort == 'price_desc':
        qs = qs.order_by('-price')
    elif sort == 'newest':
        qs = qs.order_by('-created_at')
    return qs


# Rent/buy is relaxed before type: "Rent + Land" should show land for sale, not rooms.
RELAX_ORDER = (('max', 'without the budget limit'), ('deal', 'for both rent and sale'), ('q', 'in other areas'),
               ('type', 'of other types'))


def closest_matches(org, params: dict, limit: int = 6):
    """Nothing matches every filter: drop one filter at a time (budget first) and say which one, so a
    visitor who picked 'Rent + Land' learns land is for sale here instead of meeting an empty page."""
    for key, label in RELAX_ORDER:
        if not params.get(key):
            continue
        relaxed = dict(params, **{key: ''}, deal_set=params.get('deal_set') and key != 'deal')
        rows = list(_apply_filters(_base_qs(org), relaxed)[:limit])
        if rows:
            return label, rows
    return '', []


def _city_slug(name: str) -> str:
    return slugify(name or '')


def _cities(org) -> List[dict]:
    rows = {}
    for city in _base_qs(org).values_list('city', flat=True):
        if city:
            rows.setdefault(_city_slug(city), {'name': city, 'slug': _city_slug(city), 'count': 0})['count'] += 1
    return sorted(rows.values(), key=lambda r: -r['count'])


def _category_counts(org) -> List[dict]:
    base = _base_qs(org)
    out = []
    for slug, cat in CATEGORIES.items():
        n = _apply_filters(base, cat).count()
        if n:
            out.append({'slug': slug, 'title': cat['title'], 'short': cat['short'], 'ne': cat['ne'], 'count': n})
    return out


def canonical_path(listing) -> str:
    slug = slugify(f"{listing.title} {listing.city}")[:80].strip('-')
    return f"/realestate/properties/{listing.reference_number.lower()}-{slug}/"


def _card(listing) -> dict:
    images = [u for u in (listing.images or []) if isinstance(u, str) and u.startswith('http')]
    return {
        'obj': listing, 'url': canonical_path(listing), 'price': short_price(listing),
        'price_full': price_text(listing), 'image': images[0] if images else '', 'photo_count': len(images),
        'type_label': TYPE_LABELS.get(listing.property_type, 'Property'),
        'deal_label': 'For rent' if listing.listing_type in ('rent', 'lease') else 'For sale',
        'place': ', '.join(p for p in [listing.neighborhood, listing.city] if p),
    }


def _site_url(request) -> str:
    return getattr(settings, 'PUBLIC_SITE_URL', '') or f"{request.scheme}://{request.get_host()}"


def _common(request, org) -> dict:
    number = whatsapp_number(org)
    return {
        'org': org, 'site': _site_url(request), 'wa_number': number,
        'wa_general': wa_link(number, "Namaste! I'm looking for a property. Can you help me? (via kribaat.com)"),
        'wa_general_ne': wa_link(number, "Namaste! Malai property khojna sahayog chahiyo. (kribaat.com bata)"),
        'categories_nav': _category_counts(org), 'cities_nav': _cities(org)[:12],
        'office': org.locations.filter(is_primary=True).first() if hasattr(org, 'locations') else None,
        'type_choices': [(k, v) for k, v in TYPE_LABELS.items() if k in WANT_WORDS],
    }


def _cache_headers(resp, seconds=300):
    resp['Cache-Control'] = f'public, max-age={seconds}'
    return resp


# -------------------------------------------------------------------------- views
@require_GET
def listings(request, category: str = '', city: str = ''):
    org = public_organization()
    if org is None:
        raise Http404('No public listings')
    params = {k: request.GET.get(k, '') for k in ('q', 'deal', 'type', 'max', 'sort')}
    # "Either" in the hero sends deal="" on purpose: then words like "bhada" in the area box must not
    # silently narrow it to rentals.
    params['deal_set'] = 'deal' in request.GET
    cat = None
    if category:
        cat = CATEGORIES.get(category)
        if not cat:
            raise Http404('Unknown category')
        params.update(type=cat['type'], deal=cat['deal'])
    city_name = ''
    if city:
        match = next((c for c in _cities(org) if c['slug'] == city), None)
        if not match:
            raise Http404('Unknown city')
        city_name = params['city'] = match['name']
    qs = _apply_filters(_base_qs(org), params)
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get('page'))

    noun = cat['title'] if cat else 'Rooms, flats, houses & land'
    where = city_name or 'Nepal'
    heading = f"{noun} in {where}"
    total = page.paginator.count
    filtered = any(params.get(k) for k in ('q', 'max', 'sort')) or (not cat and any(params.get(k) for k in ('deal', 'type')))
    path = request.path
    ctx = _common(request, org)
    ctx.update({
        'page': page, 'cards': [dict(_card(p), delay=min(i, 8) * 60) for i, p in enumerate(page.object_list)], 'total': total, 'heading': heading,
        'category': category, 'category_obj': cat, 'city': city, 'city_name': city_name, 'params': params,
        'title': f"{heading} - {total} listing{'s' if total != 1 else ''} | {org.name}",
        'description': (f"{total} verified {noun.lower()} in {where} from {org.name}. See prices in "
                        f"lakh/crore, photos and details, then chat on WhatsApp to book a viewing - "
                        f"{cat['ne'] if cat else 'कोठा, फ्ल्याट, घर, जग्गा'}."),
        # Filtered/paginated variants point at the clean landing page; noindex avoids thin duplicates.
        'canonical': ctx['site'] + path + (f"?page={page.number}" if page.number > 1 and not filtered else ''),
        'noindex': filtered or total == 0,
        'querystring': urlencode({k: v for k, v in params.items() if v and k not in ('city', 'deal_set')}),
        'is_home': not category and not city and not filtered,
    })
    if ctx['is_home']:
        from apps.showcase.models import ShowcaseVideo
        ctx['showcase'] = ShowcaseVideo.public(ShowcaseVideo.Placement.PROPERTIES).first()
    if params.get('max') and parse_budget(params['max']) is None:
        ctx['budget_ignored'] = params['max']
    if total == 0 and filtered:
        label, rows = closest_matches(org, params)
        ctx['near_label'] = label
        ctx['near_cards'] = [_card(p) for p in rows]
    ctx['jsonld'] = _script_json(_list_jsonld(ctx))
    return _cache_headers(render(request, 'realestate/public/list.html', ctx))


@require_GET
def detail(request, ref_slug: str):
    m = REF_RE.match(ref_slug)
    if not m:
        raise Http404()
    org = public_organization()
    listing = (PropertyListing.objects.filter(organization=org, is_published=True, reference_number__iexact=m.group(1))
               .first() if org else None)
    if listing is None:
        raise Http404('Listing not found')
    canonical = canonical_path(listing)
    if request.path != canonical:
        return HttpResponsePermanentRedirect(canonical)
    available = listing.status in PUBLIC_STATUSES
    if available and _once(request, 'view', listing.reference_number):
        PropertyListing.objects.filter(pk=listing.pk).update(view_count=F('view_count') + 1)

    ctx = _common(request, org)
    card = _card(listing)
    images = [u for u in (listing.images or []) if isinstance(u, str) and u.startswith('http')]
    related = [_card(p) for p in _base_qs(org).filter(property_type=listing.property_type)
               .exclude(pk=listing.pk)[:3]]
    facts = [(label, value) for label, value in [
        ('Reference', listing.reference_number), ('Type', card['type_label']), ('Deal', card['deal_label']),
        ('Price', card['price_full']), ('Bedrooms', listing.bedrooms), ('Bathrooms', listing.bathrooms),
        ('Floor area', f"{listing.square_feet:,} sq ft" if listing.square_feet else None),
        ('Plot size', f"{listing.lot_size:,} sq ft" if listing.lot_size else None),
        ('Parking', listing.parking_spaces), ('Year built', listing.year_built),
        ('Area', card['place']), ('Province', listing.state),
    ] if value not in (None, '')]
    description = strip_tags(listing.description or '').strip()
    ctx.update({
        'l': listing, 'card': card, 'images': images, 'facts': facts, 'related': related,
        'features': [str(f) for f in (listing.features or []) + (listing.amenities or []) if f][:16],
        'available': available, 'description_text': description,
        'chat_url': f"/realestate/properties/{listing.reference_number.lower()}/chat/",
        'title': f"{listing.title} - {card['price']} | {listing.reference_number} | {org.name}",
        'description': (f"{card['deal_label']}: {listing.title}, {card['place']}. {card['price_full']}. "
                        f"{description[:110]}").strip(),
        'canonical': ctx['site'] + canonical, 'noindex': not available,
        'og_image': images[0] if images else '',
        'crumb': next(((slug, cat['title']) for slug, cat in CATEGORIES.items()
                       if cat['type'] == listing.property_type
                       and cat['deal'] in ('', 'rent' if listing.listing_type in ('rent', 'lease') else 'sale')), None),
    })
    ctx['jsonld'] = _script_json(_detail_jsonld(ctx))
    return _cache_headers(render(request, 'realestate/public/detail.html', ctx, status=200), 120)


@require_GET
def chat_listing(request, ref: str):
    """Count the click, then hand over to WhatsApp with the listing pre-named."""
    org = public_organization()
    listing = (PropertyListing.objects.filter(organization=org, is_published=True, reference_number__iexact=ref)
               .first() if org else None)
    if listing is None:
        raise Http404()
    number = whatsapp_number(org)
    if not number:
        raise Http404('WhatsApp is not configured for this agency')
    if _once(request, 'wa', listing.reference_number):
        PropertyListing.objects.filter(pk=listing.pk).update(whatsapp_clicks=F('whatsapp_clicks') + 1)
    lang = 'ne' if request.GET.get('lang') == 'ne' else 'en'
    resp = HttpResponseRedirect(wa_link(number, listing_message(listing, lang)))
    resp['Cache-Control'] = 'no-store'
    resp['X-Robots-Tag'] = 'noindex'
    return resp


@require_GET
def chat_needs(request):
    org = public_organization()
    number = whatsapp_number(org) if org else ''
    if not number:
        raise Http404('WhatsApp is not configured for this agency')
    want = request.GET.get('type', '')
    lang = 'ne' if request.GET.get('lang') == 'ne' else 'en'
    # Accepts the hero form's own field names (q / max) as well as area / budget.
    area = request.GET.get('area') or request.GET.get('q') or ''
    budget = request.GET.get('budget') or request.GET.get('max') or ''
    if budget.replace(',', '').isdigit():
        budget = 'Rs ' + f"{int(budget.replace(',', '')):,}"
    text = needs_message(want if want in WANT_WORDS else '', request.GET.get('deal', ''), area, budget, lang)
    resp = HttpResponseRedirect(wa_link(number, text))
    resp['Cache-Control'] = 'no-store'
    resp['X-Robots-Tag'] = 'noindex'
    return resp


@require_GET
def sitemap(request):
    org = public_organization()
    site = _site_url(request)
    urls = [(site + '/', None, '1.0')]
    if org:
        urls.append((site + '/realestate/properties/', None, '0.9'))
        base = _base_qs(org)
        cities = _cities(org)
        for slug, cat in CATEGORIES.items():
            cat_qs = _apply_filters(base, cat)
            if not cat_qs.exists():
                continue
            urls.append((f"{site}/realestate/properties/{slug}/", None, '0.8'))
            for c in cities:
                if cat_qs.filter(city__iexact=c['name']).exists():
                    urls.append((f"{site}/realestate/properties/{slug}/{c['slug']}/", None, '0.7'))
        for p in base.only('reference_number', 'title', 'city', 'updated_at'):
            urls.append((site + canonical_path(p), p.updated_at, '0.6'))
    body = ['<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lastmod, prio in urls:
        body.append(f"<url><loc>{loc}</loc>" + (f"<lastmod>{lastmod:%Y-%m-%d}</lastmod>" if lastmod else '')
                    + f"<priority>{prio}</priority></url>")
    body.append('</urlset>')
    return _cache_headers(HttpResponse('\n'.join(body), content_type='application/xml'), 900)


@require_GET
def robots(request):
    site = _site_url(request)
    lines = ['User-agent: *', 'Allow: /', 'Allow: /realestate/properties/',
             'Disallow: /api/', 'Disallow: /admin/', 'Disallow: /realestate/properties/chat/',
             'Disallow: /realestate/properties/*/chat/', 'Disallow: /dashboard', 'Disallow: /settings',
             'Disallow: /inbox', '', f'Sitemap: {site}/sitemap.xml']
    return _cache_headers(HttpResponse('\n'.join(lines) + '\n', content_type='text/plain'), 3600)


# ------------------------------------------------------------------------ JSON-LD
def _script_json(data) -> str:
    """JSON safe to inline in <script>: a title like '</script><script>…' cannot break out."""
    return (json.dumps(data, ensure_ascii=False)
            .replace('<', r'\u003c').replace('>', r'\u003e').replace('&', r'\u0026'))


def _org_jsonld(ctx) -> dict:
    org, office = ctx['org'], ctx.get('office')
    data = {'@type': 'RealEstateAgent', '@id': ctx['site'] + '/#agency', 'name': org.name,
            'url': ctx['site'] + '/realestate/properties/', 'areaServed': 'Nepal'}
    if ctx.get('wa_number'):
        data['telephone'] = '+' + ctx['wa_number']
    if office:
        data['address'] = {'@type': 'PostalAddress', 'streetAddress': office.address_line1 or office.name,
                           'addressLocality': office.city or '', 'addressCountry': 'NP'
                           if (office.country or '').lower() == 'nepal' else office.country}
    return data


def _offer(ctx_site, listing, card) -> dict:
    m = market_of(listing)
    currency = {'Rs': 'NPR', '₹': 'INR', 'HK$': 'HKD', '$': 'USD'}.get(m['currency'], 'NPR')
    offer = {'@type': 'Offer', 'price': str(int(listing.price)), 'priceCurrency': currency,
             'availability': 'https://schema.org/InStock' if listing.status in PUBLIC_STATUSES
             else 'https://schema.org/SoldOut', 'url': ctx_site + card['url'],
             'businessFunction': 'http://purl.org/goodrelations/v1#LeaseOut'
             if listing.listing_type in ('rent', 'lease') else 'http://purl.org/goodrelations/v1#Sell'}
    return offer


def _list_jsonld(ctx) -> dict:
    items = [{'@type': 'ListItem', 'position': i + 1, 'url': ctx['site'] + c['url'], 'name': c['obj'].title}
             for i, c in enumerate(ctx['cards'])]
    crumbs = [('Home', '/'), ('Properties', '/realestate/properties/')]
    if ctx['category_obj']:
        crumbs.append((ctx['category_obj']['title'], f"/realestate/properties/{ctx['category']}/"))
    if ctx['city_name']:
        crumbs.append((ctx['city_name'], ctx['canonical'].replace(ctx['site'], '').split('?')[0]))
    return {'@context': 'https://schema.org', '@graph': [
        _org_jsonld(ctx),
        {'@type': 'CollectionPage', 'name': ctx['heading'], 'url': ctx['canonical'],
         'mainEntity': {'@type': 'ItemList', 'numberOfItems': ctx['total'], 'itemListElement': items}},
        {'@type': 'BreadcrumbList', 'itemListElement': [
            {'@type': 'ListItem', 'position': i + 1, 'name': n, 'item': ctx['site'] + u} for i, (n, u) in enumerate(crumbs)]},
        {'@type': 'FAQPage', 'mainEntity': [
            {'@type': 'Question', 'name': q, 'acceptedAnswer': {'@type': 'Answer', 'text': a}} for q, a in FAQ]},
    ]}


def _detail_jsonld(ctx) -> dict:
    l, card = ctx['l'], ctx['card']
    place = {'@type': 'Place', 'name': card['place'] or l.city, 'address': {
        '@type': 'PostalAddress', 'addressLocality': l.city, 'addressRegion': l.state or '',
        'streetAddress': l.neighborhood or l.address_line1, 'addressCountry': 'NP' if (l.country or '').lower() == 'nepal' else l.country}}
    if l.latitude and l.longitude:
        place['geo'] = {'@type': 'GeoCoordinates', 'latitude': float(l.latitude), 'longitude': float(l.longitude)}
    listing = {'@type': 'RealEstateListing', 'name': l.title, 'url': ctx['canonical'],
               'description': ctx['description_text'][:500], 'datePosted': f"{l.created_at:%Y-%m-%d}",
               'image': ctx['images'][:6], 'identifier': l.reference_number, 'contentLocation': place,
               'offers': _offer(ctx['site'], l, card), 'provider': {'@id': ctx['site'] + '/#agency'}}
    if l.square_feet:
        listing['floorSize'] = {'@type': 'QuantitativeValue', 'value': l.square_feet, 'unitCode': 'FTK'}
    return {'@context': 'https://schema.org', '@graph': [
        _org_jsonld(ctx), listing,
        {'@type': 'BreadcrumbList', 'itemListElement': [
            {'@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': ctx['site'] + '/'},
            {'@type': 'ListItem', 'position': 2, 'name': 'Properties', 'item': ctx['site'] + '/realestate/properties/'},
            {'@type': 'ListItem', 'position': 3, 'name': l.title, 'item': ctx['canonical']}]},
    ]}


FAQ = [
    ("How do I book a viewing?",
     "Tap “Chat on WhatsApp” on any listing. Our assistant replies in English or Nepali, shares photos, "
     "checks free viewing times and confirms your visit with a booking code."),
    ("Are the prices final?",
     "Prices shown are the asking price or monthly rent recorded for the listing. Any negotiation is passed "
     "to our team; nothing is agreed until the owner confirms."),
    ("Can I ask in Nepali?",
     "Yes. Write in Nepali (नेपाली) or Romanized Nepali (e.g. “malai kotha chaiyo”) - the reply comes in the "
     "same language."),
    ("Do you charge to view a property?",
     "Viewings are arranged free of charge through WhatsApp. Ask the assistant about any agency fees that "
     "apply to a listing."),
]
