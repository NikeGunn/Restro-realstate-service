"""Provider failover: a DeepSeek outage / empty balance must not silence the agent."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from django.core.cache import cache
from openai import APIConnectionError, APIStatusError

from apps.ai_engine import llm


def _status_error(code, msg='boom'):
    req = httpx.Request('POST', 'https://api.deepseek.com/chat/completions')
    return APIStatusError(msg, response=httpx.Response(code, request=req), body=None)


def _ok(text='ok'):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text, tool_calls=None))])


@pytest.fixture(autouse=True)
def providers(settings):
    cache.clear()
    settings.OPENAI_API_KEY = 'sk-deepseek'
    settings.OPENAI_BASE_URL = 'https://api.deepseek.com'
    settings.LLM_FALLBACK_API_KEY = 'sk-openai'
    settings.LLM_FALLBACK_BASE_URL = 'https://api.openai.com/v1'
    settings.LLM_FALLBACK_MODEL = 'gpt-4.1-mini'


def _clients(primary_effect, fallback_effect):
    primary, fallback = MagicMock(), MagicMock()
    primary.chat.completions.create.side_effect = primary_effect
    fallback.chat.completions.create.side_effect = fallback_effect
    made = {'primary': primary, 'fallback': fallback}
    return made, patch.object(llm.Provider, 'client', lambda self: made[self.name])


@pytest.mark.parametrize('error', [
    _status_error(402, 'Insufficient Balance'), _status_error(429), _status_error(503),
    _status_error(401), APIConnectionError(request=httpx.Request('POST', 'https://api.deepseek.com')),
])
def test_primary_failure_falls_back_with_fallback_model(error):
    made, p = _clients(error, [_ok('from openai')])
    with p:
        resp = llm.chat_client().chat.completions.create(model='deepseek-chat', messages=[], temperature=0.2)
    assert resp.choices[0].message.content == 'from openai'
    assert made['fallback'].chat.completions.create.call_args.kwargs['model'] == 'gpt-4.1-mini'


def test_no_balance_primary_is_skipped_during_cool_down():
    made, p = _clients([_status_error(402, 'Insufficient Balance')], [_ok('a'), _ok('b')])
    with p:
        client = llm.chat_client()
        client.chat.completions.create(model='deepseek-chat', messages=[])
        llm.chat_client().chat.completions.create(model='deepseek-chat', messages=[])
    assert made['primary'].chat.completions.create.call_count == 1   # second call went straight to fallback


def test_all_providers_down_raises_so_caller_sends_honest_fallback():
    made, p = _clients(_status_error(503), _status_error(429))
    with p, pytest.raises(APIStatusError):
        llm.chat_client().chat.completions.create(model='deepseek-chat', messages=[])


def test_primary_success_never_touches_fallback():
    made, p = _clients([_ok('ds')], [])
    with p:
        assert llm.chat_client().chat.completions.create(model='deepseek-chat', messages=[]).choices[0].message.content == 'ds'
    made['fallback'].chat.completions.create.assert_not_called()


def test_fallback_client_never_inherits_deepseek_base_url():
    chain = llm.providers()
    assert [p.base_url for p in chain] == ['https://api.deepseek.com', 'https://api.openai.com/v1']


def test_no_keys_means_no_client(settings):
    settings.OPENAI_API_KEY = ''
    settings.LLM_FALLBACK_API_KEY = ''
    assert llm.chat_client() is None


@pytest.mark.django_db
def test_agent_turn_survives_total_provider_outage(settings):
    """Both providers down → the customer still gets the honest fallback, nothing crashes."""
    from apps.accounts.models import Location, Organization
    from apps.ai_engine.services import AIService
    from apps.messaging.models import Channel, Conversation, Message, MessageSender

    o = Organization.objects.create(name='Ghar', business_type='real_estate')
    Location.objects.create(organization=o, name='KTM', is_primary=True, is_active=True, country='Nepal')
    conv = Conversation.objects.create(organization=o, channel=Channel.WHATSAPP, customer_phone='9779800000000')
    Message.objects.create(conversation=conv, sender=MessageSender.CUSTOMER, content='malai kotha chaiyo')
    made, p = _clients(_status_error(503), _status_error(429))
    with p:
        out = AIService(conv).process_message('malai kotha chaiyo')
    assert out['content'].strip()
