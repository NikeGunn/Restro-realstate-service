"""
Viewing reminders, missed-viewing follow-ups and time-aware appointments.

Regression (2026-10-04, prod WhatsApp): at 13:51 Nepal time the agent told the customer
"Your viewing ... is confirmed for today, Sunday 2026-10-04 at 11:00 AM" - the slot had passed
2h51m earlier, and nobody had reminded the customer before it.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from django.core import mail
from django.utils import timezone

from apps.accounts.models import Location, Organization
from apps.ai_engine.agent.tools import RealEstateTools
from apps.ai_engine.models import AILog
from apps.messaging.models import Channel, Conversation, Message, MessageSender
from apps.realestate import appointment_notifications as notify
from apps.realestate.models import Appointment, Lead, PropertyListing

pytestmark = pytest.mark.django_db
KTM = ZoneInfo('Asia/Kathmandu')


@pytest.fixture
def org():
    o = Organization.objects.create(name='Kribaat Realestate', business_type='real_estate')
    Location.objects.create(organization=o, name='Kathmandu Office', is_primary=True, is_active=True,
                            country='Nepal', timezone='Asia/Kathmandu')
    return o


@pytest.fixture
def conv(org):
    c = Conversation.objects.create(organization=org, channel=Channel.WHATSAPP, customer_phone='9779812345678',
                                    customer_name='Nikhil Bhagat')
    Message.objects.create(conversation=c, sender=MessageSender.CUSTOMER, content='Hye')
    return c


def _appt(org, conv, start_local: datetime, status='confirmed', email=''):
    listing = PropertyListing.objects.create(
        organization=org, title='Land 4 Kattha, Butwal', description='x', listing_type='sale', property_type='land',
        price=Decimal('7500000'), address_line1='Kalikanagar', city='Butwal', country='Nepal')
    lead = Lead.objects.create(organization=org, name='Nikhil Bhagat', phone=conv.customer_phone, email=email)
    return Appointment.objects.create(organization=org, lead=lead, property_listing=listing, conversation=conv,
                                      appointment_date=start_local.date(), appointment_time=start_local.time(),
                                      duration_minutes=60, status=status)


# ------------------------------------------------------------ agent sees the time
def test_today_but_already_past_viewing_is_labelled_time_passed(org, conv):
    now_local = timezone.now().astimezone(KTM)
    appt = _appt(org, conv, (now_local - timedelta(hours=3)).replace(second=0, microsecond=0))
    tools = RealEstateTools(conv)
    if appt.appointment_date != now_local.date():
        pytest.skip('test ran just after midnight Kathmandu time')
    data = tools.get_my_appointments()['appointments'][0]
    assert data['timing']['state'] == 'time_passed' and data['timing']['minutes_since_end'] >= 119

    from apps.ai_engine.agent.runner import _timing_label
    label = _timing_label(data['timing'])
    assert label.startswith('TIME PASSED') and 'never describe it as upcoming' in label


def test_timing_states():
    org = Organization(name='x')
    start = datetime(2026, 10, 4, 11, 0, tzinfo=KTM)
    a = Appointment(organization=org, appointment_date=start.date(), appointment_time=start.time(), duration_minutes=60)
    assert notify.timing(a, start - timedelta(minutes=50), KTM) == {'state': 'upcoming', 'minutes_until_start': 50}
    assert notify.timing(a, start + timedelta(minutes=20), KTM)['state'] == 'in_progress'
    # The screenshot: 13:51 Nepal time, 11:00 viewing (ended 12:00) → passed 111 minutes ago.
    assert notify.timing(a, datetime(2026, 10, 4, 13, 51, tzinfo=KTM), KTM) == {'state': 'time_passed',
                                                                               'minutes_since_end': 111}


# -------------------------------------------------------------------- reminders
def _wa(sent):
    service = MagicMock()
    service.send_message.side_effect = lambda to, text: sent.append((to, text)) or 'wamid.1'
    return patch('apps.channels.whatsapp_service.WhatsAppService.get_for_organization', return_value=service)


def test_reminder_one_hour_before_on_whatsapp_once(org, conv):
    now = timezone.now()
    appt = _appt(org, conv, (now + timedelta(minutes=50)).astimezone(KTM).replace(microsecond=0))
    sent = []
    with _wa(sent):
        assert notify.send_due_reminders(now) == 1
        assert notify.send_due_reminders(now + timedelta(minutes=5)) == 0       # never twice
    to, text = sent[0]
    assert to == '9779812345678' and appt.confirmation_code in text and 'Land 4 Kattha, Butwal' in text
    appt.refresh_from_db()
    assert appt.reminder_sent and appt.reminder_sent_at
    stored = conv.messages.get(intent='appointment_reminder')
    assert stored.sender == MessageSender.SYSTEM and stored.ai_metadata['delivered_via'] == 'whatsapp'


def test_no_reminder_too_early_or_too_late(org, conv):
    now = timezone.now()
    _appt(org, conv, (now + timedelta(hours=3)).astimezone(KTM))
    _appt(org, conv, (now + timedelta(minutes=5)).astimezone(KTM))
    with _wa([]):
        assert notify.send_due_reminders(now) == 0


def test_reminder_in_customers_language_and_respectful(org, conv):
    AILog.objects.create(organization=org, conversation=conv, prompt='x', response='y',
                         context={'reply_style': 'ne-latn'})
    now = timezone.now()
    _appt(org, conv, (now + timedelta(minutes=55)).astimezone(KTM), status='scheduled')
    sent = []
    with _wa(sent):
        notify.send_due_reminders(now)
    text = sent[0][1]
    assert text.startswith('Namaste Nikhil! Hajur ko viewing') and 'confirm garna baki chha' in text
    from apps.ai_engine.agent.tone import register_problems
    assert register_problems(text, 'ne-latn') == []


def test_closed_whatsapp_window_falls_back_to_email(org, conv, settings):
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    conv.messages.update(created_at=timezone.now() - timedelta(days=3))     # last customer msg 3 days ago
    now = timezone.now()
    appt = _appt(org, conv, (now + timedelta(minutes=40)).astimezone(KTM), email='nikhil@example.com')
    sent = []
    with _wa(sent):
        notify.send_due_reminders(now)
    assert sent == []                                   # Meta would silently drop it - don't pretend
    assert len(mail.outbox) == 1 and appt.confirmation_code in mail.outbox[0].subject
    assert conv.messages.get(intent='appointment_reminder').ai_metadata['delivered_via'] == 'email'


def test_undeliverable_is_recorded_honestly(org, conv):
    conv.messages.update(created_at=timezone.now() - timedelta(days=3))
    now = timezone.now()
    _appt(org, conv, (now + timedelta(minutes=40)).astimezone(KTM))
    with _wa([]):
        notify.send_due_reminders(now)
    assert conv.messages.get(intent='appointment_reminder').ai_metadata['delivered_via'] == 'not_delivered'


# -------------------------------------------------------------------- follow-ups
def test_missed_viewing_follow_up_after_the_slot(org, conv):
    now = timezone.now()
    appt = _appt(org, conv, (now - timedelta(hours=2)).astimezone(KTM).replace(microsecond=0))
    sent = []
    with _wa(sent):
        assert notify.send_missed_followups(now) == 1
        assert notify.send_missed_followups(now + timedelta(minutes=10)) == 0
    text = sent[0][1]
    assert appt.confirmation_code in text and "couldn't make it" in text and 'new time' in text
    appt.refresh_from_db()
    assert appt.followup_sent_at is not None


@pytest.mark.parametrize('status', ['completed', 'cancelled', 'no_show'])
def test_no_follow_up_when_staff_already_closed_it(org, conv, status):
    now = timezone.now()
    _appt(org, conv, (now - timedelta(hours=2)).astimezone(KTM), status=status)
    with _wa([]):
        assert notify.send_missed_followups(now) == 0


def test_no_follow_up_for_old_or_running_slots(org, conv):
    now = timezone.now()
    _appt(org, conv, (now - timedelta(days=2)).astimezone(KTM))                # too old (outage catch-up)
    _appt(org, conv, (now - timedelta(minutes=20)).astimezone(KTM))            # still in progress
    with _wa([]):
        assert notify.send_missed_followups(now) == 0


def test_beat_schedule_runs_the_task(settings):
    entry = settings.CELERY_BEAT_SCHEDULE['realestate-appointment-notifications']
    assert entry['task'] == 'apps.realestate.tasks.appointment_notifications_task'
    from apps.realestate.tasks import appointment_notifications_task
    assert appointment_notifications_task() == {'reminders': 0, 'followups': 0}
