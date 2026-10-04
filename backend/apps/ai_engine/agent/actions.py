"""
Preview → customer confirmation → locked execution → stored receipt.

The model can PROPOSE a write (prepare_*), but only code decides whether it runs:
  1. The preview must come from an earlier turn - the customer has seen it.
  2. The customer's latest message must be a plain confirmation ("yes", "huncha", "हुन्छ",
     "好"), with no new details (a changed time/name means: prepare a new preview).
  3. Execution locks the preview row and the listing row, re-checks availability and the
     price the customer saw, then commits. A second "yes" or a retried webhook gets the
     stored receipt, never a second booking.
Receipts, not model prose, are the source of what the customer is told.
"""
import hashlib
import json
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from django.db import transaction
from django.utils import timezone

from apps.ai_engine.models import AgentAction, AgentSettings
from apps.realestate.models import Appointment, PropertyListing

PREVIEW_TTL = timedelta(minutes=30)
ACTIVE_APPT = [Appointment.Status.SCHEDULED, Appointment.Status.CONFIRMED]

_AFFIRM = {
    'yes', 'yeah', 'yep', 'yup', 'ok', 'okay', 'sure', 'confirm', 'confirmed', 'correct', 'right', 'proceed',
    'ahead', 'huncha', 'hunchha', 'hunxa', 'hus', 'ho', 'thik', 'thikcha', 'thikxa',
    'garnus', 'gara', 'garidinus', 'gardinus', 'pakka', 'hajur', 'हुन्छ', 'हो', 'ठिक', 'ठीक', 'गर्नुस्',
    'गर्नुहोस्', 'पक्का', 'हजुर', '好', '是', '确认', '確認', '可以', '冇問題', '没问题', '對', '对',
}
_NEGATE = {
    'no', 'nope', 'not', "don't", 'dont', 'wait', 'hold', 'stop', 'keep', 'change', 'instead', 'but',
    'hoina', 'haina', 'nai', 'chaina', 'chhaina', 'nagarnus', 'nagara', 'pardaina', 'parena', 'bhayena',
    'होइन', 'हैन', 'छैन', 'नगर्नुस्', 'पर्दैन', '不', '唔', '别', '別', '取消唔',
}
_QUESTION = {
    'what', 'when', 'where', 'which', 'how', 'why', 'who', 'kati', 'kaha', 'kahile', 'kun', 'kina', 'ke', 'kasto',
    'के', 'कति', 'कहाँ', 'कहिले', 'कुन', '吗', '嗎', '什么', '甚麼', '幾', '几',
}
_WORD = re.compile(r"[\w'ऀ-ॿ]+|[一-鿿]", re.UNICODE)


def is_plain_confirmation(text: str) -> bool:
    """True only for a bare yes - no negation and no new details (digits = changed date/time)."""
    text = (text or '').strip().lower()
    if not text or len(text) > 80 or '?' in text or '？' in text or re.search(r'\d', text):
        return False
    words = set(_WORD.findall(text))
    return bool(words & _AFFIRM) and not (words & (_NEGATE | _QUESTION))


def _hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


# ------------------------------------------------------------------ slots
def viewing_slots(organization, listing: PropertyListing, day, now) -> List[str]:
    """Free viewing start times for one listing on one day (owner-configured hours)."""
    cfg = AgentSettings.for_org(organization)
    step = max(15, cfg.slot_minutes)
    taken = set(Appointment.objects.filter(
        organization=organization, property_listing=listing, appointment_date=day, status__in=ACTIVE_APPT,
    ).values_list('appointment_time', flat=True))
    taken = {t.strftime('%H:%M') for t in taken}
    slots, t = [], datetime.combine(day, datetime.min.time()).replace(hour=cfg.viewing_start_hour, tzinfo=now.tzinfo)
    end = t.replace(hour=min(cfg.viewing_end_hour, 23))
    while t <= end:
        if t >= now + timedelta(hours=1) and t.strftime('%H:%M') not in taken:
            slots.append(t.strftime('%H:%M'))
        t += timedelta(minutes=step)
    return slots


# --------------------------------------------------------------- previews
def create_preview(conversation, kind: str, payload: Dict[str, Any]) -> AgentAction:
    """One pending decision at a time: a new preview supersedes older ones in this chat."""
    with transaction.atomic():
        AgentAction.objects.filter(conversation=conversation, status=AgentAction.Status.PREVIEWED).update(
            status=AgentAction.Status.SUPERSEDED)
        return AgentAction.objects.create(
            organization=conversation.organization, conversation=conversation, kind=kind, payload=payload,
            payload_hash=_hash(payload), expires_at=timezone.now() + PREVIEW_TTL,
        )


def pending_preview(conversation) -> Optional[AgentAction]:
    return (AgentAction.objects.filter(conversation=conversation, status=AgentAction.Status.PREVIEWED)
            .order_by('-created_at').first())


def decline_pending(conversation) -> Optional[AgentAction]:
    action = pending_preview(conversation)
    if action:
        action.status = AgentAction.Status.DECLINED
        action.save(update_fields=['status'])
    return action


def confirm(conversation, preview_id: str, customer_message: str, turn_started_at, execute) -> Dict[str, Any]:
    """
    Run `execute(action)` for a confirmed preview, exactly once. Returns a tool result.
    `execute` must raise ActionRejected for business-rule failures (slot gone, etc.).
    """
    action = AgentAction.objects.filter(conversation=conversation, id=_uuid(preview_id)).first()
    if not action:
        action = pending_preview(conversation)
        if not action:
            return {'ok': False, 'error': 'NO_PENDING_PREVIEW: nothing is waiting for confirmation. '
                                          'Prepare a preview first and show it to the customer.'}
    if action.status == AgentAction.Status.EXECUTED:
        return {'ok': True, 'already_done': True, 'receipt': action.receipt,
                'note': 'This was already done earlier - tell the customer no second booking was made.'}
    if action.status != AgentAction.Status.PREVIEWED:
        return {'ok': False, 'error': f'PREVIEW_{action.status.upper()}: that preview is no longer valid; '
                                      'prepare a new one if the customer still wants it.'}
    if action.created_at >= turn_started_at and not name_only_amendment(conversation, action, turn_started_at,
                                                                         customer_message):
        return {'ok': False, 'error': 'NOT_CONFIRMED_YET: the customer has not seen this preview. Show it and '
                                      'ask them to confirm; do not claim it is done.'}
    if not is_plain_confirmation(customer_message):
        return {'ok': False, 'error': 'NOT_CONFIRMED: the latest message is not a plain yes. If they changed '
                                      'details, prepare a new preview with the new details.'}
    with transaction.atomic():
        action = AgentAction.objects.select_for_update().get(pk=action.pk)
        if action.status == AgentAction.Status.EXECUTED:  # lost a race with a duplicate "yes"
            return {'ok': True, 'already_done': True, 'receipt': action.receipt}
        if action.expires_at < timezone.now():
            action.status = AgentAction.Status.EXPIRED
            action.save(update_fields=['status'])
            return {'ok': False, 'error': 'PREVIEW_EXPIRED: re-check availability and prepare a new preview.'}
        try:
            with transaction.atomic():  # savepoint: a rejected execution leaves no partial writes
                receipt = execute(action)
        except ActionRejected as e:
            action.status, action.error = AgentAction.Status.FAILED, str(e)[:300]
            action.save(update_fields=['status', 'error'])
            return {'ok': False, 'error': str(e), 'nothing_was_changed': True}
        action.status, action.receipt, action.executed_at = AgentAction.Status.EXECUTED, receipt, timezone.now()
        action.save(update_fields=['status', 'receipt', 'executed_at'])
    return {'ok': True, 'receipt': receipt}


# What the customer's consent is about. The booking NAME is not on this list: it is the customer's
# own fact, typed by them, so correcting it does not change what they agreed to.
_NAME_FIELDS = {'name'}


def name_only_amendment(conversation, action: AgentAction, turn_started_at, customer_message: str) -> bool:
    """
    A preview created in THIS turn is still confirmable when it only corrects the customer's name on a
    preview the customer already saw in an EARLIER turn, using a name the customer typed themselves.

    Root cause (eval RE-043): the customer answered the first preview with their real name; the model
    asked "book it under Martas instead?", and on "Yes, confirm" re-prepared with the new name and
    confirmed. Listing, date, time and price were exactly what the customer had already seen and
    approved, yet the same-turn rule forced a second "yes". Any other difference (listing, date,
    time, price, staff-approval) still needs a fresh confirmation.
    """
    from apps.messaging.models import MessageSender

    new_name = str(action.payload.get('name') or '').strip()
    if not new_name:
        return False
    earlier = (AgentAction.objects.filter(conversation=conversation, kind=action.kind,
                                          created_at__lt=turn_started_at,
                                          status__in=[AgentAction.Status.SUPERSEDED, AgentAction.Status.PREVIEWED])
               .exclude(pk=action.pk).order_by('-created_at').first())
    if earlier is None:
        return False
    keys = (set(earlier.payload) | set(action.payload)) - _NAME_FIELDS
    if any(earlier.payload.get(k) != action.payload.get(k) for k in keys):
        return False
    said = list(conversation.messages.filter(sender=MessageSender.CUSTOMER)
                .values_list('content', flat=True)) + [customer_message or '']
    pattern = re.compile(r'(?<!\w)' + re.escape(new_name) + r'(?!\w)', re.I)
    return any(pattern.search(text or '') for text in said)


class ActionRejected(Exception):
    pass


def _uuid(value):
    import uuid
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def lock_listing(organization, listing_id) -> PropertyListing:
    """Serialize writes for one listing (two customers racing for the last slot)."""
    listing = PropertyListing.objects.select_for_update().filter(
        organization=organization, id=listing_id, status=PropertyListing.Status.ACTIVE, is_published=True,
    ).first()
    if not listing:
        raise ActionRejected('LISTING_UNAVAILABLE: this listing is no longer active. Nothing was booked.')
    return listing
