"""
Register (respect) gate for customer replies.

Customers are addressed in the honorific register in every language: hajur/tapai and
-nuhunchha/-nuhola verbs in Nepali (both scripts), courteous full sentences in English,
您 in Chinese. The model mirrors casual customer messages ("kotha chaiyo") and drifts into
low forms ("Aru sodhna cha?"), so tone is not left to the prompt alone:

  register_problems()  deterministic detector, run on every draft → one rewrite pass
  polish()             safe, exact phrase upgrades applied to every outgoing reply

Patterns are deliberately narrow (high precision): a false alarm costs one extra model
call, a missed one costs the customer's goodwill — the rewrite pass + polish cover both.
"""
import re
from typing import List, Tuple

from .language import NEPALI_DEVANAGARI, NEPALI_ROMAN

_I = re.IGNORECASE
_HONORIFIC_TAIL = r'(?!\s*(?:hola|hos|huncha|hunchha|hunxa|bhayo|parchha|parcha))'

# (pattern, what is wrong) — Romanized Nepali.
_LOW_ROMAN: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'\b(?:aru|arko)\s+(?:kehi\s+)?sodhna\s+(?:cha|chha|xa)\b', _I),
     '"Aru sodhna cha?" is curt — use "Aru kehi jannu parne bhaye sodhnuhola."'),
    (re.compile(r'\bsodhna\s+(?:cha|chha|xa)\s*\?', _I), '"sodhna cha?" — use "sodhnu hunchha?"'),
    (re.compile(r'\bherna\s+(?:man\s+)?(?:cha|chha|xa)\s*\?', _I),
     '"herna man cha?" — use "herna jaana chahanuhunchha?"'),
    (re.compile(r'\b(?:timi|timilai|timle|timro|timrai)\b', _I), 'timi/timro is low register — use tapai/hajur'),
    (re.compile(r'\b\w+(?:chau|chhau|xau)\b', _I), 'timi-level verb ending (-chau) — use -nuhunchha'),
    (re.compile(r'\b(?:bhana|gara|hera|sodha)\b(?=\s*[.!?]|\s*$)', _I),
     'bare imperative (bhana/gara) — use bhannuhola / garnuhos'),
    (re.compile(r'\bbhanidinu\b' + _HONORIFIC_TAIL, _I), '"bhanidinu" as a command — use "bhanidinuhola"'),
    (re.compile(r'\b(?:chahincha|chahinchha|chaincha|chainxa)\s*\?', _I),
     '"...chahincha?" to the customer — use "...chahinchha hola?"'),
    (re.compile(r'(?:^|\n)\s*aru\s+kehi\s*\?\s*(?:$|\n)', _I), '"Aru kehi?" alone is curt'),
]

_LOW_DEVANAGARI: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'तिमी|तिम्रो|तँ\b|तेरो'), 'तिमी/तिम्रो is low register — use तपाईं/हजुर'),
    (re.compile(r'सोध्न\s*छ\s*\?'), '"सोध्न छ?" — use "सोध्नुहुन्छ?"'),
    (re.compile(r'हेर्न\s*(?:मन\s*)?छ\s*\?'), '"हेर्न मन छ?" — use "हेर्न जान चाहनुहुन्छ?"'),
    (re.compile(r'\S+(?:छौ|दैनौ)(?=[\s?।!.]|$)'), 'timi-level verb ending (-छौ) — use -नुहुन्छ'),
    (re.compile(r'(?:^|\s)(?:भन|गर|हेर)\s*[।!.]'), 'bare imperative (भन/गर) — use भन्नुहोला / गर्नुहोस्'),
]

_LOW_ENGLISH: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'(?:^|\n)\s*(?:anything else|budget|date|name|area|and)\s*\?\s*(?:$|\n)', _I),
     'one-word question is curt — ask in a full, polite sentence'),
    (re.compile(r'(?:^|[.!?]\s+|\n)tell me\b', _I), '"Tell me ..." — use "Could you please tell me ..."'),
    (re.compile(r'\bwhat do you want\b', _I), '"What do you want" — use "How may I help you"'),
]

_LOW_CHINESE: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'你(?![們们])'), '你 — address the customer as 您'),
]


def register_problems(reply: str, style: str) -> List[str]:
    """Low-register phrases in a draft, for the reply language `style`."""
    if not reply:
        return []
    if style == NEPALI_ROMAN:
        rules = _LOW_ROMAN
    elif style == NEPALI_DEVANAGARI:
        rules = _LOW_DEVANAGARI + _LOW_ROMAN  # mixed-script replies happen
    elif style in ('zh-CN', 'zh-TW'):
        rules = _LOW_CHINESE
    else:
        rules = _LOW_ENGLISH
    found = []
    for pattern, problem in rules:
        if pattern.search(reply) and problem not in found:
            found.append(problem)
    return found


def _cap(repl: str):
    """Keep a sentence-initial capital when the matched text had one."""
    def sub(m):
        return repl[:1].upper() + repl[1:] if m.group(0)[:1].isupper() else repl
    return sub


# Exact, meaning-preserving upgrades. Ordered: longer phrases first.
_POLISH_ROMAN = [
    (re.compile(r'\b(aru|arko)\s+(?:kehi\s+)?sodhna\s+(?:cha|chha|xa)\b\s*\??', _I),
     _cap('aru kehi jannu parne bhaye sodhnuhola.')),
    (re.compile(r'\bsodhna\s+(?:cha|chha|xa)\s*\?', _I), _cap('sodhnu hunchha?')),
    (re.compile(r'\bherna\s+man\s+(?:cha|chha|xa)\s*\?', _I), _cap('herna jaana chahanuhunchha?')),
    (re.compile(r'\bbhanidinu\b' + _HONORIFIC_TAIL, _I), _cap('bhanidinuhola')),
    (re.compile(r'\b(chahincha|chahinchha|chaincha|chainxa)\s*\?', _I), _cap('chahinchha hola?')),
    (re.compile(r'\btimilai\b', _I), _cap('tapailai')),
    (re.compile(r'\btimle\b', _I), _cap('tapai le')),
    (re.compile(r'\btimro\b', _I), _cap('tapai ko')),
    (re.compile(r'\btimi\b', _I), _cap('tapai')),
    (re.compile(r'\bbhana\b(?=\s*[.!]|\s*$)', _I), _cap('bhannuhola')),
    (re.compile(r'(?:^|(?<=\n))(\s*)aru\s+kehi\s*\?\s*(?=$|\n)', _I),
     lambda m: m.group(1) + 'Aru kehi jannu parne bhaye sodhnuhola.'),
]
_POLISH_DEVANAGARI = [
    (re.compile(r'अरू\s*(?:केही\s*)?सोध्न\s*छ\s*\?'), 'अरू केही जान्नुपर्ने भए सोध्नुहोला।'),
    (re.compile(r'सोध्न\s*छ\s*\?'), 'सोध्नुहुन्छ?'),
    (re.compile(r'हेर्न\s*मन\s*छ\s*\?'), 'हेर्न जान चाहनुहुन्छ?'),
    (re.compile(r'तिमीलाई'), 'तपाईंलाई'),
    (re.compile(r'तिम्रो'), 'तपाईंको'),
    (re.compile(r'तिमी'), 'तपाईं'),
]
_POLISH_ENGLISH = [
    (re.compile(r'(?:^|(?<=\n))(\s*)anything else\s*\?\s*(?=$|\n)', _I),
     lambda m: m.group(1) + 'Is there anything else I can help you with?'),
    (re.compile(r'(^|[.!?]\s+|\n)tell me\b', _I), lambda m: m.group(1) + 'Could you please tell me'),
]
_POLISH_CHINESE = [(re.compile(r'你(?![們们])'), '您')]


def polish(reply: str, style: str) -> str:
    """Apply safe honorific upgrades. Never changes numbers, codes or listing names."""
    if not reply:
        return reply
    if style == NEPALI_ROMAN:
        rules = _POLISH_ROMAN
    elif style == NEPALI_DEVANAGARI:
        rules = _POLISH_DEVANAGARI + _POLISH_ROMAN
    elif style in ('zh-CN', 'zh-TW'):
        rules = _POLISH_CHINESE
    else:
        rules = _POLISH_ENGLISH
    for pattern, repl in rules:
        reply = pattern.sub(repl, reply)
    return reply


def no_dashes(text: str) -> str:
    """House style: no em/en dashes in any chat message (they read as machine-written)."""
    if not text:
        return text
    return (text.replace(' \u2014 ', ' - ').replace('\u2014', '-')
            .replace(' \u2013 ', ' - ').replace('\u2013', '-'))


def rewrite_instruction(problems: List[str]) -> str:
    return ("TONE CHECK FAILED — your reply was NOT sent: " + "; ".join(problems)
            + ". Rewrite the SAME reply in the respectful register from the TONE section (hajur/tapai, "
              "-nuhunchha/-nuhola verbs; courteous full sentences in English; 您 in Chinese). Keep every fact, "
              "number, price, reference code, date and list item exactly as it is. Output only the rewritten reply.")
