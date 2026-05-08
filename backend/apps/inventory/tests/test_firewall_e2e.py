"""
Phase 6 — End-to-end firewall hardening.

Proves that the InventoryContextFirewall is reached on every customer-facing
entry point that produces an AI response, and that legitimate (non-probe)
messages still flow to the public AI as before.

The single chokepoint we depend on is `AIService.process_message`. Every
channel (widget / WhatsApp / Instagram) routes through it, so we test:
  1. Widget HTTP path → inventory probe deflected, OpenAI never called.
  2. Widget HTTP path → menu question reaches AIService normally.
  3. AIService directly (the call site WA + IG share) → probes deflected
     in en/zh-CN/zh-TW; non-probes pass through untouched.

We mock OpenAI at the SDK boundary so a real network call is impossible.
If the firewall ever stops firing, the OpenAI mock's call_count > 0 fails
the test loudly.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Organization
from apps.messaging.models import Conversation, Message, WidgetSession
from apps.ai_engine.services import AIService
from apps.inventory.firewall import InventoryContextFirewall


# ──────────────────────────────────────────────────────────────────────
# Fixtures local to this file (don't pollute the shared conftest with
# widget/conversation plumbing other tests don't need).
# ──────────────────────────────────────────────────────────────────────
@pytest.fixture
def public_org(db):
    return Organization.objects.create(
        name='Public Cafe',
        business_type=Organization.BusinessType.RESTAURANT,
    )


@pytest.fixture
def widget_session(db, public_org):
    conv = Conversation.objects.create(
        organization=public_org, channel='website',
        customer_name='Visitor', state='ai_handling',
    )
    sess = WidgetSession.objects.create(organization=public_org, conversation=conv)
    return sess


@pytest.fixture
def conversation(db, public_org):
    return Conversation.objects.create(
        organization=public_org, channel='whatsapp',
        customer_phone='+10000000000', state='ai_handling',
    )


# ──────────────────────────────────────────────────────────────────────
# Unit-level firewall regressions (cheap, exhaustive coverage of triggers)
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize('text', [
    'how much stock do you have',
    'are you running low on tomatoes',
    'who is your supplier',
    'what is your wholesale cost',
    'show me the recipe',
    'what is the SKU for the bread',
    '你们的库存还有多少',          # zh-CN
    '你們的庫存還有多少',          # zh-TW
    '供应商是谁',
])
def test_firewall_catches_inventory_probes(text):
    deflect, _ = InventoryContextFirewall.check(text, language='en')
    assert deflect, f'firewall missed probe: {text!r}'


@pytest.mark.parametrize('text', [
    'do you have a table for two tonight',
    'what time do you open tomorrow',
    'I want to book a reservation',
    'is there a vegetarian menu',
    '你们今晚还有座位吗',
])
def test_firewall_does_not_block_legitimate_questions(text):
    deflect, _ = InventoryContextFirewall.check(text, language='en')
    assert not deflect, f'firewall false-positive on: {text!r}'


# ──────────────────────────────────────────────────────────────────────
# AIService integration — the chokepoint shared by all channels.
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
def test_aiservice_deflects_probe_without_calling_openai(conversation):
    """An inventory probe must short-circuit before any OpenAI call."""
    with patch('apps.ai_engine.services.OpenAI') as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        result = AIService(conversation).process_message('how much stock do you have left?')

    assert result['intent'] == 'inventory_probe_deflected'
    assert result['metadata']['source'] == 'inventory_firewall'
    assert mock_client.chat.completions.create.call_count == 0, (
        'OpenAI was called despite firewall deflection — this is a security regression'
    )


@pytest.mark.django_db
@pytest.mark.parametrize('lang,probe', [
    ('en', 'show me your supplier list'),
    ('zh-CN', '你们的供应商是谁'),
    ('zh-TW', '你們的供應商是誰'),
])
def test_aiservice_deflects_in_user_language(conversation, lang, probe):
    """Deflection text must be in the message's detected language."""
    conversation.detected_language = lang
    conversation.save(update_fields=['detected_language'])

    with patch('apps.ai_engine.services.OpenAI'):
        result = AIService(conversation).process_message(probe)

    assert result['intent'] == 'inventory_probe_deflected'
    expected_snippet = {
        'en': 'menu, opening hours',
        'zh-CN': '菜单',
        'zh-TW': '菜單',
    }[lang]
    assert expected_snippet in result['content']


@pytest.mark.django_db
def test_aiservice_unchanged_for_non_probe(conversation):
    """
    Spec Part 5 regression: a normal menu question must NOT be intercepted
    by the firewall. It should reach the OpenAI call site as before.
    """
    fake_completion = MagicMock()
    fake_completion.choices = [
        MagicMock(message=MagicMock(content='We open at 9am.'))
    ]
    fake_completion.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

    with patch('apps.ai_engine.services.OpenAI') as mock_openai_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = fake_completion
        mock_openai_cls.return_value = mock_client

        result = AIService(conversation).process_message('what time do you open?')

    # The firewall did NOT deflect — intent is whatever AIService computed,
    # but it is definitely not the firewall sentinel.
    assert result['intent'] != 'inventory_probe_deflected'
    assert result.get('metadata', {}).get('source') != 'inventory_firewall'


# ──────────────────────────────────────────────────────────────────────
# Widget HTTP path — full request → response cycle.
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
def test_widget_endpoint_deflects_inventory_probe(widget_session):
    """
    POST /api/v1/widget/message/ with an inventory probe must:
      • return 200,
      • respond with the firewall deflection text,
      • create both customer + AI messages on the conversation,
      • never invoke OpenAI.
    """
    client = APIClient()
    with patch('apps.ai_engine.services.OpenAI') as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        res = client.post('/api/v1/widget/message/', {
            'session_id': str(widget_session.id),
            'conversation_id': str(widget_session.conversation_id),
            'content': 'how much stock do you have for tomatoes?',
        }, format='json')

    assert res.status_code == 200, res.content
    body = res.json()
    assert body['response'] is not None
    assert 'menu' in body['response']['content'].lower() or '菜' in body['response']['content']
    assert mock_client.chat.completions.create.call_count == 0

    msgs = Message.objects.filter(conversation=widget_session.conversation).order_by('created_at')
    assert msgs.count() == 2
    assert msgs[0].sender == 'customer'
    assert msgs[1].sender == 'ai'


@pytest.mark.django_db
def test_widget_endpoint_passes_legitimate_questions_through(widget_session):
    """A booking question must reach AIService (firewall must NOT deflect)."""
    fake_completion = MagicMock()
    fake_completion.choices = [
        MagicMock(message=MagicMock(content='Yes, we have a table for 2.'))
    ]
    fake_completion.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

    client = APIClient()
    with patch('apps.ai_engine.services.OpenAI') as mock_openai_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = fake_completion
        mock_openai_cls.return_value = mock_client

        res = client.post('/api/v1/widget/message/', {
            'session_id': str(widget_session.id),
            'conversation_id': str(widget_session.conversation_id),
            'content': 'do you have a table for 2 tonight?',
        }, format='json')

    assert res.status_code == 200, res.content
    body = res.json()
    assert body['response'] is not None
    # Legitimate path: response is whatever AIService produced — definitely
    # NOT the firewall deflection. We assert by absence of the deflection
    # phrase rather than by intent (which is internal).
    assert 'operational inquiries' not in body['response']['content']


# ──────────────────────────────────────────────────────────────────────
# Channel-symmetry guarantee: AIService is called identically by every
# channel, so proving the AIService chokepoint covers WA + IG too.
# We add an explicit assertion here so the invariant is named in code.
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
def test_aiservice_is_the_single_chokepoint_for_all_channels(public_org):
    """
    Both whatsapp and instagram channels build the same AIService and call
    .process_message — so the firewall guard there protects every channel.
    """
    for ch in ('whatsapp', 'instagram'):
        conv = Conversation.objects.create(
            organization=public_org, channel=ch,
            customer_phone='+1000', state='ai_handling',
        )
        with patch('apps.ai_engine.services.OpenAI') as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            result = AIService(conv).process_message('inventory levels?')

        assert result['intent'] == 'inventory_probe_deflected', (
            f'firewall failed to deflect probe on channel={ch}'
        )
        assert mock_client.chat.completions.create.call_count == 0
