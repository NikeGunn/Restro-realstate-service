"""
Regression tests for the 2026-10-03 production failures on the Nepal agency:

1. "Maile jagga ko barema sodhnu thio" → English "could you clarify?" loop, no land shown.
2. Invented rooms/prices written as "HK₨7,500" slipped through the gate (₨ not recognised,
   and a made-up max_price in the tool ARGUMENTS counted as evidence).
3. Follow-ups lost the facts from the previous turn's tool results.
OpenAI is mocked - these pin the guarantees, not model quality.
"""
import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.accounts.models import Location, Organization
from apps.ai_engine.agent import language as reply_lang
from apps.ai_engine.agent import vocab
from apps.ai_engine.agent.tools import RealEstateTools
from apps.ai_engine.agent.verifier import verify_reply
from apps.ai_engine.models import AILog
from apps.ai_engine.services import AIService
from apps.messaging.models import Channel, Conversation
from apps.realestate.models import PropertyListing

pytestmark = pytest.mark.django_db


def _listing(org, title, ptype, ltype, price, city, **extra):
    return PropertyListing.objects.create(
        organization=org, title=title, description=extra.pop('description', title), listing_type=ltype,
        property_type=ptype, price=Decimal(price), address_line1='x', city=city, state='Bagmati',
        postal_code='0', country='Nepal', **extra)


@pytest.fixture
def nepal_org():
    o = Organization.objects.create(name='Ghar Jagga', business_type='real_estate')
    Location.objects.create(organization=o, name='KTM', is_primary=True, is_active=True, country='Nepal')
    _listing(o, 'Single Room near TU, Kirtipur', 'room', 'rent', '6000', 'Kirtipur')
    _listing(o, 'Furnished Room, New Baneshwor', 'room', 'rent', '12000', 'Kathmandu', neighborhood='New Baneshwor',
             features=['Attached bathroom', 'Wifi'])
    _listing(o, 'Residential Land 5 Aana, Bhaisepati', 'land', 'sale', '21000000', 'Lalitpur')
    _listing(o, 'Plot 8 Aana, Bhaktapur', 'land', 'sale', '16000000', 'Bhaktapur')
    return o


@pytest.fixture
def nepal_conv(nepal_org):
    return Conversation.objects.create(organization=nepal_org, channel=Channel.WHATSAPP,
                                       customer_phone='9779812345678', customer_name='Nikhil')


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


# ---------------------------------------------------------------- vocabulary
@pytest.mark.parametrize('word,expected', [
    ('jagga', 'land'), ('जग्गा', 'land'), ('plot', 'land'), ('ropani', 'land'), ('kotha', 'room'),
    ('कोठा', 'room'), ('ghar', 'house'), ('flat', 'apartment'), ('2BHK', 'apartment'), ('shutter', 'retail'),
    ('Land', 'land'), ('spaceship', ''),
])
def test_property_type_synonyms(word, expected):
    valid = {c for c, _ in PropertyListing.PropertyType.choices}
    assert vocab.normalize_property_type(word, valid) == expected


def test_jagga_search_returns_land_whichever_field_the_model_uses(nepal_conv):
    tools = RealEstateTools(nepal_conv)
    for kwargs in ({'property_type': 'jagga'}, {'keywords': 'jagga'}, {'keywords': 'sasto jagga kinne'},
                   {'property_type': 'land'}):
        out = tools.search_properties(**kwargs)
        assert out['exact_match'], kwargs
        assert {r['property_type'] for r in out['results']} == {'Land'}, kwargs
        assert out['total_matches'] == 2


def test_strict_search_labels_near_matches_and_never_widens_silently(nepal_conv):
    out = RealEstateTools(nepal_conv).search_properties(property_type='land', area='Pokhara', max_price=1000000)
    assert out['exact_match'] is False and out['results'] == []         # nothing is presented as a match
    assert out['near_matches'], 'closest real land is still shown, as an alternative'
    assert all(m['differs_from_request'] for m in out['near_matches'])   # each says what differs
    assert any('over the maximum budget' in d for m in out['near_matches'] for d in m['differs_from_request'])
    assert {loc['district'] for loc in out['same_type_elsewhere']} == {'Bhaktapur', 'Lalitpur'}


def test_keywords_match_any_word_and_features(nepal_conv):
    out = RealEstateTools(nepal_conv).search_properties(keywords='wifi parking')
    assert out['exact_match'] and out['results'][0]['title'] == 'Furnished Room, New Baneshwor'


def test_devanagari_area_alias(nepal_conv):
    out = RealEstateTools(nepal_conv).search_properties(area='भक्तपुर')
    assert out['exact_match'] and out['results'][0]['district'] == 'Bhaktapur'


def test_portfolio_overview_lists_every_category(nepal_conv):
    cats = {c['category']: c for c in RealEstateTools(nepal_conv).get_portfolio_overview()['categories']}
    assert cats['Land for sale']['listings'] == 2
    assert cats['Land for sale']['districts'] == ['Bhaktapur', 'Lalitpur']
    assert cats['Room for rent']['price_range'] == 'Rs 6,000 - Rs 12,000'


# ------------------------------------------------------------------ language
@pytest.mark.parametrize('text,style', [
    ('Maile jagga ko barema sodhnu thio', reply_lang.NEPALI_ROMAN),
    ('Kaha kaha upalabdha xa hola?', reply_lang.NEPALI_ROMAN),
    ('Malai kirtipur ma room chaiyo?', reply_lang.NEPALI_ROMAN),
    ('Kotha vada kati hola esko?', reply_lang.NEPALI_ROMAN),
    ('बानेश्वर नजिक furnished कोठा बजेट १५ हजार', reply_lang.NEPALI_DEVANAGARI),
    ('Can you tell me about my appointment date?', 'en'),
    ('I want a cheap room near the college', 'en'),
    ('Hello', 'en'),
])
def test_reply_style_detection(text, style):
    assert reply_lang.detect_reply_style(text, fallback='en') == style


@pytest.mark.parametrize('current,previous,style', [
    ('10000', ['Kathmandu ma room chaiyeko thyo?'], reply_lang.NEPALI_ROMAN),
    ('Kirtipur', ['Malai kotha chaiyo', '10000'], reply_lang.NEPALI_ROMAN),
    ('10000', ['I need a room in Kathmandu'], 'en'),
    ('Yes please', ['Malai kotha chaiyo'], 'en'),
])
def test_neutral_replies_keep_the_conversation_language(current, previous, style):
    assert reply_lang.sticky_reply_style(current, previous, fallback='en') == style


# ---------------------------------------------------------------------- gate
def test_gate_catches_rupee_sign_and_per_month_figures():
    ev = ['"price": "Rs 6,000/month"']
    assert not verify_reply('Room in Kirtipur: HK₨7,500/month.', ev, []).ok
    assert not verify_reply('Room in Kirtipur: ₨ 7,500', ev, []).ok
    assert not verify_reply('Room in Kirtipur costs 7,500 per month.', ev, []).ok
    assert not verify_reply('Kirtipur ko kotha 7500 ho.', ev, []).ok           # bare figure, no currency
    assert verify_reply('Kirtipur ko kotha Rs 6,000/month ho.', ev, []).ok


def test_gate_ignores_codes_dates_and_phones():
    ev = ['PROP958917 APT6GAFYO']
    reply = 'Booked PROP958917, code APT6GAFYO on 2026-10-13 at 10:00. Call +9779705651002.'
    assert verify_reply(reply, ev, [{'tool': 'book_viewing'}]).ok


def test_made_up_search_argument_cannot_verify_itself(nepal_conv):
    """The model invents max_price=7500 and then quotes it - previously the args counted as evidence."""
    svc = _service(nepal_conv, [
        _msg(tool_calls=[_call('search_properties', {'property_type': 'room', 'max_price': 7500})]),
        _msg('Kirtipur ma Rs 7,500 samma ko kotha cha.'),
        _msg('Kirtipur ma Rs 7,500 samma ko kotha cha.'),
    ])
    out = svc.process_message('Kirtipur ma sasto kotha cha?')
    assert '7,500' not in out['content']


# ------------------------------------------------------------------- runner
def test_jagga_question_gets_real_land_in_romanized_nepali(nepal_conv):
    svc = _service(nepal_conv, [
        _msg('Hajur, hamro sanga 2 ota jagga cha: Bhaisepati ma 5 aana Rs 2,10,00,000 (2.1 crore) ra '
             'Bhaktapur ma 8 aana Rs 1,60,00,000 (1.6 crore). Kun area ma herna chahanu huncha?'),
    ])
    out = svc.process_message('Maile jagga ko barema sodhnu thio')
    assert out['metadata']['verified'] is True
    assert '2.1 crore' in out['content']
    sent = svc.client.chat.completions.create.call_args.kwargs['messages']
    system = sent[0]['content']
    assert 'PORTFOLIO' in system and 'Residential Land 5 Aana, Bhaisepati' in system
    assert 'Land for sale: 2 listing(s) in Bhaktapur, Lalitpur' in system
    assert any(m['role'] == 'system' and 'Romanized Nepali' in m['content'] for m in sent[1:])


def test_tool_facts_carry_over_to_the_next_turn(nepal_conv):
    ref = PropertyListing.objects.get(title__startswith='Single Room').reference_number
    svc = _service(nepal_conv, [
        _msg(tool_calls=[_call('get_property_details', {'reference': ref})]),
        _msg(f'{ref} Kirtipur ko kotha Rs 6,000/month ho.'),
    ])
    svc.process_message('Kirtipur ko kotha ko detail?')
    log = AILog.objects.filter(conversation=nepal_conv).latest('created_at')
    assert log.context['tool_facts'] and ref in log.context['tool_facts'][0]

    svc2 = _service(nepal_conv, [_msg('Tyo kotha ko bhada Rs 6,000/month ho.')])
    svc2.process_message('Kotha vada kati hola esko?')
    system = svc2.client.chat.completions.create.call_args.kwargs['messages'][0]['content']
    assert 'FACTS FROM EARLIER TOOL CALLS' in system and ref in system.split('FACTS FROM EARLIER TOOL CALLS')[1]


def test_reasoning_model_uses_completion_token_budget(nepal_conv, settings):
    settings.AI_AGENT_MODEL = 'gpt-5.4-mini'
    svc = _service(nepal_conv, [_msg('Namaste! Kasto property khojnu bhayeko ho?')])
    svc.process_message('Namaste hajur')
    kwargs = svc.client.chat.completions.create.call_args.kwargs
    assert kwargs['model'] == 'gpt-5.4-mini'
    assert 'temperature' not in kwargs and kwargs['max_completion_tokens'] >= 2000
