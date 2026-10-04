"""
Vertical isolation: a real-estate customer must never hear about menus or tables, and a restaurant
guest must never hear about listings or viewings.

Root cause (prod 2026-10-04, org converted restaurant -> real estate):
  1. The restaurant inventory firewall ran for every org: "afno storage ma hernu" got
     "I can help you with our menu, opening hours, bookings..." on a land agency. (services.py now
     runs it for restaurants only.)
  2. The customer's long-term memory summary was built from EVERY conversation of that phone,
     including archived restaurant chats and an old Hong Kong portfolio ("restaurant booking",
     "vegan friend", "PROP958917 HK$32,000"), and was injected into every prompt unfiltered.

Defence in depth, all deterministic:
  * `off_vertical()` - vocabulary that belongs only to the OTHER vertical, unless the customer used
    it first ("menu paam na" -> "I can't share a menu, I'm a property consultant" is fine).
    The real-estate agent treats a hit as a failed verification (corrective retry); the shared
    AIService exit replaces any reply that still leaks with a neutral, in-vertical line.
  * `clean_memory()` - drops memory lines about the other vertical, unknown listing references and
    foreign currencies before they reach the prompt.
"""
import logging
import re
from typing import Iterable, List

logger = logging.getLogger(__name__)

REAL_ESTATE = 'real_estate'
RESTAURANT = 'restaurant'

# Words that only the OTHER vertical would ever say. Kept tight on purpose: "water supply", "kitchen",
# "vegetarian only" (a landlord rule) and office "opening hours" are normal property talk.
_RESTAURANT_ONLY = re.compile(
    r"\b(menu|menus|dishes|cuisine|chef|dine-?in|takeaway|coffee pass|lucky draw|cocktails?|appetizers?|dietary|"
    r"(?:book|reserve)\s+(?:a\s+)?table|table\s+(?:booking|reservation|for\s+\d+)|restaurant)\b|मेनु|मेनू|रेस्टुरेन्ट",
    re.I)
_REAL_ESTATE_ONLY = re.compile(
    r"\bPROP\d{6}\b|\b(property listings?|viewing|lalpurja|ropani|kattha|landlord|real estate|jagga|"
    r"for sale|per month rent)\b|जग्गा|घरजग्गा",
    re.I)

_FOREIGN = {REAL_ESTATE: _RESTAURANT_ONLY, RESTAURANT: _REAL_ESTATE_ONLY}

SAFE = {
    REAL_ESTATE: {
        'en': "I'm the property assistant for {org}. I can help you find rooms, flats, houses, shops and land, "
              "and arrange viewings. What are you looking for?",
        'ne-latn': "Hajur, ma {org} ko property sahayak hu. Kotha, flat, ghar, shutter ra jagga khojna ra herna "
                   "milauna sahayog garchhu. Ke khojnu bhayeko ho?",
        'ne-deva': "हजुर, म {org} को प्रोपर्टी सहायक हुँ। कोठा, फ्ल्याट, घर, सटर र जग्गा खोज्न सहयोग गर्छु। के खोज्नुभएको हो?",
    },
    RESTAURANT: {
        'en': "I'm the assistant for {org}. I can help with our menu, opening hours and table bookings. "
              "How can I help?",
    },
}


def _family(business_type: str) -> str:
    return REAL_ESTATE if business_type == REAL_ESTATE else RESTAURANT


def off_vertical(business_type: str, reply: str, customer_texts: Iterable[str] = ()) -> List[str]:
    """Other-vertical words in the reply that the customer did not use themselves."""
    pattern = _FOREIGN[_family(business_type)]
    said = ' '.join(customer_texts or []).lower()
    hits = []
    for m in pattern.finditer(reply or ''):
        word = m.group(0).lower()
        if word not in said and word not in hits:
            hits.append(word)
    return hits


def safe_reply(business_type: str, org_name: str, style: str = 'en') -> str:
    table = SAFE[_family(business_type)]
    return (table.get(style) or table['en']).format(org=org_name)


def enforce(organization, reply: str, customer_text: str, style: str = 'en') -> str:
    """Last line of defence for EVERY AI reply, whatever path produced it."""
    hits = off_vertical(organization.business_type, reply, [customer_text])
    if not hits:
        return reply
    logger.error("Vertical guard blocked a %s reply for org %s (words: %s): %s",
                 organization.business_type, organization.id, hits, (reply or '')[:300])
    return safe_reply(organization.business_type, organization.name, style)


_REF_RE = re.compile(r'\bPROP\d{6}\b', re.I)
_CURRENCY_RE = re.compile(r'HK\$|HK₨|US\$|₹|\$|₨|NPR|Rs\.?|रु', re.I)


def clean_memory(text: str, business_type: str, known_refs: Iterable[str], currency: str = '') -> str:
    """Drop memory lines a stale or foreign past would poison the prompt with."""
    if not text:
        return text
    known = {r.upper() for r in known_refs}
    pattern = _FOREIGN[_family(business_type)]
    kept = []
    for line in text.splitlines():
        if pattern.search(line):
            continue
        refs = {r.upper() for r in _REF_RE.findall(line)}
        if refs and not refs <= known:
            continue
        if currency and business_type == REAL_ESTATE:
            used = {c.upper().rstrip('.') for c in _CURRENCY_RE.findall(line)}
            mine = {currency.upper().rstrip('.')} | ({'NPR', 'RS', 'रु'} if currency.upper().startswith('RS') else set())
            if used - mine:
                continue
        kept.append(line)
    return "\n".join(kept)
