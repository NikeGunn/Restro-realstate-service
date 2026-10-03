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
# HK$1,234,567 · $32,000 · HKD 5.98M · HK$18.8 million · 42,000,000 港元
MONEY_RE = re.compile(
    r'(?:HK\$|HKD\s?|\$|港幣|港元)\s?(\d[\d,]*(?:\.\d+)?)\s*(million|m\b|萬|万|k\b)?'
    r'|(\d[\d,]*(?:\.\d+)?)\s*(million|萬|万)?\s*(?:港元|港幣|HKD)',
    re.I,
)
NUMBER_RE = re.compile(r'\d[\d,]*(?:\.\d+)?')

BOOKED_CLAIM_RE = re.compile(
    r"(viewing|appointment|visit|tour)[^.!?\n]{0,60}\b(is |has been |are )?(booked|confirmed|scheduled|reserved)\b"
    r"|\b(booked|confirmed|scheduled|reserved)\b[^.!?\n]{0,40}(viewing|appointment|visit|tour)"
    r"|已(為你|为你|為您|为您)?(預約|预约|確認|确认|安排)",
    re.I,
)
CANCEL_CLAIM_RE = re.compile(r"\b(has been|is now|successfully) cancel+ed\b|已(取消)", re.I)


def _to_number(raw: str, unit: str = '') -> float:
    value = float(raw.replace(',', ''))
    unit = (unit or '').lower()
    if unit in ('million', 'm'):
        value *= 1_000_000
    elif unit in ('萬', '万'):
        value *= 10_000
    elif unit == 'k':
        value *= 1_000
    return value


SCALED_RE = re.compile(r'(\d[\d,]*(?:\.\d+)?)\s*(million|mil|m\b|萬|万|k\b)', re.I)


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

    def fail(self, problem: str):
        self.ok = False
        self.problems.append(problem)


def verify_reply(reply: str, evidence: List[str], actions: List[dict],
                 has_existing_appointments: bool = False) -> GateResult:
    result = GateResult()
    blob = "\n".join(evidence)
    upper_blob = blob.upper()

    for ref in {r.upper() for r in REF_RE.findall(reply)}:
        if ref not in upper_blob:
            result.fail(f"reference {ref} does not exist in any tool result")

    for code in {c.upper() for c in APPT_RE.findall(reply)}:
        if code not in upper_blob:
            result.fail(f"confirmation code {code} was not returned by a tool")

    known = evidence_numbers(evidence)
    for m in MONEY_RE.finditer(reply):
        raw, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        try:
            value = round(_to_number(raw, unit), 2)
        except (TypeError, ValueError):
            continue
        if value not in known:
            result.fail(f"amount {m.group(0).strip()} is not in the listings or knowledge")

    performed = {a.get('tool') for a in actions}
    if BOOKED_CLAIM_RE.search(reply) and 'book_viewing' not in performed and not has_existing_appointments:
        # Allowed only when the code quoted comes from an existing appointment (get_my_appointments).
        if not APPT_RE.search(reply):
            result.fail("claims a viewing is booked/confirmed but book_viewing did not succeed this turn")
    if CANCEL_CLAIM_RE.search(reply) and 'cancel_appointment' not in performed:
        result.fail("claims a cancellation but cancel_appointment did not succeed this turn")

    return result
