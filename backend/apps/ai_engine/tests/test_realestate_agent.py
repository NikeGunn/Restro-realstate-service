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
from apps.ai_engine.agent.tools import RealEstateTools, format_money
from apps.ai_engine.agent.verifier import verify_reply
from apps.ai_engine.models import AgentMemory
from apps.ai_engine.services import AIService
from apps.messaging.models import Channel, Conversation, Message, MessageSender
from apps.realestate.models import Appointment, PropertyListing

pytestmark = pytest.mark.django_db


@pytest.fixture
def org():
    o = Organization.objects.create(name='Acme Realty', business_type='real_estate')
    Location.objects.create(organization=o, name='HQ', is_primary=True, is_active=True,
                            country='Hong Kong', timezone='Asia/Hong_Kong')
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


def test_search_whole_territory_is_not_an_area_filter(conv, listing):
    assert RealEstateTools(conv).search_properties(area='Hong Kong')['total_matches'] == 1
    assert RealEstateTools(conv).search_properties(area='香港')['total_matches'] == 1


def test_search_price_asc_sort(conv, listing):
    PropertyListing.objects.create(organization=conv.organization, title='Cheaper', description='x', listing_type='rent',
                                   price=Decimal('9000'), address_line1='a', city='Wan Chai', state='HK', postal_code='0')
    res = RealEstateTools(conv).search_properties(listing_type='rent', sort='price_asc')
    assert [r['title'] for r in res['results']][0] == 'Cheaper'


def test_salvage_drops_only_unverifiable_sentence():
    from apps.ai_engine.agent.verifier import salvage
    reply = "No 2-beds under HK$15,000 right now. Our most affordable rental is the Wan Chai flat at HK$32,000/month. Want details?"
    gate = verify_reply(reply, ['"price": "HK$32,000/month"'], [])
    assert not gate.ok and not gate.fatal
    trimmed = salvage(reply, gate)
    assert 'HK$15,000' not in trimmed and 'HK$32,000' in trimmed
    assert verify_reply(trimmed, ['"price": "HK$32,000/month"'], []).ok


def test_salvage_refuses_false_action_claims():
    from apps.ai_engine.agent.verifier import salvage
    gate = verify_reply("Your viewing is confirmed!", [], [])
    assert gate.fatal and salvage("Your viewing is confirmed!", gate) == ''


def test_vague_budget_turn_never_dead_ends(conv, listing):
    """The prod WhatsApp failure: model invents a budget twice -> must salvage, not fallback."""
    bad = "Sorry, nothing under HK$15,000. The Wan Chai 2-bed is HK$32,000/month — want to see it?"
    search = _msg(tool_calls=[_call('search_properties', {'listing_type': 'rent', 'sort': 'price_asc'})])
    replies = iter([search, _msg(bad), _msg(bad)])
    svc = _service(conv, [])
    svc.client.chat.completions.create.side_effect = lambda *a, **k: next(replies)
    out = svc.process_message('I want cheap rooms i am student')
    assert out['metadata']['verified'] is True
    assert 'HK$32,000' in out['content'] and 'HK$15,000' not in out['content']


# ------------------------------------------------------------- Nepal market
@pytest.fixture
def nepal_conv():
    o = Organization.objects.create(name='Ghar Jagga', business_type='real_estate')
    Location.objects.create(organization=o, name='KTM', is_primary=True, is_active=True, country='Nepal')
    PropertyListing.objects.create(organization=o, title='Room near TU', description='x', listing_type='rent',
                                   property_type='room', price=Decimal('6000'), address_line1='a', city='Kirtipur',
                                   state='Bagmati', postal_code='0')
    return Conversation.objects.create(organization=o, channel=Channel.WHATSAPP, customer_phone='9779812345678')


def test_nepal_market_uses_npr_and_kathmandu_time(nepal_conv):
    tools = RealEstateTools(nepal_conv)
    assert tools.market['currency'] == 'Rs' and tools.market['tz'] == 'Asia/Kathmandu'
    assert tools.search_properties(area='Nepal')['results'][0]['price'] == 'Rs 6,000/month'


def test_lakh_crore_formatting():
    from apps.ai_engine.agent.tools import MARKETS
    assert format_money(Decimal('38500000'), MARKETS['nepal']) == 'Rs 3,85,00,000 (3.85 crore)'
    assert format_money(Decimal('250000'), MARKETS['nepal']) == 'Rs 2,50,000 (2.5 lakh)'


def test_gate_understands_npr_lakh_crore():
    ev = ['"price": "Rs 3,85,00,000 (3.85 crore)"', '"price": "Rs 6,000/month"']
    assert verify_reply("The house is Rs 3.85 crore and the room Rs 6,000/month.", ev, []).ok
    assert not verify_reply("Room only Rs 4,000 per month!", ev, []).ok
    assert not verify_reply("Land is 2 crore.", ev, []).ok
    assert verify_reply("Your budget of 15 hajar is noted; 50 lakh too.", ev + ['kotha 15 hajar samma, budget 50 lakh'], []).ok
    assert not verify_reply("Your budget of 15 hajar is noted.", ev, []).ok  # hajar is checked too
