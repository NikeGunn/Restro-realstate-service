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
    'ajhai', 'ahile', 'aile', 'aba', 'abo', 'esko', 'yesko', 'tesko', 'mero', 'hamro', 'timro', 'bholi',
    'parsi', 'hijo', 'baje', 'dinchha', 'dinchhau', 'milchha', 'herna', 'jane', 'gara', 'garnu', 'bhannus',
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
    english = sum(1 for w in words if w in ENGLISH_MARKERS)
    if words and (strong >= 2 or (strong == 1 and (weak >= 1 or len(words) <= 3 or not english))):
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


# Deterministic wording for completed actions — the customer is told what the RECEIPT says.
_RECEIPT = {
    'book_viewing': {
        'confirmed': {
            'en': "Confirmed: viewing {code} — {property}, {weekday} {date} at {time} ({timezone}).",
            NEPALI_ROMAN: "Confirm bhayo: viewing {code} — {property}, {weekday} {date}, {time} baje ({timezone}).",
            NEPALI_DEVANAGARI: "पक्का भयो: भ्यूइङ {code} — {property}, {weekday} {date}, {time} बजे ({timezone})।",
            'zh': "已確認：睇樓 {code} — {property}，{date}（{weekday}）{time}（{timezone}）。",
        },
        'pending_staff_approval': {
            'en': "Request sent: viewing {code} — {property}, {weekday} {date} at {time} ({timezone}). "
                  "Our team still needs to approve it; it is not confirmed yet.",
            NEPALI_ROMAN: "Request pathaiyo: viewing {code} — {property}, {weekday} {date}, {time} baje. "
                          "Team le approve garna baki chha; ajhai confirm bhayeko chhaina.",
            NEPALI_DEVANAGARI: "अनुरोध पठाइयो: भ्यूइङ {code} — {property}, {weekday} {date}, {time} बजे। "
                               "टिमले स्वीकृत गर्न बाँकी छ; अझै पक्का भएको छैन।",
            'zh': "已提交申請：睇樓 {code} — {property}，{date} {time}。仍待職員確認，尚未確認。",
        },
    },
    'cancel_appointment': {
        'cancelled': {'en': "Cancelled: appointment {code}.", NEPALI_ROMAN: "Appointment {code} cancel bhayo.",
                      NEPALI_DEVANAGARI: "अपोइन्टमेन्ट {code} रद्द भयो।", 'zh': "已取消預約 {code}。"},
    },
    'reschedule_appointment': {
        '*': {'en': "Updated: {code} is now on {weekday} {date} at {time} ({timezone}).",
              NEPALI_ROMAN: "Update bhayo: {code} aba {weekday} {date}, {time} baje ({timezone}).",
              NEPALI_DEVANAGARI: "परिवर्तन भयो: {code} अब {weekday} {date}, {time} बजे ({timezone})।",
              'zh': "已更改：{code} 改為 {date}（{weekday}）{time}（{timezone}）。"},
    },
}


def receipt_line(receipt: dict, style: str) -> str:
    by_status = _RECEIPT.get(receipt.get('action'), {})
    templates = by_status.get(receipt.get('status')) or by_status.get('*') or {}
    key = 'zh' if style in ('zh-CN', 'zh-TW') else style
    template = templates.get(key) or templates.get('en') or "Done: {code}."
    fields = {k: '' for k in ('code', 'property', 'weekday', 'date', 'time', 'timezone')}
    fields.update({k: v for k, v in receipt.items() if v is not None})
    return template.format(**fields)


def busy_message(style: str) -> str:
    return {
        NEPALI_ROMAN: "Hajur, ahile hamro team le tapai ko message herchha — chadai reply aauchha.",
        NEPALI_DEVANAGARI: "हजुर, अहिले हाम्रो टिमले तपाईंको सन्देश हेर्छ — चाँडै जवाफ आउँछ।",
    }.get(style, "Thanks for your message — our team will reply to you here.")
