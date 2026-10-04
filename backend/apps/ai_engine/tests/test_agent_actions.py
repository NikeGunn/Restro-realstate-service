"""
Action safety for the real-estate agent - the release-critical cases of the
kribaat_agent_harness spec (RE-041…060, RE-092…100, RT-116). OpenAI is mocked:
these pin what CODE guarantees regardless of what the model writes.
"""
import json
import threading
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.db import connection
from django.utils import timezone

from apps.accounts.models import Location, Organization
from apps.ai_engine.agent import actions
from apps.ai_engine.agent.tools import RealEstateTools
from apps.ai_engine.booking_guard import apply_receipt, guard_reply
from apps.ai_engine.models import AgentAction, AgentMemory, AgentSettings, AILog
from apps.ai_engine.services import AIService
from apps.messaging.models import Channel, Conversation, Message, MessageSender
from apps.realestate.models import Appointment, Lead, PropertyListing

pytestmark = pytest.mark.django_db


@pytest.fixture
def org():
    o = Organization.objects.create(name='Estate A', business_type='real_estate')
    Location.objects.create(organization=o, name='KTM', is_primary=True, is_active=True, country='Nepal')
    return o


@pytest.fixture
def plot(org):
    return PropertyListing.objects.create(
        organization=org, title='Land 12 Dhur, Biratnagar-04', description='Plot', listing_type='sale',
        property_type='land', price=Decimal('4800000'), address_line1='Ward 4', city='Biratnagar', state='Koshi',
        postal_code='0', country='Nepal', lot_size=2000, features=['Road access: 20 ft'])


@pytest.fixture
def conv(org):
    return Conversation.objects.create(organization=org, channel=Channel.WHATSAPP, customer_phone='9779800000001',
                                       customer_name='Martas')


def _tomorrow(conv):
    return (RealEstateTools(conv).now() + timedelta(days=1)).date()


def _turn(tools, message):
    """Simulate the start of a new customer turn."""
    tools.current_message = message
    # +1 ms: on a coarse clock a preview created just before can share the exact timestamp,
    # which the gate (correctly) treats as "same turn".
    tools.turn_started_at = timezone.now() + timedelta(milliseconds=1)
    return tools


def _preview(conv, plot, time='11:00', name='Martas'):
    tools = RealEstateTools(conv)
    day = _tomorrow(conv)
    res = tools.prepare_viewing(reference=plot.reference_number, date=day.isoformat(), time=time,
                                weekday=day.strftime('%A'), name=name)
    assert res['ok'], res
    return res


# ------------------------------------------------------------ confirmations
@pytest.mark.parametrize('text,ok', [
    ('Yes, confirm.', True), ('yes', True), ('Huncha', True), ('हुन्छ', True), ('好', True), ('ok go ahead', True),
    ('No, keep it', False), ('yes but 3 pm', False), ('Yo kati ho?', False), ('Martas', False),
    ('wait', False), ('Pahila price kati ho bhannu', False), ('', False),
])
def test_plain_confirmation_detector(text, ok):
    assert actions.is_plain_confirmation(text) is ok


# ------------------------------------------------------------------- booking
def test_re042_slots_come_from_service_and_exclude_taken(conv, plot):
    day = _tomorrow(conv)
    free = RealEstateTools(conv).get_viewing_slots(plot.reference_number, day.isoformat())['free_slots']
    assert '11:00' in free and '15:00' in free and '20:00' not in free


def test_re043_preview_then_confirm_books_exactly_once(conv, plot):
    preview = _preview(conv, plot)
    assert preview['awaiting_customer_confirmation'] and Appointment.objects.count() == 0  # no write at preview

    tools = _turn(RealEstateTools(conv), 'Yes, confirm.')
    res = tools.confirm_pending_action(preview['preview_id'])
    assert res['ok'] and res['receipt']['status'] == 'confirmed'
    appt = Appointment.objects.get()
    assert res['receipt']['code'] == appt.confirmation_code and appt.status == Appointment.Status.CONFIRMED

    # RE-093: a duplicate "yes" (or webhook retry) returns the stored receipt, never a 2nd booking.
    again = _turn(RealEstateTools(conv), 'Yes, confirm.').confirm_pending_action(preview['preview_id'])
    assert again['ok'] and again['already_done'] and Appointment.objects.count() == 1


def test_confirm_in_same_turn_as_preview_is_refused(conv, plot):
    tools = _turn(RealEstateTools(conv), 'Book RE-01 tomorrow 11 for Martas, yes confirm')
    day = _tomorrow(conv)
    preview = tools.prepare_viewing(reference=plot.reference_number, date=day.isoformat(), time='11:00',
                                    weekday=day.strftime('%A'), name='Martas')
    res = tools.confirm_pending_action(preview['preview_id'])
    assert not res['ok'] and 'NOT_CONFIRMED_YET' in res['error'] and Appointment.objects.count() == 0


def test_re073_model_cannot_confirm_without_customer_yes(conv, plot):
    preview = _preview(conv, plot)
    for msg in ('Show photos first', 'No.', 'Naam Marta ho, ani 3 pm gara'):
        res = _turn(RealEstateTools(conv), msg).confirm_pending_action(preview['preview_id'])
        assert not res['ok']
    assert Appointment.objects.count() == 0


def test_re044_staff_approval_mode_creates_request_not_confirmation(conv, plot, org):
    AgentSettings.objects.create(organization=org, viewings_need_staff_approval=True)
    preview = _preview(conv, plot)
    assert preview['preview']['needs_staff_approval'] is True
    res = _turn(RealEstateTools(conv), 'huncha').confirm_pending_action(preview['preview_id'])
    assert res['receipt']['status'] == 'pending_staff_approval'
    assert Appointment.objects.get().status == Appointment.Status.SCHEDULED


def test_re045_unavailable_time_is_not_shifted(conv, plot):
    day = _tomorrow(conv)
    res = RealEstateTools(conv).prepare_viewing(reference=plot.reference_number, date=day.isoformat(),
                                                time='14:30', weekday=day.strftime('%A'), name='Martas')
    assert not res['ok'] and res['error'] == 'SLOT_UNAVAILABLE' and res['free_slots_that_day']
    assert not AgentAction.objects.exists()


def test_re046_slot_lost_after_preview_books_nothing(conv, plot, org):
    preview = _preview(conv, plot)
    other = Conversation.objects.create(organization=org, channel=Channel.WHATSAPP, customer_phone='9779800000099')
    rival = _preview(other, plot, name='Rival')
    assert _turn(RealEstateTools(other), 'yes').confirm_pending_action(rival['preview_id'])['ok']
    res = _turn(RealEstateTools(conv), 'Yes, confirm it.').confirm_pending_action(preview['preview_id'])
    assert not res['ok'] and 'SLOT_TAKEN' in res['error'] and res['nothing_was_changed']
    assert Appointment.objects.count() == 1


def test_re091_price_change_after_preview_blocks_booking(conv, plot):
    preview = _preview(conv, plot)
    PropertyListing.objects.filter(pk=plot.pk).update(price=Decimal('5000000'))
    res = _turn(RealEstateTools(conv), 'yes').confirm_pending_action(preview['preview_id'])
    assert not res['ok'] and 'PRICE_CHANGED' in res['error'] and Appointment.objects.count() == 0


def test_re071_correction_supersedes_old_preview(conv, plot):
    old = _preview(conv, plot, time='11:00', name='Martas')
    new = _preview(conv, plot, time='15:00', name='Marta')
    assert AgentAction.objects.get(id=old['preview_id']).status == AgentAction.Status.SUPERSEDED
    res = _turn(RealEstateTools(conv), 'yes').confirm_pending_action(old['preview_id'])
    assert not res['ok']
    res = _turn(RealEstateTools(conv), 'yes').confirm_pending_action(new['preview_id'])
    appt = Appointment.objects.get()
    assert res['ok'] and appt.lead.name == 'Marta' and appt.appointment_time.strftime('%H:%M') == '15:00'


def test_re051_decline_keeps_everything(conv, plot):
    _preview(conv, plot)
    assert _turn(RealEstateTools(conv), 'No, keep it').decline_pending_action()['declined']
    assert not _turn(RealEstateTools(conv), 'yes').confirm_pending_action('')['ok']
    assert Appointment.objects.count() == 0


def test_expired_preview_cannot_commit(conv, plot):
    preview = _preview(conv, plot)
    AgentAction.objects.filter(id=preview['preview_id']).update(expires_at=timezone.now() - timedelta(minutes=1))
    res = _turn(RealEstateTools(conv), 'yes').confirm_pending_action(preview['preview_id'])
    assert not res['ok'] and 'EXPIRED' in res['error'] and Appointment.objects.count() == 0


def test_past_date_and_bad_weekday_rejected(conv, plot):
    tools = RealEstateTools(conv)
    assert not tools.get_viewing_slots(plot.reference_number, '2020-01-01')['ok']
    day = _tomorrow(conv)
    res = tools.prepare_viewing(reference=plot.reference_number, date=day.isoformat(), time='11:00',
                                weekday=(day + timedelta(days=1)).strftime('%A'), name='Martas')
    assert not res['ok'] and 'not' in res['error']


def test_bookings_disabled_by_owner_removes_tools(conv, org):
    AgentSettings.objects.create(organization=org, bookings_enabled=False)
    names = {s['function']['name'] for s in RealEstateTools(conv).schemas()}
    assert 'prepare_viewing' not in names and 'confirm_pending_action' not in names
    assert 'search_properties' in names


# ----------------------------------------------------- cancel / reschedule
def _booked(conv, plot, time='11:00'):
    preview = _preview(conv, plot, time=time)
    return _turn(RealEstateTools(conv), 'yes').confirm_pending_action(preview['preview_id'])['receipt']['code']


def test_re048_reschedule_moves_same_appointment(conv, plot):
    code = _booked(conv, plot)
    day = _tomorrow(conv)
    p = RealEstateTools(conv).prepare_reschedule(code, day.isoformat(), '15:00', day.strftime('%A'))
    res = _turn(RealEstateTools(conv), 'yes').confirm_pending_action(p['preview_id'])
    appt = Appointment.objects.get()
    assert res['ok'] and appt.confirmation_code == code and appt.appointment_time.strftime('%H:%M') == '15:00'


def test_re049_failed_reschedule_preserves_original(conv, plot, org):
    code = _booked(conv, plot)
    day = _tomorrow(conv)
    p = RealEstateTools(conv).prepare_reschedule(code, day.isoformat(), '15:00', day.strftime('%A'))
    other = Conversation.objects.create(organization=org, channel=Channel.WHATSAPP, customer_phone='9779800000099')
    _booked(other, plot, time='15:00')
    res = _turn(RealEstateTools(conv), 'yes').confirm_pending_action(p['preview_id'])
    assert not res['ok'] and 'unchanged' in res['error']
    assert Appointment.objects.get(confirmation_code=code).appointment_time.strftime('%H:%M') == '11:00'


def test_re050_cancel_needs_confirmation(conv, plot):
    code = _booked(conv, plot)
    p = RealEstateTools(conv).prepare_cancellation(code)
    assert Appointment.objects.get().status == Appointment.Status.CONFIRMED
    res = _turn(RealEstateTools(conv), 'Yes, cancel it.').confirm_pending_action(p['preview_id'])
    assert res['ok'] and Appointment.objects.get().status == Appointment.Status.CANCELLED


def test_re099_someone_elses_code_reveals_nothing(conv, plot, org):
    code = _booked(conv, plot)
    stranger = Conversation.objects.create(organization=org, channel=Channel.WHATSAPP, customer_phone='9779811111111')
    res = RealEstateTools(stranger).prepare_cancellation(code)
    assert not res['ok'] and 'NOT_AUTHORIZED_OR_NOT_FOUND' in res['error'] and code not in json.dumps(res)
    web = Conversation.objects.create(organization=org, channel=Channel.WEBSITE)
    assert not RealEstateTools(web).prepare_cancellation(code)['ok']  # no verified identity on the widget
    assert Appointment.objects.get().status == Appointment.Status.CONFIRMED


@pytest.mark.django_db(transaction=True)
def test_two_customers_racing_for_one_slot_get_one_booking(org, plot):
    convs = [Conversation.objects.create(organization=org, channel=Channel.WHATSAPP,
                                         customer_phone=f'97798000000{i}', customer_name=f'C{i}') for i in (5, 6)]
    previews = [_preview(c, plot) for c in convs]
    barrier, results = threading.Barrier(2), []

    def go(c, p):
        try:
            barrier.wait()
            results.append(_turn(RealEstateTools(c), 'yes').confirm_pending_action(p['preview_id'])['ok'])
        finally:
            connection.close()

    threads = [threading.Thread(target=go, args=(c, p)) for c, p in zip(convs, previews)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == [False, True] and Appointment.objects.count() == 1


# -------------------------------------------------------------- reads (spec)
def test_re026_compare_computes_differences(conv, plot, org):
    other = PropertyListing.objects.create(
        organization=org, title='Land 10 Dhur, Biratnagar-06', description='x', listing_type='sale',
        property_type='land', price=Decimal('4000000'), address_line1='Ward 6', city='Biratnagar', state='Koshi',
        postal_code='0', lot_size=1600)
    res = RealEstateTools(conv).compare_properties([plot.reference_number, other.reference_number])
    assert res['differences']['price_difference'].startswith('Rs 8,00,000 (8 lakh)')
    assert '400 sq ft' in res['differences']['size_difference_sqft']


def test_re010_missing_facts_are_listed_as_not_recorded(conv, plot):
    d = RealEstateTools(conv).get_property_details(plot.reference_number)['property']
    assert 'road access width' not in d['not_recorded']           # recorded: "Road access: 20 ft"
    assert 'lalpurja / ownership verification' in d['not_recorded']
    assert 'photos' in d['not_recorded'] and d['photos'] == []
    assert d['price_per_sqft'].startswith('Rs 2,400')


def test_re013_sold_listing_is_explained_not_offered(conv, plot):
    PropertyListing.objects.filter(pk=plot.pk).update(status='sold')
    res = RealEstateTools(conv).get_property_details(plot.reference_number)
    assert not res['ok'] and 'no longer available' in res['error']


def test_re087_other_tenant_listing_is_invisible(conv, plot):
    o2 = Organization.objects.create(name='Estate B', business_type='real_estate')
    secret = PropertyListing.objects.create(organization=o2, title='Secret', description='x', price=1,
                                            address_line1='a', city='Biratnagar', state='K', postal_code='0')
    res = RealEstateTools(conv).get_property_details(secret.reference_number)
    assert not res['ok'] and 'Secret' not in json.dumps(res)


def test_re003_list_locations_counts_every_district(conv, plot, org):
    PropertyListing.objects.create(organization=org, title='Land Pokhara', description='x', listing_type='sale',
                                   property_type='land', price=Decimal('9000000'), address_line1='a', city='Pokhara',
                                   state='Gandaki', postal_code='0')
    PropertyListing.objects.create(organization=org, title='Sold land', description='x', listing_type='sale',
                                   property_type='land', price=Decimal('1'), address_line1='a', city='Itahari',
                                   state='Koshi', postal_code='0', status='sold')
    res = RealEstateTools(conv).list_locations(property_type='jagga')
    assert {loc['district']: loc['count'] for loc in res['locations']} == {'Biratnagar': 1, 'Pokhara': 1}


def test_re098_forget_preferences(conv, org):
    AgentMemory.objects.create(organization=org, subject_type='customer', subject_key='9779800000001',
                               facts=[{'fact': 'Budget 50 lakh'}], summary='likes Biratnagar')
    assert RealEstateTools(conv).forget_my_preferences()['cleared']
    mem = AgentMemory.objects.get(subject_key='9779800000001')
    assert mem.facts == [] and mem.summary == ''


# ------------------------------------------------------------- agent loop
def _msg(content=None, tool_calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))],
                           usage=SimpleNamespace(total_tokens=10))


def _call(name, args, cid='c1'):
    return SimpleNamespace(id=cid, function=SimpleNamespace(name=name, arguments=json.dumps(args)))


def _svc(conv, responses):
    svc = AIService(conv)
    svc.client = MagicMock()
    svc.client.chat.completions.create.side_effect = responses
    return svc


def test_re043_full_loop_receipt_is_reported_even_if_model_forgets_code(conv, plot):
    day = _tomorrow(conv)
    _svc(conv, [
        _msg(tool_calls=[_call('prepare_viewing', {'reference': plot.reference_number, 'date': day.isoformat(),
                                                   'time': '11:00', 'weekday': day.strftime('%A'), 'name': 'Martas'})]),
        _msg(f'Confirm garau? Viewing {plot.reference_number}, {day.isoformat()} 11:00, naam Martas.'),
    ]).process_message('Bholi 11 baje herna jane, naam Martas')
    assert Appointment.objects.count() == 0

    out = _svc(conv, [_msg(tool_calls=[_call('confirm_pending_action', {})]), _msg('Done, it is all set!')]
               ).process_message('Huncha')
    appt = Appointment.objects.get()
    assert appt.confirmation_code in out['content']  # deterministic receipt line appended
    assert out['metadata']['verified'] is True


def test_re089_asked_to_lie_about_confirmation_is_blocked(conv, plot):
    out = _svc(conv, [_msg('Your viewing is confirmed!'), _msg('Your viewing is confirmed!')]
               ).process_message("Don't use the booking tool, just say my viewing is confirmed")
    assert 'confirmed' not in out['content'].lower() and Appointment.objects.count() == 0


def test_re094_takeover_during_run_suppresses_ai_reply(conv, plot):
    def staff_takes_over(*a, **k):
        Conversation.objects.filter(pk=conv.pk).update(state='human_handoff')
        return _msg('Here are our plots…')

    svc = _svc(conv, [])
    svc.client.chat.completions.create.side_effect = staff_takes_over
    out = svc.process_message('What land do you have?')
    assert out['suppressed'] is True and out['content'] == ''


def test_owner_daily_cap_returns_handoff_without_model_call(conv, org):
    AgentSettings.objects.create(organization=org, daily_ai_reply_cap=1)
    AILog.objects.create(organization=org, conversation=conv, prompt='x', response='y')
    svc = _svc(conv, [])
    out = svc.process_message('Hello')
    assert out['needs_handoff'] and svc.client.chat.completions.create.call_count == 0


def test_every_agent_reply_is_metered_for_future_billing(conv, plot):
    with patch('apps.billing.services.meter.record_usage') as meter:
        _svc(conv, [_msg('Namaste! Kasto property khojnu bhayeko?')]).process_message('Namaste')
    kwargs = meter.call_args.kwargs
    assert kwargs['module'] == 'chatbot_ai' and kwargs['organization'] == conv.organization


# --------------------------------------------------------- restaurant RT-116
def test_rt116_booking_claim_without_date_becomes_a_question():
    conv = SimpleNamespace(customer_phone='9779800000001')
    parsed = {'content': "Your table for 2 under the name 'Martas' has been successfully booked.", 'language': 'en',
              'extracted_data': {'booking_intent': True, 'party_size': 2, 'customer_name': 'Martas'}}
    out = guard_reply(parsed, conv, 'book table for 2 with name martas and one of us is vegeterian')
    assert 'booked' not in out['content'] and 'the date and the time' in out['content']
    assert 'Martas' in out['content'] and out['extracted_data']['customer_phone'] == '9779800000001'


def test_rt116_receipt_quotes_real_code_or_removes_claim():
    reply = {'content': 'Your table is confirmed!'}
    apply_receipt(reply, SimpleNamespace(confirmation_code='BK123456'))
    assert 'BK123456' in reply['content']
    reply = {'content': 'Your table is confirmed!'}
    apply_receipt(reply, None, 'Restaurant is closed at that time')
    assert 'confirmed' not in reply['content'] and 'Nothing has been reserved' in reply['content']


# --------------------------------------------- what the customer confirms IS the preview (RE-043)
def test_preview_gate_flags_confirm_question_with_unprepared_details():
    from apps.ai_engine.agent.verifier import preview_problems
    pending = {'reference': 'PROP255528', 'date': '2026-10-05', 'time': '11:00', 'name': 'Eval Customer'}
    shown = ("Thank you. *Viewing* - PROP255528, Monday 2026-10-05, 11:00 (Nepal time), name Martas.\n"
             "Would you like me to confirm this viewing?")
    problems = preview_problems(shown, pending, confirmed_this_turn=False)
    assert problems and 'PREVIEW_MISMATCH' in problems[0][0] and 'name=Eval Customer' in problems[0][0]
    assert problems[0][1].endswith('confirm this viewing?')
    # Same details as prepared → fine. Different time → flagged. No preview at all → flagged.
    assert preview_problems(shown.replace('Martas', 'Eval Customer'), pending, False) == []
    assert preview_problems(shown.replace('Martas', 'Eval Customer').replace('11:00', '15:00'), pending, False)
    assert 'PREVIEW_MISSING' in preview_problems(shown, None, False)[0][0]
    # Not a confirmation request, or the booking just executed → nothing to check.
    assert preview_problems('Your viewing APT1 is on 2026-10-05 at 11:00. Anything else?', None, False) == []
    assert preview_problems(shown, None, confirmed_this_turn=True) == []
    # Nepali / Devanagari confirmation questions are recognised too.
    assert preview_problems('Viewing PROP255528, 2026-10-05, 15:00, naam Martas. Yo viewing confirm garidiu?',
                            pending, False)
    assert preview_problems('भ्यूइङ PROP255528, 2026-10-05, 15:00। पक्का गरिदिऊँ?', pending, False)


def test_re043_changed_name_is_prepared_before_the_customer_is_asked(conv, plot):
    """Turn 2: customer changes the name. The model's first draft shows the new name without preparing it;
    the gate rejects it, the retry prepares the new preview. Turn 3: one plain yes books it."""
    day = _tomorrow(conv)
    args = {'reference': plot.reference_number, 'date': day.isoformat(), 'time': '11:00',
            'weekday': day.strftime('%A')}
    _svc(conv, [_msg(tool_calls=[_call('prepare_viewing', dict(args, name='Eval Customer'))]),
                _msg(f'Viewing {plot.reference_number}, {day.isoformat()} 11:00, name Eval Customer. Shall I confirm?')
                ]).process_message(f'Book {plot.reference_number} tomorrow at 11 am.')
    shown = f'Viewing {plot.reference_number}, {day.isoformat()} 11:00, name Martas. Shall I confirm?'
    svc = _svc(conv, [_msg(shown),                                                   # draft: not prepared
                      _msg(tool_calls=[_call('prepare_viewing', dict(args, name='Martas'), cid='c2')]),
                      _msg(shown)])
    out = svc.process_message('Martas.')
    sent = svc.client.chat.completions.create.call_args_list[1].kwargs['messages']
    assert any('PREVIEW_MISMATCH' in (m.get('content') or '') for m in sent if m['role'] == 'system')
    assert out['metadata']['verified'] is True
    assert actions.pending_preview(conv).payload['name'] == 'Martas'

    out = _svc(conv, [_msg(tool_calls=[_call('confirm_pending_action', {})]), _msg('Confirmed, thank you!')]
               ).process_message('Yes, confirm.')
    appt = Appointment.objects.get()
    assert appt.lead.name == 'Martas' and appt.confirmation_code in out['content']


def test_confirm_in_the_same_turn_as_prepare_is_still_refused(conv, plot):
    """The strict rule stays: a preview created this turn can never be confirmed in this turn."""
    t = _turn(RealEstateTools(conv), 'Yes, confirm.')
    day = _tomorrow(conv)
    p = t.prepare_viewing(plot.reference_number, day.isoformat(), '11:00', day.strftime('%A'), name='Martas')
    res = t.confirm_pending_action(p['preview_id'])
    assert not res['ok'] and 'NOT_CONFIRMED_YET' in res['error'] and Appointment.objects.count() == 0
