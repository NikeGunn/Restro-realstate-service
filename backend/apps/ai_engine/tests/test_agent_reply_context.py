"""
"Long-press → Reply" and connecting earlier dots.

Root cause (2026-10-04): WhatsApp sends the id of the quoted message in `context.id`; we dropped it,
so "yo wala ko price kati?" replying to a photo sent an hour ago was read against the latest topic.
Photos we sent had no stored ids either, and nothing told the agent that a listing it talked about
earlier has changed since. These tests pin: ingest → stored reply_to → agent TURN BRIEF → quoted reply.
"""

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.accounts.models import Location, Organization
from apps.ai_engine.agent.runner import RealEstateAgent
from apps.ai_engine.services import AIService
from apps.channels.models import WhatsAppConfig
from apps.channels.whatsapp_service import WhatsAppService
from apps.messaging.models import Channel, Conversation, Message, MessageSender
from apps.messaging.reply_context import resolve
from apps.realestate.models import PropertyListing

pytestmark = pytest.mark.django_db
PHONE = '9779705651002'


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
def land(org):
    return PropertyListing.objects.create(
        organization=org, title='Land 4 Kattha, Butwal', description='plot', listing_type='sale',
        property_type='land', price=Decimal('8000000'), address_line1='Kalikanagar', city='Butwal',
        neighborhood='Kalikanagar', state='Lumbini', postal_code='', country='Nepal')


@pytest.fixture
def conv(org):
    return Conversation.objects.create(organization=org, channel=Channel.WHATSAPP, customer_phone=PHONE,
                                       customer_name='Nikhil Bhagat')


def _msg(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=None))],
                           usage=SimpleNamespace(total_tokens=10))


def _wa_service(org):
    cfg = WhatsAppConfig.objects.create(organization=org, phone_number_id='123', access_token='t', is_active=True)
    return WhatsAppService(cfg)


def _inbound(text, wamid, context_id=''):
    m = {'from': PHONE, 'id': wamid, 'timestamp': '1', 'type': 'text', 'text': {'body': text}}
    if context_id:
        m['context'] = {'from': '977', 'id': context_id}
    return m


# ---------------------------------------------------------------- resolve
def test_resolve_finds_our_text_reply_a_photo_and_unknown_ids(conv):
    Message.objects.create(conversation=conv, sender=MessageSender.AI, content='Shutter Rs 65,000/month',
                           channel_message_id='wamid.AI1',
                           ai_metadata={'attachment_ids': {'wamid.PH1': 'PROP481475 - Shutter (1/2)'}})
    assert resolve(conv, 'wamid.AI1')['content'] == 'Shutter Rs 65,000/month'
    photo = resolve(conv, 'wamid.PH1')
    assert photo['kind'] == 'photo' and 'PROP481475' in photo['content'] and photo['sender'] == 'assistant'
    assert resolve(conv, 'wamid.GONE') == {'id': 'wamid.GONE', 'found': False}
    assert resolve(conv, '') is None


def test_another_customers_message_id_never_leaks(org, conv):
    other = Conversation.objects.create(organization=org, channel=Channel.WHATSAPP, customer_phone='9779800000000')
    Message.objects.create(conversation=other, sender=MessageSender.AI, content='secret', channel_message_id='wamid.X')
    assert resolve(conv, 'wamid.X') == {'id': 'wamid.X', 'found': False}


# ---------------------------------------------------------------- WhatsApp ingest + outbound quote
def test_whatsapp_reply_context_is_stored_and_our_answer_quotes_it(org, conv, shutter):
    svc = _wa_service(org)
    Message.objects.create(conversation=conv, sender=MessageSender.AI, channel_message_id='wamid.OLD',
                           content=f'*{shutter.reference_number}* - Shutter on New Road - Rs 65,000/month')
    with patch.object(WhatsAppService, '_process_with_ai') as ai:
        svc._handle_incoming_message(_inbound('yo wala ko deposit kati?', 'wamid.NEW', 'wamid.OLD'), [])
    stored = Message.objects.get(channel_message_id='wamid.NEW')
    assert stored.ai_metadata['reply_to']['found'] and 'New Road' in stored.ai_metadata['reply_to']['content']
    ai.assert_called_once()

    reply = {'content': 'Hajur, deposit record ma chhaina.', 'confidence': 0.95, 'language': 'ne',
             'attachments': [{'type': 'image', 'url': 'https://media.kribaat.com/a.jpg', 'caption': 'cap 1/1'}]}
    with patch('apps.channels.whatsapp_service.AIService') as ai_cls, \
            patch.object(WhatsAppService, 'send_message', return_value='wamid.OUT') as send, \
            patch.object(WhatsAppService, 'send_image', return_value='wamid.IMG'):
        ai_cls.return_value.client = object()
        ai_cls.return_value.process_message.return_value = reply
        svc._process_with_ai(conv, stored)
    assert send.call_args.kwargs['reply_to'] == 'wamid.NEW'
    out = Message.objects.get(channel_message_id='wamid.OUT')
    assert out.ai_metadata['attachment_ids'] == {'wamid.IMG': 'cap 1/1'}


def test_plain_message_is_not_sent_as_a_quote(org, conv):
    svc = _wa_service(org)
    with patch.object(WhatsAppService, '_process_with_ai'):
        svc._handle_incoming_message(_inbound('hi', 'wamid.P1'), [])
    stored = Message.objects.get(channel_message_id='wamid.P1')
    assert 'reply_to' not in stored.ai_metadata
    with patch('apps.channels.whatsapp_service.AIService') as ai_cls, \
            patch.object(WhatsAppService, 'send_message', return_value='wamid.O2') as send:
        ai_cls.return_value.client = object()
        ai_cls.return_value.process_message.return_value = {'content': 'Namaste!', 'confidence': 0.9}
        svc._process_with_ai(conv, stored)
    assert send.call_args.kwargs['reply_to'] == ''


def test_send_message_puts_the_quote_in_the_graph_payload(org):
    svc = _wa_service(org)
    with patch('apps.channels.whatsapp_service.requests.post') as post:
        post.return_value.json.return_value = {'messages': [{'id': 'wamid.S'}]}
        svc.send_message('977', 'hi', reply_to='wamid.Q')
    assert post.call_args.kwargs['json']['context'] == {'message_id': 'wamid.Q'}


def test_image_caption_is_kept(org, conv):
    svc = _wa_service(org)
    m = {'from': PHONE, 'id': 'wamid.IMGIN', 'timestamp': '1', 'type': 'image',
         'image': {'id': 'media1', 'caption': 'yo ghar jasto chahiyo'}}
    with patch.object(WhatsAppService, '_process_with_ai'):
        svc._handle_incoming_message(m, [])
    assert 'yo ghar jasto chahiyo' in Message.objects.get(channel_message_id='wamid.IMGIN').content


# ---------------------------------------------------------------- the agent connects the dots
def _agent_prompt(conv, text):
    """Run one agent turn with a canned model; return everything the model was shown."""
    svc = AIService(conv)
    svc.client = MagicMock()
    svc.client.chat.completions.create.side_effect = [_msg('Hajur.')] * 4
    svc.process_message(text)
    msgs = svc.client.chat.completions.create.call_args_list[0].kwargs['messages']
    return msgs[0]['content'], msgs[-2]['content'], msgs


def test_quoted_old_photo_steers_the_turn_to_that_listing(conv, shutter, land):
    # An hour ago: the shutter photo. Since then: talk about Butwal land (the "latest topic").
    old = Message.objects.create(conversation=conv, sender=MessageSender.AI, channel_message_id='wamid.TXT',
                                 content=f'{shutter.reference_number} ko photo pathaie.',
                                 ai_metadata={'attachment_ids': {'wamid.PH': f'{shutter.reference_number} - Shutter (1/1)'}})
    Message.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(hours=1))
    Message.objects.create(conversation=conv, sender=MessageSender.AI,
                           content=f'1. *{land.reference_number}* - Land 4 Kattha, Butwal - Rs 80,00,000')
    Message.objects.create(conversation=conv, sender=MessageSender.CUSTOMER, content='yo wala ko bhada kati?',
                           channel_message_id='wamid.Q',
                           ai_metadata={'reply_to': resolve(conv, 'wamid.PH')})
    system, brief, _ = _agent_prompt(conv, 'yo wala ko bhada kati?')
    assert 'REPLIED TO an earlier assistant message' in brief and shutter.reference_number in brief
    assert '1 h ago' in brief
    # The ledger shows both listings with live status; the land is #1 in the latest list.
    assert f'{land.reference_number} (#1 in your latest list)' in system
    assert f'{shutter.reference_number}: Shutter on New Road' in system


def test_listing_changed_since_it_was_discussed_is_flagged(conv, shutter):
    m = Message.objects.create(conversation=conv, sender=MessageSender.AI,
                               content=f'{shutter.reference_number} - Rs 65,000/month')
    Message.objects.filter(pk=m.pk).update(created_at=timezone.now() - timedelta(days=2))
    PropertyListing.objects.filter(pk=shutter.pk).update(status='rented', updated_at=timezone.now())
    Message.objects.create(conversation=conv, sender=MessageSender.CUSTOMER, content='tyo shutter ajhai chha?')
    system, _, _ = _agent_prompt(conv, 'tyo shutter ajhai chha?')
    line = next(l for l in system.splitlines() if l.startswith(f'- {shutter.reference_number}'))
    assert 'NOT available now (rented)' in line and 'updated after it was last mentioned' in line


def test_returning_customer_gets_a_reconnect_hint(conv, shutter):
    m = Message.objects.create(conversation=conv, sender=MessageSender.AI, content=f'{shutter.reference_number} ok')
    Message.objects.filter(pk=m.pk).update(created_at=timezone.now() - timedelta(days=3))
    Message.objects.create(conversation=conv, sender=MessageSender.CUSTOMER, content='Hye')
    _, brief, _ = _agent_prompt(conv, 'Hye')
    assert 'back after 3 days ago' in brief or 'back after 3 days' in brief


def test_quote_of_a_message_we_no_longer_have_asks_instead_of_guessing(conv):
    Message.objects.create(conversation=conv, sender=MessageSender.CUSTOMER, content='yo kati ho?',
                           ai_metadata={'reply_to': {'id': 'wamid.GONE', 'found': False}})
    _, brief, _ = _agent_prompt(conv, 'yo kati ho?')
    assert 'cannot see any more' in brief


def test_history_marks_older_quoted_replies(conv, shutter):
    Message.objects.create(conversation=conv, sender=MessageSender.AI, channel_message_id='wamid.A',
                           content=f'{shutter.reference_number} Rs 65,000/month')
    Message.objects.create(conversation=conv, sender=MessageSender.CUSTOMER, content='yo herna milchha?',
                           ai_metadata={'reply_to': resolve(conv, 'wamid.A')})
    hist = RealEstateAgent(AIService(conv))._history('next question')
    assert any(h['content'].startswith('[replying to the assistant message') for h in hist)


def test_quoted_price_is_not_evidence_until_rechecked(conv, shutter):
    """The quoted text is shown, not trusted: a price only in the quote must be re-checked with a tool."""
    old = Message.objects.create(conversation=conv, sender=MessageSender.AI, channel_message_id='wamid.OLDP',
                                 content='Shutter was Rs 55,000/month')
    Message.objects.create(conversation=conv, sender=MessageSender.CUSTOMER, content='yo ho?', channel_message_id='q',
                           ai_metadata={'reply_to': resolve(conv, 'wamid.OLDP')})
    svc = AIService(conv)
    svc.client = MagicMock()
    svc.client.chat.completions.create.side_effect = [_msg('Hajur, Rs 55,000/month ho.')] * 4
    out = svc.process_message('yo ho?')
    assert '55,000' not in out['content']
    assert old.pk
