"""
Viewing reminders and missed-viewing follow-ups (Celery beat, every 5 minutes).

Regression (2026-10-04): a customer booked "today 11:00" and heard nothing; at 13:51 the agent
still called the viewing "confirmed for today at 11:00". Two gaps:
  1. Nothing ever contacted the customer before or after the slot.
  2. The agent saw appointments by DATE only, so a slot that had already passed looked upcoming.
     (fixed in RealEstateTools._appt - every appointment now carries its `timing`.)

This module sends, on the conversation the booking came from:
  * a reminder ~1 hour before the viewing   (once: Appointment.reminder_sent)
  * a gentle follow-up ~30 min after the slot ended, when staff have not marked it completed /
    no-show / cancelled - "if you couldn't make it, I can arrange a new time"
                                            (once: Appointment.followup_sent_at)

Delivery rules:
  * WhatsApp free-form text is only delivered inside Meta's 24-hour customer-service window
    (outside it Meta accepts the call and silently drops the message). Outside the window we
    use email when the lead has one; otherwise the message is still written into the chat
    history (staff see it, the agent knows it) and the attempt is logged - never a fake "sent".
  * Website-widget chats: the message is stored on the conversation; the widget shows it.
  * Language follows the customer's chat (Devanagari / Romanized Nepali / English / Chinese),
    honorific register (see ai_engine/agent/tone.py).
  * Every message is saved as a SYSTEM message so the agent sees it in history next turn.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Appointment

logger = logging.getLogger(__name__)

REMINDER_LEAD = timedelta(minutes=60)       # remind when the viewing starts within this
REMINDER_MIN_LEAD = timedelta(minutes=10)   # too close to be useful → skip, don't spam
FOLLOWUP_AFTER = timedelta(minutes=30)      # after the slot ends
FOLLOWUP_MAX_AGE = timedelta(hours=36)      # never chase old slots (e.g. after downtime)
WHATSAPP_WINDOW = timedelta(hours=24)
ACTIVE = (Appointment.Status.SCHEDULED, Appointment.Status.CONFIRMED)

NE_DEVA, NE_ROMAN = 'ne-deva', 'ne-latn'

_REMINDER = {
    'en': ("Namaste{name}! A friendly reminder: your viewing {code} - {property} - is today at {time} "
           "({tz}). {status_line}If you need to change the time, just reply here and I'll help."),
    NE_ROMAN: ("Namaste{name}! Hajur ko viewing {code} - {property} - aaja {time} baje ({tz}) chha. "
               "{status_line}Samaya milena bhane yahi reply garnuhola, ma naya samaya milaidinchhu."),
    NE_DEVA: ("नमस्ते{name}! हजुरको भ्यूइङ {code} - {property} - आज {time} बजे ({tz}) छ। "
              "{status_line}समय मिलेन भने यहीँ जवाफ दिनुहोला, म नयाँ समय मिलाइदिन्छु।"),
    'zh': "您好{name}！溫馨提示：您的睇樓預約 {code} - {property} - 今天 {time}（{tz}）。{status_line}如需更改時間，請直接回覆。",
}
_PENDING_LINE = {
    'en': "Our team is still confirming this slot. ",
    NE_ROMAN: "Team le yo samaya confirm garna baki chha. ",
    NE_DEVA: "टिमले यो समय पक्का गर्न बाँकी छ। ",
    'zh': "職員仍在確認此時段。",
}
_FOLLOWUP = {
    'en': ("Namaste{name}! Your viewing {code} - {property} - was scheduled for {when} ({tz}). "
           "We hope it went well! If you couldn't make it, no problem at all - reply here and I'll "
           "arrange a new time for you."),
    NE_ROMAN: ("Namaste{name}! Hajur ko viewing {code} - {property} - {when} ({tz}) ma thiyo. "
               "Ramro sanga bhayo hola bhanne aasha chha! Aauna milena bhane kehi chinta nagarnuhola - "
               "yahi reply garnuhola, ma naya samaya milaidinchhu."),
    NE_DEVA: ("नमस्ते{name}! हजुरको भ्यूइङ {code} - {property} - {when} ({tz}) मा थियो। "
              "राम्रोसँग भयो होला भन्ने आशा छ! आउन मिलेन भने केही चिन्ता नगर्नुहोला - यहीँ जवाफ दिनुहोला, "
              "म नयाँ समय मिलाइदिन्छु।"),
    'zh': "您好{name}！您的睇樓預約 {code} - {property} - 原定於 {when}（{tz}）。希望一切順利！如未能出席，請直接回覆，我會為您重新安排時間。",
}
_EMAIL_SUBJECT = {'reminder': 'Reminder: your viewing {code} today at {time}',
                  'followup': 'Your viewing {code} - need a new time?'}


# ------------------------------------------------------------------ time helpers
def market_tz(organization) -> ZoneInfo:
    from apps.ai_engine.agent.tools import market_for
    try:
        return ZoneInfo(market_for(organization)['tz'])
    except Exception:
        return ZoneInfo('UTC')


def starts_at(appt: Appointment, tz: Optional[ZoneInfo] = None) -> datetime:
    """Appointment date/time are stored in the agency's local time."""
    tz = tz or market_tz(appt.organization)
    return datetime.combine(appt.appointment_date, appt.appointment_time).replace(tzinfo=tz)


def ends_at(appt: Appointment, tz: Optional[ZoneInfo] = None) -> datetime:
    return starts_at(appt, tz) + timedelta(minutes=appt.duration_minutes or 60)


def timing(appt: Appointment, now: Optional[datetime] = None, tz: Optional[ZoneInfo] = None) -> dict:
    """{'state': upcoming|in_progress|time_passed, 'minutes': int} relative to now."""
    now = now or timezone.now()
    start, end = starts_at(appt, tz), ends_at(appt, tz)
    if now < start:
        return {'state': 'upcoming', 'minutes_until_start': int((start - now).total_seconds() // 60)}
    if now < end:
        return {'state': 'in_progress', 'minutes_since_start': int((now - start).total_seconds() // 60)}
    return {'state': 'time_passed', 'minutes_since_end': int((now - end).total_seconds() // 60)}


# --------------------------------------------------------------------- language
def reply_style(conversation) -> str:
    """The language the agent last used with this customer (or detect from their messages)."""
    from apps.ai_engine.models import AILog
    from apps.ai_engine.agent.language import detect_reply_style
    from apps.messaging.models import MessageSender

    if conversation is None:
        return 'en'
    ctx = (AILog.objects.filter(conversation=conversation, context__has_key='reply_style')
           .order_by('-created_at').values_list('context', flat=True).first())
    if ctx and ctx.get('reply_style'):
        return ctx['reply_style']
    last = (conversation.messages.filter(sender=MessageSender.CUSTOMER).order_by('-created_at')
            .values_list('content', flat=True).first())
    return detect_reply_style(last or '', fallback='en')


def _template(table: dict, style: str) -> str:
    key = 'zh' if style in ('zh-CN', 'zh-TW') else style
    return table.get(key) or table['en']


def _fields(appt: Appointment, style: str, tz: ZoneInfo) -> dict:
    first = (appt.lead.name or '').split()[0] if appt.lead and appt.lead.name else ''
    if first.lower() in ('whatsapp', 'website', 'customer', 'guest'):
        first = ''
    start = starts_at(appt, tz)
    return {
        'name': f" {first}" if first else '', 'code': appt.confirmation_code,
        'property': appt.property_listing.title if appt.property_listing else appt.get_appointment_type_display(),
        'time': start.strftime('%H:%M'), 'when': start.strftime('%A %Y-%m-%d %H:%M'),
        'tz': str(tz).split('/')[-1].replace('_', ' ') + ' time',
        'status_line': _template(_PENDING_LINE, style) if appt.status == Appointment.Status.SCHEDULED else '',
    }


# --------------------------------------------------------------------- delivery
def _whatsapp_window_open(conversation, now) -> bool:
    from apps.messaging.models import MessageSender
    last_in = (conversation.messages.filter(sender=MessageSender.CUSTOMER).order_by('-created_at')
               .values_list('created_at', flat=True).first())
    return bool(last_in and now - last_in < WHATSAPP_WINDOW)


def _email(appt: Appointment, kind: str, text: str, fields: dict) -> bool:
    to = (appt.lead.email if appt.lead else '') or ''
    if not to:
        return False
    from django.core.mail import send_mail
    try:
        send_mail(_EMAIL_SUBJECT[kind].format(**fields), text + f"\n\n- {appt.organization.name}",
                  settings.DEFAULT_FROM_EMAIL, [to], fail_silently=False)
        return True
    except Exception:
        logger.exception("Appointment %s email failed", appt.confirmation_code)
        return False


def deliver(appt: Appointment, kind: str, now: datetime) -> str:
    """Send `kind` ('reminder' | 'followup'). Returns the channel used, '' if only recorded."""
    from apps.messaging.models import Message, MessageSender

    tz = market_tz(appt.organization)
    conv = appt.conversation
    style = reply_style(conv)
    fields = _fields(appt, style, tz)
    from apps.ai_engine.agent.tone import no_dashes
    text = no_dashes(_template(_REMINDER if kind == 'reminder' else _FOLLOWUP, style).format(**fields))

    channel = ''
    wa_id = None
    if conv is not None and str(conv.channel) == 'whatsapp' and conv.customer_phone:
        if _whatsapp_window_open(conv, now):
            from apps.channels.whatsapp_service import WhatsAppService
            service = WhatsAppService.get_for_organization(appt.organization)
            wa_id = service.send_message(to=conv.customer_phone, text=text) if service else None
            channel = 'whatsapp' if wa_id else ''
        else:
            logger.info("Appointment %s %s: WhatsApp 24h window closed - trying email",
                        appt.confirmation_code, kind)
    elif conv is not None:
        channel = str(conv.channel)   # widget & co: the stored message is what the customer sees
    if not channel and _email(appt, kind, text, fields):
        channel = 'email'

    if conv is not None:
        Message.objects.create(conversation=conv, sender=MessageSender.SYSTEM, content=text,
                               channel_message_id=wa_id or '', intent=f'appointment_{kind}',
                               ai_metadata={'kind': f'appointment_{kind}', 'appointment': appt.confirmation_code,
                                            'delivered_via': channel or 'not_delivered'})
    if not channel:
        logger.warning("Appointment %s %s could not be delivered (no open WhatsApp window, no email)",
                       appt.confirmation_code, kind)
    return channel


# ------------------------------------------------------------------------- jobs
def _candidates(now: datetime):
    """Active appointments around now (date-level prefilter; exact checks use each org's tz)."""
    today = now.date()
    return (Appointment.objects.filter(status__in=ACTIVE, appointment_date__range=(today - timedelta(days=2),
                                                                                   today + timedelta(days=1)))
            .select_related('organization', 'lead', 'property_listing', 'conversation'))


def send_due_reminders(now: Optional[datetime] = None) -> int:
    now = now or timezone.now()
    sent = 0
    for appt in _candidates(now).filter(reminder_sent=False):
        tz = market_tz(appt.organization)
        until = starts_at(appt, tz) - now
        if not (REMINDER_MIN_LEAD <= until <= REMINDER_LEAD):
            continue
        with transaction.atomic():
            # Claim first: a second beat worker (or a retry) must not send it twice.
            if not Appointment.objects.filter(pk=appt.pk, reminder_sent=False).update(
                    reminder_sent=True, reminder_sent_at=now):
                continue
        try:
            deliver(appt, 'reminder', now)
            sent += 1
        except Exception:
            logger.exception("Reminder for %s failed", appt.confirmation_code)
    return sent


def send_missed_followups(now: Optional[datetime] = None) -> int:
    now = now or timezone.now()
    sent = 0
    for appt in _candidates(now).filter(followup_sent_at__isnull=True):
        tz = market_tz(appt.organization)
        since_end = now - ends_at(appt, tz)
        if not (FOLLOWUP_AFTER <= since_end <= FOLLOWUP_MAX_AGE):
            continue
        with transaction.atomic():
            if not Appointment.objects.filter(pk=appt.pk, followup_sent_at__isnull=True,
                                              status__in=ACTIVE).update(followup_sent_at=now):
                continue
        try:
            deliver(appt, 'followup', now)
            sent += 1
        except Exception:
            logger.exception("Follow-up for %s failed", appt.confirmation_code)
    return sent
