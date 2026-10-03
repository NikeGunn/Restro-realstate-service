"""
Real-estate agent: tool loop, verification gate and persistent memory.
OpenAI is mocked — these pin the guarantees, not model quality.
"""
import json
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.accounts.models import Location, Organization
from apps.ai_engine.agent import memory as agent_memory
from apps.ai_engine.agent.tools import RealEstateTools, hk_now
from apps.ai_engine.agent.verifier import verify_reply
from apps.ai_engine.models import AgentMemory
from apps.ai_engine.services import AIService
from apps.messaging.models import Channel, Conversation, Message, MessageSender
from apps.realestate.models import Appointment, PropertyListing

pytestmark = pytest.mark.django_db


@pytest.fixture
def org():
    o = Organization.objects.create(name='Acme Realty', business_type='real_estate')
    Location.objects.create(organization=o, name='HQ', is_primary=True, is_active=True)
    return o


@pytest.fixture
def listing(org):
    return PropertyListing.objects.create(
        organization=org, title='Modern 2-Bed, Wan Chai', description='Furnished', listing_type='rent',
        property_type='apartment', price=Decimal('32000'), rent_period='monthly',
        address_line1='200 QRE', city='Wan Chai', state='HK', postal_code='0', bedrooms=2,
    )


@pytest.fixture
def conv(org):
    return Conversation.objects.create(organization=org, channel=Channel.WHATSAPP,
                                       customer_phone='85291234567', customer_name='Priya')


def _msg(content=None, tool_calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))],
                           usage=SimpleNamespace(total_tokens=10))


def _call(name, args, cid='c1'):
    return SimpleNamespace(id=cid, function=SimpleNamespace(name=name, arguments=json.dumps(args)))


def _service(conv, responses):
    svc = AIService(conv)
    svc.client = MagicMock()
    svc.client.chat.completions.create.side_effect = responses
    return svc


# ------------------------------------------------------------------ verifier
def test_gate_rejects_invented_reference_and_price():
    r = verify_reply("Try PROP999999 at HK$9,999,999", ['{"reference": "PROP111111", "price": "HK$32,000"}'], [])
    assert not r.ok and len(r.problems) == 2


def test_gate_accepts_grounded_price_in_million_form():
    assert verify_reply("It is HK$18.8 million.", ['"price": "HK$18,800,000"'], []).ok


def test_gate_rejects_booking_claim_without_tool():
    assert not verify_reply("Your viewing is confirmed for 3pm!", [], []).ok


def test_gate_allows_booking_claim_after_tool():
    assert verify_reply("Your viewing is confirmed, code APTABC123.", ['"APTABC123"'],
                        [{'tool': 'book_viewing'}]).ok


# --------------------------------------------------------------------- tools
def test_book_viewing_rejects_out_of_hours_and_past(conv, listing):
    tools = RealEstateTools(conv)
    tomorrow = (hk_now() + timedelta(days=1)).date().isoformat()
    assert not tools.book_viewing(date=tomorrow, time='23:00', property_reference=listing.reference_number)['ok']
    assert not tools.book_viewing(date='2020-01-01', time='15:00')['ok']
    assert Appointment.objects.count() == 0


def test_book_viewing_creates_appointment_and_memory(conv, listing):
    tomorrow = (hk_now() + timedelta(days=1)).date().isoformat()
    res = RealEstateTools(conv).book_viewing(date=tomorrow, time='15:00', name='Priya Sharma',
                                             property_reference=listing.reference_number)
    assert res['ok'] and res['appointment']['confirmation_code'].startswith('APT')
    mem = AgentMemory.objects.get(subject_key='85291234567')
    assert mem.display_name == 'Priya Sharma'
    assert any(res['appointment']['confirmation_code'] in f['fact'] for f in mem.facts)


def test_search_is_tenant_scoped(conv, listing):
    other = Organization.objects.create(name='Other', business_type='real_estate')
    PropertyListing.objects.create(organization=other, title='Secret', description='x', price=1,
                                   address_line1='a', city='Wan Chai', state='HK', postal_code='0')
    titles = [r['title'] for r in RealEstateTools(conv).search_properties(area='Wan Chai')['results']]
    assert titles == ['Modern 2-Bed, Wan Chai']


# ---------------------------------------------------------------- agent loop
def test_hallucinated_booking_never_reaches_customer(conv, listing):
    Message.objects.create(conversation=conv, sender=MessageSender.CUSTOMER, content='book it tomorrow 3pm')
    svc = _service(conv, [_msg("Done! Your viewing is confirmed."), _msg("Your viewing is booked!")])
    out = svc.process_message('book it tomorrow 3pm')
    assert 'confirmed' not in out['content'].lower() and 'booked' not in out['content'].lower()
    assert out['metadata']['verified'] is False
    assert Appointment.objects.count() == 0


def test_tool_loop_books_then_confirms(conv, listing):
    tomorrow = (hk_now() + timedelta(days=1)).date().isoformat()
    first = _msg(tool_calls=[_call('book_viewing', {'date': tomorrow, 'time': '15:00', 'name': 'Priya',
                                                    'property_reference': listing.reference_number})])

    def second():
        return _msg(f"Your viewing is confirmed. Code {Appointment.objects.get().confirmation_code}.")

    replies = iter([lambda: first, second])
    svc = _service(conv, [])
    svc.client.chat.completions.create.side_effect = lambda *a, **k: next(replies)()

    out = svc.process_message('book the Wan Chai flat tomorrow 3pm, I am Priya')
    appt = Appointment.objects.get()
    assert out['metadata']['verified'] is True
    assert appt.confirmation_code in out['content']
    assert out['extracted_data'] == {}  # channels must not create a second appointment


def test_current_message_not_duplicated_in_history(conv):
    Message.objects.create(conversation=conv, sender=MessageSender.CUSTOMER, content='hello')
    svc = _service(conv, [_msg("Hi Priya, how can I help?")])
    svc.process_message('hello')
    sent = svc.client.chat.completions.create.call_args.kwargs['messages']
    assert [m['content'] for m in sent if m['role'] == 'user'] == ['hello']


def test_memory_injected_for_returning_customer(conv):
    agent_memory.remember(conv.organization, 'customer', '85291234567', 'Has a dog', display_name='Priya')
    agent_memory.remember(conv.organization, 'owner', 'owner', 'Always offer a virtual tour to overseas buyers')
    svc = _service(conv, [_msg("Welcome back Priya!")])
    svc.process_message('hi again')
    system = svc.client.chat.completions.create.call_args.kwargs['messages'][0]['content']
    assert 'Has a dog' in system and 'virtual tour to overseas buyers' in system


def test_summarize_customer_folds_messages(conv):
    Message.objects.create(conversation=conv, sender=MessageSender.CUSTOMER, content='I need 3 beds near schools')
    client = MagicMock()
    client.chat.completions.create.return_value = _msg("- Needs 3 bedrooms near good schools")
    mem = agent_memory.summarize_customer(conv.organization, '85291234567', client=client)
    assert 'schools' in mem.summary and mem.summarized_until is not None
    assert 'Needs 3 bedrooms' in agent_memory.customer_memory_text(conv)


def test_gate_accepts_customer_stated_millions():
    assert verify_reply("Noted: expected price HK$9 million.", ["expecting 9 million"], []).ok


def test_book_viewing_rejects_weekday_mismatch(conv, listing):
    day = (hk_now() + timedelta(days=3)).date()
    wrong = (day + timedelta(days=1)).strftime('%A')
    res = RealEstateTools(conv).book_viewing(date=day.isoformat(), time='11:00', weekday=wrong, name='Priya')
    assert not res['ok'] and 'not' in res['error']
    assert Appointment.objects.count() == 0
