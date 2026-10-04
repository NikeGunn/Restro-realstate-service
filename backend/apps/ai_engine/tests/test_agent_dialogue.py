"""
Regression tests for the prod chat of 2026-10-04 (WhatsApp, Kribaat Realestate) - one per root cause:

1. "afno storage ma hernu" got the RESTAURANT inventory deflection ("menu, opening hours...").
2. "Yes" / "hunxa" / "ah hunxa" answered with the same question again (no action).
3. "I'll ask the team for photos" / "Request sent to the team" with nothing recorded.
4. "more photos" answered from memory ("no more photos") instead of the photo tool.
5. Booking name "Martas" was lost: the appointment hung off the old lead "Nikhil Bhagat", staff saw
   the wrong name and cancelled it.
6. Staff cancelled it in the dashboard; the customer was never told and the agent said the booking
   "is not in the record".
7. "i schedule gardeu voli after 1 pm" was answered in English.
8. "Yes go ahead" to "details or a viewing?" became a viewing at a time the customer never chose.
OpenAI is mocked: these pin the guarantees, not model quality (see run_agent_evals for that).
"""
import json
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Location, Organization, OrganizationMembership, User
from apps.ai_engine.agent import dialogue
from apps.ai_engine.agent.language import detect_reply_style, sticky_reply_style
from apps.ai_engine.agent.runner import HISTORY_CHARS, RealEstateAgent
from apps.ai_engine.agent.tools import RealEstateTools
from apps.ai_engine.services import AIService
from apps.handoff.models import HandoffAlert
from apps.messaging.models import Channel, Conversation, Message, MessageSender
from apps.realestate.models import Appointment, Lead, PropertyListing

pytestmark = pytest.mark.django_db


@pytest.fixture
def org():
    o = Organization.objects.create(name='Kribaat Test', business_type='real_estate')
    Location.objects.create(organization=o, name='Kathmandu Office', is_primary=True, is_active=True,
                            country='Nepal', timezone='Asia/Kathmandu')
    return o


@pytest.fixture
def shutter(org):
    return PropertyListing.objects.create(
        organization=org, title='Shutter on New Road, Kathmandu', description='prime market', listing_type='rent',
        property_type='retail', price=Decimal('65000'), rent_period='monthly', address_line1='New Road',
        city='Kathmandu', neighborhood='New Road', state='Bagmati', postal_code='', country='Nepal',
        images=['https://media.kribaat.com/a.jpg'])


@pytest.fixture
def conv(org):
    return Conversation.objects.create(organization=org, channel=Channel.WHATSAPP, customer_phone='9779705651002',
                                       customer_name='Nikhil Bhagat')


def _msg(content=None, tool_calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))],
                           usage=SimpleNamespace(total_tokens=10))


def _call(name, args, cid='c1'):
    return SimpleNamespace(id=cid, function=SimpleNamespace(name=name, arguments=json.dumps(args)))


def _say(conv, sender, text):
    return Message.objects.create(conversation=conv, sender=sender, content=text)


def _service(conv, responses):
    svc = AIService(conv)
    svc.client = MagicMock()
    svc.client.chat.completions.create.side_effect = responses
    return svc


# ------------------------------------------------------------ 1. inventory firewall scope
@pytest.mark.parametrize('text', ['photo hola maily web ma dekheko they ekchoti hernu hola afno storage ma',
                                  'Water supply kasto chha?', 'Is there a storage room?'])
def test_real_estate_messages_never_get_the_restaurant_inventory_deflection(conv, text):
    _say(conv, MessageSender.CUSTOMER, text)
    out = _service(conv, [_msg("Hajur, ma herchhu.")] * 4).process_message(text)
    assert 'menu' not in out['content'].lower()
    assert out['metadata'].get('source') == 'realestate_agent'


def test_restaurant_inventory_probe_is_still_deflected():
    o = Organization.objects.create(name='Cafe', business_type='restaurant')
    c = Conversation.objects.create(organization=o, channel=Channel.WHATSAPP, customer_phone='9779800000001')
    out = AIService(c).process_message('How much stock of chicken do you have?')
    assert out['intent'] == 'inventory_probe_deflected'


# ------------------------------------------------------------ 2-4. dialogue state
@pytest.mark.parametrize('text,yes', [
    ('Yes', True), ('hunxa', True), ('ah hunxa', True), ('Yes go ahead', True), ('Yes request your team', True),
    ('हुन्छ', True), ('ok', True), ('no', False), ('hunxa tara 3 baje?', False), ('Martas', False),
    ('malai photo chaenxa', False), ('Can you give me more photos', False), ('', False),
])
def test_affirmation_detector(text, yes):
    assert dialogue.is_affirmation(text) is yes


def _hist(*pairs):
    return [{'role': r, 'content': c} for r, c in pairs]


def test_yes_to_viewing_question_is_resolved_as_do_it():
    h = _hist(('user', 'ah hunxa'), ('assistant', 'Photo haru pathaieko chha. Herna jaana chahanuhunchha?'))
    b = dialogue.analyse('hunxa', h, pending_preview=False)
    assert b.affirmed and b.offer == 'viewing' and 'Do it now' in b.text()


def test_yes_to_ask_the_team_is_a_team_request_not_photos():
    h = _hist(('assistant', 'There are no photos uploaded yet. Would you like me to ask the team if they can provide photos?'))
    b = dialogue.analyse('Yes', h, pending_preview=False)
    assert b.offer == 'team_request' and 'request_team_followup' in b.text()


def test_repeating_the_answered_question_is_rejected():
    q = 'Would you like me to request the team to provide photos for you?'
    b = dialogue.analyse('Yes', _hist(('assistant', 'No photos yet. ' + q)), pending_preview=False)
    probs = dialogue.problems('Currently there are no photos. Would you like me to request the team to provide photos?',
                              b, ['send_property_photos'], [])
    assert any('REPEATED_QUESTION' in p for p in probs)


@pytest.mark.parametrize('reply', [
    'Hajur, ma team sanga New Road ko shutter ko photo magera pathaidinchhu.',
    'Request sent to the team to provide photos for the Butwal land.',
    "I'll ask the team to send more photos.",
])
def test_team_promise_needs_a_recorded_request(reply):
    b = dialogue.analyse('please', [], pending_preview=False)
    assert any('TEAM_PROMISE' in p for p in dialogue.problems(reply, b, [], []))
    assert not any('TEAM_PROMISE' in p for p in dialogue.problems(reply, b, ['request_team_followup'],
                                                                  ['request_team_followup']))


def test_offering_to_ask_the_team_is_fine_without_a_tool():
    b = dialogue.analyse('road kati feet ho?', [], pending_preview=False)
    reply = 'Road width record ma chhaina. Team sanga sodhera bhanidinchhu, huncha?'
    assert not dialogue.problems(reply, b, ['get_property_details'], ['get_property_details'])


def test_photo_answers_must_come_from_the_photo_tool_this_turn():
    b = dialogue.analyse('Can you give me more photos', [], pending_preview=False)
    probs = dialogue.problems('There are no more photos uploaded beyond the one I sent.', b, [], [])
    assert any('PHOTOS_NOT_CHECKED' in p for p in probs)
    assert not dialogue.problems('I have sent you 2 photos.', b, ['send_property_photos'], ['send_property_photos'])


@pytest.mark.parametrize('text,retry', [
    ('ekchoti afno database check garnu feri', True), ('Do search again on database', True),
    ('afno storage ma hernu hola', True), ('Is there a storage room?', False), ('Water supply system kasto?', False),
])
def test_retry_detector(text, retry):
    assert dialogue.analyse(text, [], pending_preview=False).retry is retry


def test_check_again_needs_a_fresh_tool_call():
    b = dialogue.analyse('ekchoti afno database check garnu feri', [], pending_preview=False)
    assert any('RECHECK' in p for p in dialogue.problems('Hajur, photo chhaina.', b, [], []))


def test_agent_retries_when_the_draft_repeats_the_answered_question(conv, shutter):
    q = 'Herna jaana chahanuhunchha?'
    _say(conv, MessageSender.AI, f'New Road ko shutter ({shutter.reference_number}) Rs 65,000/month. {q}')
    _say(conv, MessageSender.CUSTOMER, 'hunxa')
    svc = _service(conv, [
        _msg(f'Hajur, dhanyabad! {q}'),                                   # draft 1: the prod failure
        _msg('Hajur, kun din ra kati baje herna aauna milchha, bhannuhola?'),  # corrected
        _msg('Hajur, kun din ra kati baje herna aauna milchha, bhannuhola?'),  # (tone pass, if any)
    ])
    out = svc.process_message('hunxa')
    assert 'kun din' in out['content'] and q not in out['content']
    retry_prompt = svc.client.chat.completions.create.call_args_list[1].kwargs['messages'][-1]['content']
    assert 'REPEATED_QUESTION' in retry_prompt


# ------------------------------------------------------------ 3. team requests are real records
def test_request_team_followup_records_an_alert_without_silencing_the_ai(conv, shutter):
    t = RealEstateTools(conv)
    r = t.request_team_followup('Customer wants more photos of the shop', reference=shutter.reference_number)
    assert r['ok'] and not r['already_requested']
    alert = HandoffAlert.objects.get(conversation=conv)
    assert shutter.reference_number in alert.reason and not alert.is_resolved
    assert RealEstateTools(conv).request_team_followup('Customer wants more photos of the shop',
                                                       reference=shutter.reference_number)['already_requested']
    conv.refresh_from_db()
    assert conv.state != 'human_handoff' and t.escalation == {}


def test_staff_resolution_notes_reach_the_agent_prompt(conv, shutter):
    RealEstateTools(conv).request_team_followup('More photos please', reference=shutter.reference_number)
    HandoffAlert.objects.filter(conversation=conv).update(is_resolved=True, resolution_notes='Uploaded 3 new photos')
    agent = RealEstateAgent(AIService(conv))
    assert 'Uploaded 3 new photos' in agent._system_prompt('en')


# ------------------------------------------------------------ 4. photos always re-checked
def test_photo_tool_reads_live_data_each_call(conv, shutter):
    assert RealEstateTools(conv).send_property_photos(shutter.reference_number)['photos_available'] == 1
    shutter.images = shutter.images + ['https://media.kribaat.com/b.jpg']
    shutter.save(update_fields=['images'])
    assert RealEstateTools(conv).send_property_photos(shutter.reference_number)['photos_available'] == 2


# ------------------------------------------------------------ 5. booking name is stored
def _book(conv, shutter, name, time='14:00', said='voli after 1 pm, 2 baje'):
    from apps.ai_engine.agent import actions as agent_actions
    from apps.ai_engine.models import AgentAction
    _say(conv, MessageSender.CUSTOMER, f'{said}. Naam {name}.')
    t = RealEstateTools(conv)
    t.current_message = f'{name}'
    t.turn_started_at = timezone.now()
    day = t.now().date() + timedelta(days=1)
    p = t.prepare_viewing(shutter.reference_number, day.isoformat(), time, day.strftime('%A'), name=name)
    assert p['ok'], p
    AgentAction.objects.filter(id=p['preview_id']).update(created_at=timezone.now() - timedelta(minutes=1))
    t2 = RealEstateTools(conv)
    t2.current_message, t2.turn_started_at = 'yes', timezone.now()
    r = t2.confirm_pending_action(p['preview_id'])
    assert r['ok'], r
    assert agent_actions.pending_preview(conv) is None
    return Appointment.objects.get(confirmation_code=r['receipt']['code'])


def test_booking_for_someone_else_keeps_their_name(org, conv, shutter):
    Lead.objects.create(organization=org, name='Nikhil Bhagat', phone='9779705651002', conversation=conv)
    appt = _book(conv, shutter, 'Martas')
    assert appt.attendee_name == 'Martas' and appt.lead.name == 'Nikhil Bhagat'
    mine = RealEstateTools(conv).get_my_appointments()['appointments']
    assert mine[0]['booked_name'] == 'Martas'


# ------------------------------------------------------------ 6. staff changes reach customer + agent
def _owner(org):
    u = User.objects.create_user(username='o@x.com', email='o@x.com', password='pw-12345678')
    OrganizationMembership.objects.create(user=u, organization=org, role='owner')
    c = APIClient()
    c.force_authenticate(u)
    return c


def test_staff_cancel_is_told_to_the_customer_and_the_agent(org, conv, shutter):
    _say(conv, MessageSender.CUSTOMER, 'i schedule gardeu voli after 1 pm')  # Romanized Nepali chat
    appt = _book(conv, shutter, 'Martas')
    with patch('apps.channels.whatsapp_service.WhatsAppService.get_for_organization') as wa:
        wa.return_value.send_message.return_value = 'wamid.1'
        r = _owner(org).post(f'/api/realestate/appointments/{appt.id}/cancel/',
                             {'reason': 'Naam mismatch bhayo'}, format='json')
    assert r.status_code == 200 and r.json()['customer_notified_via'] == 'whatsapp'
    sent = wa.return_value.send_message.call_args.kwargs['text']
    assert appt.confirmation_code in sent and 'Naam mismatch bhayo' in sent and 'cancel' in sent
    notice = Message.objects.filter(conversation=conv, sender=MessageSender.SYSTEM).last()
    assert notice.content == sent
    # The agent sees the notice in its history and the cancellation in the appointment tool.
    agent = RealEstateAgent(AIService(conv))
    hist = agent._history('mero appointment kati baje ko xa?')
    assert any('[Automatic notice sent to the customer]' in m['content'] and appt.confirmation_code in m['content']
               for m in hist)
    changed = RealEstateTools(conv).get_my_appointments()['recently_changed']
    assert changed[0]['status'] == 'cancelled by our team'
    assert changed[0]['cancellation_reason'] == 'Naam mismatch bhayo'


def test_staff_reschedule_and_confirm_notify(org, conv, shutter):
    appt = _book(conv, shutter, 'Martas')
    c = _owner(org)
    new_day = (timezone.now() + timedelta(days=3)).date().isoformat()
    r = c.patch(f'/api/realestate/appointments/{appt.id}/', {'appointment_date': new_day}, format='json')
    assert r.status_code == 200
    assert Message.objects.filter(conversation=conv, intent='appointment_staff_rescheduled').count() == 1
    appt.refresh_from_db()
    assert not appt.reminder_sent


def test_customer_cancel_in_chat_is_not_reported_as_staff_cancel(conv, shutter):
    from apps.ai_engine.models import AgentAction
    appt = _book(conv, shutter, 'Martas')
    t = RealEstateTools(conv)
    p = t.prepare_cancellation(appt.confirmation_code)
    AgentAction.objects.filter(id=p['preview_id']).update(created_at=timezone.now() - timedelta(minutes=1))
    t2 = RealEstateTools(conv)
    t2.current_message, t2.turn_started_at = 'yes', timezone.now()
    assert t2.confirm_pending_action(p['preview_id'])['ok']
    changed = RealEstateTools(conv).get_my_appointments()['recently_changed']
    assert changed[0]['status'] == 'cancelled by the customer in chat'


# ------------------------------------------------------------ 7. language
@pytest.mark.parametrize('text', ['i schedule gardeu voli after 1 pm', 'new road wala ko barema vannu',
                                  'malai photo chaenxa', 'ekchoti afno database check garnu feri and photo pathaunu'])
def test_casual_romanized_nepali_is_nepali(text):
    assert detect_reply_style(text) == 'ne-latn'


@pytest.mark.parametrize('text', ['I want to buy a house in Kathmandu', 'Can you send me photos',
                                  'Please book it for me tomorrow', 'after 1 pm you can choose any one'])
def test_english_stays_english(text):
    assert detect_reply_style(text) == 'en'


def test_bare_name_keeps_the_nepali_conversation():
    assert sticky_reply_style('Martas', ['i schedule gardeu voli after 1 pm']) == 'ne-latn'


@pytest.mark.parametrize('ack', ['yes', 'ok', 'Yes, confirm', 'thank you'])
def test_bare_yes_keeps_the_conversation_language(ack):
    assert sticky_reply_style(ack, ['PROP1 bholi 2 baje herna milchha? naam Martas']) == 'ne-latn'
    assert sticky_reply_style(ack, ['Can I see the flat tomorrow?']) == 'en'


def test_conditional_offer_to_ask_the_team_is_not_a_promise():
    b = dialogue.analyse('photo chha?', [], pending_preview=False)
    reply = 'Photo upload bhayeko chhaina. Chahinchha bhane ma team sanga photo magera pathaidinchhu.'
    assert not dialogue.problems(reply, b, ['send_property_photos'], ['send_property_photos'])


# ------------------------------------------------------------ 8. viewing time is the customer's choice
def test_agent_cannot_pick_a_viewing_time_the_customer_never_chose(conv, shutter):
    _say(conv, MessageSender.CUSTOMER, 'Yes go ahead. Naam Martas.')
    t = RealEstateTools(conv)
    t.current_message = 'Yes go ahead. Naam Martas.'
    day = t.now().date() + timedelta(days=1)
    r = t.prepare_viewing(shutter.reference_number, day.isoformat(), '11:00', day.strftime('%A'), name='Martas')
    assert not r['ok'] and 'TIME_NOT_CHOSEN' in r['error'] and r['free_slots_that_day']


def test_delegated_time_is_allowed(conv, shutter):
    _say(conv, MessageSender.CUSTOMER, 'Naam Martas. after 1 pm you can choose any one')
    t = RealEstateTools(conv)
    day = t.now().date() + timedelta(days=1)
    assert t.prepare_viewing(shutter.reference_number, day.isoformat(), '14:00', day.strftime('%A'),
                             name='Martas')['ok']


# ------------------------------------------------------------ context budget
def test_history_is_bounded_and_keeps_the_newest(conv):
    for i in range(60):
        _say(conv, MessageSender.CUSTOMER if i % 2 == 0 else MessageSender.AI, f'msg {i} ' + 'x' * 2500)
    agent = RealEstateAgent(AIService(conv))
    hist = agent._history('latest')
    total = sum(len(m['content']) for m in hist)
    assert total <= HISTORY_CHARS + 2000 and 'msg 59' in hist[-1]['content']
    assert all(len(m['content']) <= 1600 for m in hist)
