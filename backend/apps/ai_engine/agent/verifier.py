"""
Pre-delivery verification gate.

Deterministic checks run on every draft reply BEFORE it reaches the customer.
The model's own confidence is never trusted; a reply is sent only if every
reference code and money figure it states is present in the evidence (tool
results + knowledge in the prompt) and every action it claims was actually
performed by a tool this turn.
"""
import re
from dataclasses import dataclass, field
from typing import Iterable, List, Set

REF_RE = re.compile(r'\bPROP\d{6}\b', re.I)
APPT_RE = re.compile(r'\bAPT[A-Z0-9]{6}\b', re.I)
# HK$1,234,567 · $32,000 · HKD 5.98M · 42,000,000 港元 · Rs 12,000 · NRs 12,000 · ₨ 9,500 · HK₨ 7,500 (sic)
# NPR 1,85,00,000 · रु. 50 लाख · 1.85 crore · 15 hajar · 12,000/month · 12000 per month
UNIT = r'(million|m\b|萬|万|k\b|lakhs?|lacs?|crores?|cr\b|लाख|करोड|hajar|hazar|हजार)'
CURRENCY = r'(?:HK\$|HK₨|HKD\s?|US\$|\$|港幣|港元|NRs\.?|Rs\.?|₨|₹|INR\s?|NPR|रु\.?|रू\.?)'
MONEY_RE = re.compile(
    CURRENCY + r'\s?(\d[\d,]*(?:\.\d+)?)\s*' + UNIT + r'?'
    r'|(\d[\d,]*(?:\.\d+)?)\s*' + UNIT + r'?\s*(?:港元|港幣|HKD|NPR|rupees|rupiya|रुपैयाँ)'
    r'|(\d[\d,]*(?:\.\d+)?)\s*(lakhs?|lacs?|crores?|लाख|करोड|hajar|hazar|हजार)'
    r'|(\d[\d,]*(?:\.\d+)?)()\s*(?:/\s?(?:month|mo|mahina)\b|per\s+month|a\s+month|monthly|प्रति\s?महिना)',
    re.I,
)
# Any standalone figure of 4+ digits (prices, sizes) must be backed by evidence too,
# whatever currency word the model chose (or forgot). Dates/times are excluded.
# Phone-like runs (9+ bare digits, or after '+') and codes such as PROP958917 are not figures.
BIG_NUMBER_RE = re.compile(r'(?<![\w\-:/.+])(\d{1,3}(?:,\d{2,3})+|\d{4,8})(?:\.\d+)?(?![\w\-:/])')
ISO_DATE_RE = re.compile(r'\b\d{4}-\d{2}-\d{2}\b')
NUMBER_RE = re.compile(r'\d[\d,]*(?:\.\d+)?')

BOOKED_CLAIM_RE = re.compile(
    r"(viewing|appointment|visit|tour)[^.!?\n]{0,60}\b(is |has been |are )?(booked|confirmed|scheduled|reserved)\b"
    r"|\b(booked|confirmed|scheduled|reserved)\b[^.!?\n]{0,40}(viewing|appointment|visit|tour)"
    r"|已(為你|为你|為您|为您)?(預約|预约|確認|确认|安排)",
    re.I,
)
CANCEL_CLAIM_RE = re.compile(r"\b(has been|is now|successfully) cancel+ed\b|已(取消)", re.I)


_HEDGE_RE = re.compile(r"(\bnot\b|n't|\byet\b|\bonce\b|\bafter\b|\bwill\b|\bwould\b|\bshall\b|\bcan\b|\bif\b|"
                       r"\bbefore\b|\bto be\b|\?|hoina|chhaina|chaina|छैन|未|尚未|會|会)", re.I)


def _asserted(pattern, reply: str) -> bool:
    """A real claim — not "not booked yet", "once you confirm it will be booked", or a question."""
    for m in pattern.finditer(reply):
        line_start = reply.rfind('\n', 0, m.start()) + 1
        line_end = reply.find('\n', m.end())
        line = reply[line_start:line_end if line_end != -1 else len(reply)]
        sentence = next((s for s in re.split(r'(?<=[.!。！])\s', line) if m.group(0) in s), line)
        if not _HEDGE_RE.search(sentence):
            return True
    return False


def _to_number(raw: str, unit: str = '') -> float:
    value = float(raw.replace(',', ''))
    unit = (unit or '').lower()
    if unit in ('million', 'm'):
        value *= 1_000_000
    elif unit in ('萬', '万'):
        value *= 10_000
    elif unit == 'k':
        value *= 1_000
    elif unit.startswith(('lakh', 'lac')) or unit == 'लाख':
        value *= 100_000
    elif unit.startswith('crore') or unit in ('cr', 'करोड'):
        value *= 10_000_000
    elif unit in ('hajar', 'hazar', 'हजार'):
        value *= 1_000
    return value


SCALED_RE = re.compile(r'(\d[\d,]*(?:\.\d+)?)\s*(million|mil|m\b|萬|万|k\b|lakhs?|lacs?|crores?|cr\b|लाख|करोड|hajar|hazar|हजार)', re.I)


def evidence_numbers(texts: Iterable[str]) -> Set[float]:
    nums: Set[float] = set()
    for text in texts:
        for raw in NUMBER_RE.findall(text or ''):
            try:
                nums.add(round(float(raw.replace(',', '')), 2))
            except ValueError:
                continue
        for raw, unit in SCALED_RE.findall(text or ''):  # "9 million", "18.8M", "900萬"
            try:
                nums.add(round(_to_number(raw, 'million' if unit.lower() == 'mil' else unit), 2))
            except ValueError:
                continue
    return nums


@dataclass
class GateResult:
    ok: bool = True
    problems: List[str] = field(default_factory=list)
    offending: List[str] = field(default_factory=list)  # exact substrings that failed
    fatal: bool = False  # false action claims can't be fixed by trimming sentences

    def fail(self, problem: str, span: str = '', fatal: bool = False):
        self.ok = False
        self.problems.append(problem)
        if span:
            self.offending.append(span)
        self.fatal = self.fatal or fatal or not span


def verify_reply(reply: str, evidence: List[str], actions: List[dict],
                 has_existing_appointments: bool = False) -> GateResult:
    result = GateResult()
    blob = "\n".join(evidence)
    upper_blob = blob.upper()

    for ref in {r.upper() for r in REF_RE.findall(reply)}:
        if ref not in upper_blob:
            result.fail(f"reference {ref} does not exist in any tool result", span=ref)

    for code in {c.upper() for c in APPT_RE.findall(reply)}:
        if code not in upper_blob:
            result.fail(f"confirmation code {code} was not returned by a tool", fatal=True)

    known = evidence_numbers(evidence)
    checked: Set[float] = set()
    for m in MONEY_RE.finditer(reply):
        raw, unit = next(((m.group(i), m.group(i + 1)) for i in (1, 3, 5, 7) if m.group(i)), (None, None))
        try:
            value = round(_to_number(raw, unit), 2)
        except (TypeError, ValueError):
            continue
        if value not in known:
            result.fail(f"amount {m.group(0).strip()} is not in the listings, knowledge or what the customer said",
                        span=m.group(0).strip())
        else:
            checked.add(value)

    for m in BIG_NUMBER_RE.finditer(ISO_DATE_RE.sub(' ', reply)):
        try:
            value = round(float(m.group(1).replace(',', '')), 2)
        except ValueError:
            continue
        if value not in known and value not in checked and not any(m.group(1) in o for o in result.offending):
            result.fail(f"figure {m.group(0)} does not appear in any tool result or KNOWLEDGE", span=m.group(0))

    performed = {a.get('tool') for a in actions}
    if _asserted(BOOKED_CLAIM_RE, reply) and 'book_viewing' not in performed and not has_existing_appointments:
        # Allowed only when the code quoted comes from an existing appointment (get_my_appointments).
        if not APPT_RE.search(reply):
            result.fail("claims a viewing is booked/confirmed but book_viewing did not succeed this turn", fatal=True)
    if _asserted(CANCEL_CLAIM_RE, reply) and 'cancel_appointment' not in performed:
        result.fail("claims a cancellation but cancel_appointment did not succeed this turn", fatal=True)

    return result




def salvage(reply: str, gate: GateResult) -> str:
    """
    Drop only the sentences/lines that contain an unverifiable figure or reference,
    keeping the rest of a useful answer. Returns '' when nothing safe is left.
    """
    if gate.fatal or not gate.offending:
        return ''
    kept = []
    for line in reply.splitlines():
        if any(span.lower() in line.lower() for span in gate.offending):
            # try sentence-level trimming inside the line first
            parts = [p for p in re.split(r'(?<=[.!?。！？])\s+', line)
                     if p and not any(span.lower() in p.lower() for span in gate.offending)]
            if parts:
                kept.append(' '.join(parts))
            continue
        kept.append(line)
    text = "\n".join(kept).strip()
    return text if len(text) >= 20 else ''
