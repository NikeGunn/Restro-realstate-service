"""
Customer vocabulary → structured search criteria.

Customers say "jagga", "जग्गा", "kotha", "ghar", "shutter", "ktm", "patan". The model
is asked to map these itself, but a small deterministic layer here means a missed
mapping can never turn into "no land available" when the agency has land.
Pure functions, no Django imports — easy to test and to extend per market.
"""
import re
from typing import Dict, List, Tuple

# property_type enum value -> words customers use (English, Romanized Nepali, Devanagari)
PROPERTY_TYPE_WORDS: Dict[str, Tuple[str, ...]] = {
    'land': ('land', 'lands', 'plot', 'plots', 'jagga', 'jaggaa', 'jaga', 'जग्गा', 'जमिन', 'jamin',
             'ghaderi', 'घडेरी', 'ropani', 'रोपनी', 'aana', 'ana', 'आना', 'bigha', 'बिघा', 'kattha', 'कट्ठा'),
    'room': ('room', 'rooms', 'kotha', 'kothaa', 'कोठा', 'single room'),
    'apartment': ('flat', 'flats', 'apartment', 'apartments', 'फ्ल्याट', 'फ्लाट', 'bhk', '1bhk', '2bhk', '3bhk'),
    'house': ('house', 'houses', 'ghar', 'gharr', 'घर', 'bungalow', 'banglo', 'bunglow', 'villa'),
    'retail': ('shutter', 'shutters', 'सटर', 'shop', 'pasal', 'पसल', 'dokan'),
    'office': ('office', 'offices', 'अफिस', 'karyalaya'),
    'commercial': ('commercial', 'business space', 'godown', 'warehouse', 'गोदाम'),
}

LISTING_TYPE_WORDS: Dict[str, Tuple[str, ...]] = {
    'sale': ('sale', 'sell', 'buy', 'buying', 'purchase', 'kinna', 'kinne', 'kinnu', 'kinda', 'किन्ने',
             'किन्न', 'bikri', 'बिक्री', 'bechna', 'bechne', 'बेच्ने'),
    'rent': ('rent', 'rental', 'lease', 'bhada', 'bhadama', 'vada', 'bhaada', 'भाडा', 'भाडामा', 'tenant'),
}

# Common ways people name districts / areas -> the name used on listings.
AREA_ALIASES: Dict[str, str] = {
    'ktm': 'Kathmandu', 'kathmandu valley': '', 'valley': '', 'काठमाडौं': 'Kathmandu', 'काठमाण्डौ': 'Kathmandu',
    'patan': 'Lalitpur', 'ललितपुर': 'Lalitpur', 'पाटन': 'Lalitpur',
    'bkt': 'Bhaktapur', 'भक्तपुर': 'Bhaktapur',
    'पोखरा': 'Pokhara', 'चितवन': 'Chitwan', 'bharatpur': 'Chitwan', 'भरतपुर': 'Chitwan',
    'कीर्तिपुर': 'Kirtipur', 'किर्तिपुर': 'Kirtipur', 'बानेश्वर': 'Baneshwor', 'baneshwar': 'Baneshwor',
    'कोटेश्वर': 'Koteshwor', 'koteshwar': 'Koteshwor', 'चाबहिल': 'Chabahil', 'कलंकी': 'Kalanki',
    'बुटवल': 'Butwal', 'विराटनगर': 'Biratnagar', 'धरान': 'Dharan', 'हेटौंडा': 'Hetauda',
}

# Words that carry no search meaning on their own.
STOPWORDS = {
    'a', 'an', 'the', 'in', 'at', 'on', 'for', 'near', 'with', 'and', 'or', 'of', 'to', 'any', 'some',
    'cheap', 'cheapest', 'affordable', 'budget', 'best', 'good', 'nice', 'available', 'please',
    'ma', 'tira', 'najik', 'nera', 'ko', 'ka', 'ki', 'ra', 'ni', 'pani', 'chahiyo', 'chaiyo', 'chahiyeko',
    'sasto', 'ramro', 'kati', 'xa', 'cha', 'chha', 'हो', 'मा', 'तिर', 'नजिक', 'सस्तो', 'चाहियो',
}

_TOKEN_RE = re.compile(r'[\wऀ-ॿ]+', re.UNICODE)

_WORD_TO_TYPE = {w: t for t, words in PROPERTY_TYPE_WORDS.items() for w in words}
_WORD_TO_LISTING = {w: t for t, words in LISTING_TYPE_WORDS.items() for w in words}


def tokens(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or '')]


def normalize_property_type(value: str, valid: set) -> str:
    """'jagga' -> 'land', 'Room' -> 'room', 'kotha' -> 'room'. Unknown -> ''."""
    v = (value or '').strip().lower()
    if not v:
        return ''
    if v in valid:
        return v
    if v in _WORD_TO_TYPE:
        return _WORD_TO_TYPE[v]
    for tok in tokens(v):
        if tok in _WORD_TO_TYPE:
            return _WORD_TO_TYPE[tok]
    return ''


def normalize_listing_type(value: str) -> str:
    v = (value or '').strip().lower()
    if v in ('sale', 'buy', 'rent', 'lease'):
        return 'sale' if v in ('sale', 'buy') else 'rent'
    for tok in tokens(v):
        if tok in _WORD_TO_LISTING:
            return _WORD_TO_LISTING[tok]
    return ''


def normalize_area(value: str) -> str:
    v = (value or '').strip()
    return AREA_ALIASES.get(v.lower(), v)


def split_keywords(keywords: str) -> Tuple[List[str], str, str]:
    """
    Pull type / listing words out of free-text keywords.
    Returns (remaining_search_words, inferred_property_type, inferred_listing_type).
    """
    words, ptype, ltype = [], '', ''
    for tok in tokens(keywords):
        if tok in _WORD_TO_TYPE:
            ptype = ptype or _WORD_TO_TYPE[tok]
        elif tok in _WORD_TO_LISTING:
            ltype = ltype or _WORD_TO_LISTING[tok]
        elif tok not in STOPWORDS and len(tok) > 1 and not tok.isdigit():
            words.append(tok)
    return words, ptype, ltype
