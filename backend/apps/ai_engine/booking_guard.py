"""
Restaurant booking claims must match reality.

The restaurant path asks the model for JSON (reply + extracted booking data); the channel
creates the booking afterwards. The model used to write "your table has been booked" when
date/time were missing, so no booking existed (prod screenshot, 2026-06-20). Two
deterministic checks close that gap for every channel:

  * before delivery (`guard_reply`): a booking claim with incomplete data is replaced by a
    question for exactly the missing fields — everything already given is kept;
  * after the booking service ran (`apply_receipt`): the reply quotes the real confirmation
    code, or — if no booking was created — never claims one.
"""
import re
from typing import Any, Dict, List, Optional

from .agent import language as reply_lang

CLAIM_RE = re.compile(
    r"\b(table|booking|reservation|seat)s?\b[^.!?\n]{0,60}\b(booked|confirmed|reserved|successful(ly)?)\b"
    r"|\b(booked|confirmed|reserved)\b[^.!?\n]{0,40}\b(table|booking|reservation)\b"
    r"|已(為你|为你|為您|为您)?(預訂|预订|預約|预约|確認|确认)", re.I)
REQUIRED = ('date', 'time', 'party_size', 'customer_name')
FIELD_NAMES = {
    'en': {'date': 'the date', 'time': 'the time', 'party_size': 'how many people', 'customer_name': 'the name'},
    reply_lang.NEPALI_ROMAN: {'date': 'kun din', 'time': 'kati baje', 'party_size': 'kati jana',
                              'customer_name': 'kasko naam ma'},
    'zh': {'date': '日期', 'time': '時間', 'party_size': '人數', 'customer_name': '訂座名稱'},
}


def _style(text: str, language: str) -> str:
    style = reply_lang.detect_reply_style(text, fallback=language)
    return 'zh' if style in ('zh-CN', 'zh-TW') else (style if style in FIELD_NAMES else 'en')


def missing_fields(extracted: Dict[str, Any]) -> List[str]:
    return [f for f in REQUIRED if not extracted.get(f)]


def guard_reply(parsed: Dict[str, Any], conversation, user_message: str) -> Dict[str, Any]:
    """Replace a premature 'booked' claim with a question for what is still missing."""
    extracted = parsed.setdefault('extracted_data', {}) or {}
    if extracted.get('booking_intent') and conversation.customer_phone and not extracted.get('customer_phone'):
        extracted['customer_phone'] = conversation.customer_phone  # verified channel identity
    if not CLAIM_RE.search(parsed.get('content') or ''):
        return parsed
    missing = missing_fields(extracted) if extracted.get('booking_intent') else list(REQUIRED)
    if extracted.get('booking_intent') and not missing:
        return parsed  # complete: the booking service runs next and apply_receipt checks the result
    style = _style(user_message, parsed.get('language', 'en'))
    names = [FIELD_NAMES[style][f] for f in (missing or ['date', 'time'])]
    known = []
    if extracted.get('party_size'):
        known.append(f"{extracted['party_size']}")
    if extracted.get('customer_name'):
        known.append(str(extracted['customer_name']))
    parsed['content'] = {
        'en': (f"Happy to book that{' (' + ', '.join(known) + ')' if known else ''}. "
               f"To check availability I still need {' and '.join(names)}."),
        reply_lang.NEPALI_ROMAN: (f"Huncha{' (' + ', '.join(known) + ')' if known else ''}. Table check garna "
                                  f"{', '.join(names)} bhannus na."),
        'zh': f"好的{'（' + '、'.join(known) + '）' if known else ''}。請告訴我{'、'.join(names)}，我先查看是否有位。",
    }[style]
    parsed['booking_claim_blocked'] = True
    return parsed


def apply_receipt(ai_response: Dict[str, Any], booking: Optional[Any], failure: str = '') -> None:
    """After the booking service: quote the real code, or remove a claim that has no booking."""
    content = ai_response.get('content') or ''
    if booking:
        code = getattr(booking, 'confirmation_code', '')
        if code and code not in content:
            ai_response['content'] = (content + f"\n\nConfirmation code: {code}").strip()
        return
    if CLAIM_RE.search(content):
        ai_response['content'] = ("I couldn't complete that booking yet"
                                  + (f": {failure}" if failure else '') + ". Nothing has been reserved. "
                                  "Would you like me to try another time or connect you with our team?")
