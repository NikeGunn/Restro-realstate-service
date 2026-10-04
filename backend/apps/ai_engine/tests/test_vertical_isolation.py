"""
Restaurant and real-estate must never bleed into each other (see vertical_guard.py for root causes).
The memory sample below is the real prod summary that poisoned a Nepal land agency on 2026-10-04.
"""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.accounts.models import Location, Organization
from apps.ai_engine.agent import memory as agent_memory
from apps.ai_engine.agent.runner import RealEstateAgent
from apps.ai_engine.models import AgentMemory
from apps.ai_engine.services import AIService
from apps.ai_engine.vertical_guard import clean_memory, enforce, off_vertical
from apps.messaging.models import Channel, Conversation, Message, MessageSender
from apps.realestate.models import PropertyListing

pytestmark = pytest.mark.django_db

POISONED = """**Profile**
- Customer: Swagat
- Has a vegan friend (specific dietary needs).
**Requirements**
- Looking for affordable 2-bedroom properties in Hong Kong as a student, budget under HK$15,000.
- Wants a shutter (shop unit) in Kathmandu Valley; monthly budget not yet stated.
**Properties Discussed**
1. **Modern 2-Bed near MTR, Wan Chai** - PROP958917, HK$32,000/month.
3. **Room in Kirtipur** - HK₨7,500/month, quiet area, suitable for students.
8. **Shutter on New Road, Kathmandu** - {ref}, Rs 65,000/month, 200 sq ft.
**Timeline of contact**
- 2026-01-14: Initial contact regarding restaurant booking.
- 2026-01-18: Inquiry about making a reservation for a table for 2.
- 2026-10-03: Discussed land and room options."""


@pytest.fixture
def org():
    o = Organization.objects.create(name='Kribaat Test', business_type='real_estate')
    Location.objects.create(organization=o, name='Kathmandu Office', is_primary=True, is_active=True,
                            country='Nepal', timezone='Asia/Kathmandu')
    return o


@pytest.fixture
def shutter(org):
    return PropertyListing.objects.create(
        organization=org, title='Shutter on New Road, suitable for a restaurant', description='prime market',
        listing_type='rent', property_type='retail', price=Decimal('65000'), rent_period='monthly',
        address_line1='New Road', city='Kathmandu', neighborhood='New Road', state='Bagmati', postal_code='',
        country='Nepal')


@pytest.fixture
def conv(org):
    return Conversation.objects.create(organization=org, channel=Channel.WHATSAPP, customer_phone='9779705651002')


def _msg(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=None))],
                           usage=SimpleNamespace(total_tokens=10))


def _svc(conv, replies):
    svc = AIService(conv)
    svc.client = MagicMock()
    svc.client.chat.completions.create.side_effect = [_msg(r) for r in replies]
    return svc


# ------------------------------------------------------------------ the guard
@pytest.mark.parametrize('reply,hits', [
    ('I can help you with our menu, opening hours, bookings.', ['menu']),
    ('Shall I book a table for 2 tonight?', ['book a table']),
    ('Rs 65,000/month, water supply and kitchen are recorded.', []),
    ('Our office opening hours are 10 to 6.', []),
])
def test_off_vertical_for_real_estate(reply, hits):
    assert off_vertical('real_estate', reply) == hits


def test_customer_words_may_be_echoed():
    assert off_vertical('real_estate', "Hajur, ma menu dina sakdina.", ['menu paam na']) == []


def test_restaurant_org_never_talks_listings():
    assert set(off_vertical('restaurant', 'Your viewing of PROP123456 is confirmed.')) == {'prop123456', 'viewing'}
    org = SimpleNamespace(business_type='restaurant', name='Cafe', id=1)
    assert 'menu' in enforce(org, 'Here is jagga for sale.', 'hi')


# ------------------------------------------------------------------ agent gate
def test_agent_draft_that_mentions_the_menu_is_rewritten(conv):
    Message.objects.create(conversation=conv, sender=MessageSender.CUSTOMER, content='timi ke garchau?')
    out = _svc(conv, ['I can help with our menu and table bookings.',
                      'Hajur, ma property sahayak hu. Kotha, flat ra jagga khojna sahayog garchhu.',
                      'Hajur, ma property sahayak hu. Kotha, flat ra jagga khojna sahayog garchhu.']
               ).process_message('timi ke garchau?')
    assert 'menu' not in out['content'].lower() and 'property' in out['content'].lower()


def test_listing_fact_with_restaurant_word_is_allowed(conv, shutter):
    Message.objects.create(conversation=conv, sender=MessageSender.CUSTOMER, content='new road shutter?')
    reply = f'Hajur, {shutter.reference_number} - Shutter on New Road, suitable for a restaurant - Rs 65,000/month.'
    out = _svc(conv, [reply, reply, reply]).process_message('new road shutter?')
    assert 'restaurant' in out['content']


def test_last_line_of_defence_on_non_agent_paths(conv):
    """Even a path that bypasses the agent (fast paths, manager replies) cannot leak."""
    svc = AIService(conv)
    svc._process_message = lambda text: {'content': 'Our menu has momo.', 'metadata': {}, 'language': 'en'}
    out = svc.process_message('hello')
    assert 'menu' not in out['content'] and 'property assistant' in out['content']


# ------------------------------------------------------------------ memory hygiene
def test_poisoned_prod_summary_is_cleaned(shutter):
    text = POISONED.format(ref=shutter.reference_number)
    clean = clean_memory(text, 'real_estate', [shutter.reference_number], 'Rs')
    for gone in ('vegan', 'Hong Kong', 'PROP958917', 'HK₨', 'restaurant booking', 'table for 2'):
        assert gone not in clean
    assert shutter.reference_number in clean and 'Kathmandu Valley' in clean


def test_agent_prompt_never_sees_the_poison(conv, shutter):
    AgentMemory.objects.create(organization=conv.organization, subject_type='customer',
                               subject_key='9779705651002', summary=POISONED.format(ref=shutter.reference_number))
    prompt = RealEstateAgent(AIService(conv))._system_prompt('en')
    assert 'HK$' not in prompt and 'vegan' not in prompt and 'restaurant booking' not in prompt


def test_summarizer_ignores_archived_chats(org, conv):
    old = Conversation.objects.create(organization=org, channel=Channel.WHATSAPP, customer_phone='9779705651002',
                                      state='archived')
    Message.objects.create(conversation=old, sender=MessageSender.CUSTOMER, content='Table for 2 at 7pm please')
    Message.objects.create(conversation=conv, sender=MessageSender.CUSTOMER, content='Kirtipur ma kotha chahiyo')
    client = MagicMock()
    client.chat.completions.create.return_value = _msg('- Wants a room in Kirtipur.')
    agent_memory.summarize_customer(org, '9779705651002', client=client)
    prompt = client.chat.completions.create.call_args.kwargs['messages'][0]['content']
    assert 'Kirtipur' in prompt and 'Table for 2' not in prompt


def test_business_change_clears_customer_memory(org):
    AgentMemory.objects.create(organization=org, subject_type='customer', subject_key='977',
                               summary='booked a table', facts=[{'fact': 'likes momo'}])
    AgentMemory.objects.create(organization=org, subject_type='owner', subject_key='owner',
                               facts=[{'fact': 'be polite'}])
    org.business_type = 'restaurant'
    org.save()
    cust = AgentMemory.objects.get(organization=org, subject_type='customer')
    assert cust.summary == '' and cust.facts == []
    assert AgentMemory.objects.get(organization=org, subject_type='owner').facts  # owner playbook kept
