"""
Deterministic reply-language decision for the agent.

The shared LanguageService only knows en / zh-CN / zh-TW, so "Maile jagga ko barema
sodhnu thio" was labelled English and the agent answered in English. Script and
Romanized-Nepali detection here is cheap and exact; the result is passed to the model
as an explicit instruction instead of a hint it can ignore.
"""
import re

_DEVANAGARI = re.compile(r'[ऀ-ॿ]')
_LATIN = re.compile(r'[A-Za-z]')
_WORD = re.compile(r"[a-z]+")

# Words that are distinctly Nepali when written in Latin letters (not English words).
STRONG = {
    'malai', 'maile', 'mailai', 'hajur', 'tapai', 'tapain', 'tapailai', 'chahiyo', 'chaiyo', 'chahiyeko',
    'chaiyeko', 'chainxa', 'chahincha', 'kotha', 'jagga', 'ghar', 'bhada', 'vada', 'kati', 'hola', 'xa', 'cha',
    'chha', 'chan', 'xan', 'huncha', 'hunxa', 'hunchha', 'garnu', 'garna', 'garne', 'garchu', 'garxu',
    'milcha', 'milxa', 'sasto', 'mahango', 'kaha', 'kahan', 'kun', 'kasto', 'kina', 'thiyo', 'thio',
    'sodhnu', 'sodhna', 'upalabdha', 'barema', 'baare', 'najik', 'nera', 'tira', 'dekhi', 'samma', 'dinu',
    'dinus', 'dinuhos', 'namaste', 'dhanyabad', 'dhanyavad', 'thik', 'hernu', 'herna', 'jaana',
    'bhanda', 'ekdam', 'ali', 'pani', 'haru', 'sanga', 'ramro',
    'ani', 'yo', 'tyo', 'yaha', 'tyaha', 'chhaina', 'chaina', 'xaina', 'parcha', 'parxa',
}
# Short words also used in English text; they only count alongside a strong word.
WEAK = {'ma', 'ho', 'ra', 'ko', 'ka', 'ki', 'ni', 'ta', 'la', 'na'}

NEPALI_DEVANAGARI = 'ne-deva'
NEPALI_ROMAN = 'ne-latn'


def detect_reply_style(text: str, fallback: str = 'en') -> str:
    """Return 'ne-deva', 'ne-latn', or the shared detector's code (en/zh-CN/zh-TW)."""
    text = text or ''
    deva = len(_DEVANAGARI.findall(text))
    latin = len(_LATIN.findall(text))
    if deva and deva >= latin * 0.5:
        return NEPALI_DEVANAGARI
    words = _WORD.findall(text.lower())
    strong = sum(1 for w in words if w in STRONG)
    weak = sum(1 for w in words if w in WEAK)
    if words and (strong >= 2 or (strong == 1 and (weak >= 1 or len(words) <= 3))):
        return NEPALI_ROMAN
    return fallback


INSTRUCTIONS = {
    NEPALI_DEVANAGARI: ("Nepali in Devanagari script (नेपाली). Write the whole reply in Devanagari; keep "
                        "listing titles, reference codes and prices exactly as the tool gave them."),
    NEPALI_ROMAN: ("Romanized Nepali — Nepali words in Latin letters, the way the customer writes "
                   "(e.g. \"Hajur, Bhaisepati ma 5 aana jagga cha, mol Rs 2,10,00,000 (2.1 crore) ho.\"). "
                   "Do NOT answer in English."),
    'en': "English.",
    'zh-CN': "Simplified Chinese (简体中文).",
    'zh-TW': "Traditional Chinese (繁體中文, Cantonese tone is fine).",
}

DISPLAY = {NEPALI_DEVANAGARI: 'Nepali (Devanagari)', NEPALI_ROMAN: 'Romanized Nepali'}


def instruction_for(style: str) -> str:
    return INSTRUCTIONS.get(style, INSTRUCTIONS['en'])


# Function words that only appear in real English sentences.
ENGLISH_MARKERS = {
    'i', 'you', 'we', 'my', 'me', 'your', 'is', 'are', 'am', 'was', 'do', 'does', 'did', 'have', 'has', 'what',
    'where', 'which', 'when', 'how', 'can', 'could', 'would', 'please', 'want', 'need', 'looking', 'the', 'any',
    'show', 'tell', 'about', 'under', 'yes', 'no', 'ok', 'okay', 'thanks', 'thank', 'hi', 'hello', 'book',
}


def is_neutral(text: str) -> bool:
    """'10000', 'Kirtipur', 'PROP123456' — no language signal of its own."""
    words = _WORD.findall((text or '').lower())
    return not _DEVANAGARI.search(text or '') and len(words) <= 3 and not (set(words) & (ENGLISH_MARKERS | STRONG))


def sticky_reply_style(current: str, previous_customer_texts, fallback: str = 'en') -> str:
    """A neutral reply ("10000") keeps the language the customer was already using."""
    style = detect_reply_style(current, fallback=fallback)
    if style == fallback and is_neutral(current):
        for text in reversed(list(previous_customer_texts)):
            if not is_neutral(text):
                return detect_reply_style(text, fallback=fallback)
    return style
