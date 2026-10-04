"""
Chat-completion client with provider failover.

Primary   = OPENAI_API_KEY + OPENAI_BASE_URL (DeepSeek since 2026-10-04, OpenAI-compatible API).
Fallback  = LLM_FALLBACK_API_KEY + LLM_FALLBACK_BASE_URL + LLM_FALLBACK_MODEL (OpenAI by default).

Any provider error (no credit / 402, rate limit / 429, bad key, 5xx, timeout, connection,
unknown model) moves the SAME request to the next provider with that provider's model. A
provider that failed for a "won't fix itself in seconds" reason (auth, credit, quota) is
skipped for a short cool-down so every customer message doesn't pay its latency first.
If every provider fails the last error is raised — callers already turn that into an
honest fallback message, so the agent never crashes and never goes silent.

`chat_client().chat.completions.create(...)` mirrors the openai SDK, so call sites and the
MagicMock-based tests are unchanged.
"""
import logging
from dataclasses import dataclass
from types import SimpleNamespace
from typing import List, Optional

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

OPENAI_URL = 'https://api.openai.com/v1'
COOL_DOWN_SECONDS = 120
_STICKY_STATUS = {401, 402, 403, 404}   # bad key / no balance / no access / unknown model


@dataclass
class Provider:
    name: str
    api_key: str
    base_url: str
    model: str            # '' = use the caller's model (primary provider)

    def client(self):
        from openai import OpenAI
        # Explicit base_url always: the SDK would otherwise read OPENAI_BASE_URL from the env
        # and send the fallback's OpenAI key to DeepSeek.
        return OpenAI(api_key=self.api_key, base_url=self.base_url or OPENAI_URL,
                      timeout=getattr(settings, 'LLM_TIMEOUT_SECONDS', 45), max_retries=1)


def providers() -> List[Provider]:
    out = []
    if settings.OPENAI_API_KEY:
        out.append(Provider('primary', settings.OPENAI_API_KEY, getattr(settings, 'OPENAI_BASE_URL', ''), ''))
    fb_key = getattr(settings, 'LLM_FALLBACK_API_KEY', '')
    if fb_key and fb_key != settings.OPENAI_API_KEY:
        out.append(Provider('fallback', fb_key, getattr(settings, 'LLM_FALLBACK_BASE_URL', '') or OPENAI_URL,
                            getattr(settings, 'LLM_FALLBACK_MODEL', '') or 'gpt-4.1-mini'))
    return out


def _down_key(p: Provider) -> str:
    return f"llm:down:{p.name}:{p.base_url}"


class _Completions:
    def __init__(self, chain: List[Provider]):
        self.chain = chain
        self._clients = {}

    def create(self, **kwargs):
        from openai import APIError, APIStatusError

        live = [p for p in self.chain if not cache.get(_down_key(p))] or self.chain
        last_error: Optional[Exception] = None
        for i, p in enumerate(live):
            call = dict(kwargs)
            if p.model:
                call['model'] = p.model
                if not p.model.startswith(('gpt-5', 'o3', 'o4')):
                    # Reasoning-only params from the primary's model must not leak to the fallback.
                    call.pop('reasoning_effort', None)
                    if 'max_completion_tokens' in call:
                        call['max_tokens'] = min(call.pop('max_completion_tokens'), 1500)
            try:
                client = self._clients.get(p.name) or self._clients.setdefault(p.name, p.client())
                resp = client.chat.completions.create(**call)
                if i:
                    logger.warning("LLM failover: answered by %s (%s)", p.name, call.get('model'))
                return resp
            except APIError as e:
                last_error = e
                status = getattr(e, 'status_code', None) if isinstance(e, APIStatusError) else None
                quota = 'insufficient_quota' in str(e) or 'Insufficient Balance' in str(e)
                if status in _STICKY_STATUS or quota:
                    cache.set(_down_key(p), str(e)[:200], COOL_DOWN_SECONDS)
                logger.error("LLM provider %s failed (status=%s, model=%s): %s",
                             p.name, status, call.get('model'), str(e)[:300])
        # Every provider failed — the caller sends its honest fallback message.
        raise last_error or RuntimeError('no LLM provider configured')


class FailoverClient:
    def __init__(self, chain: List[Provider]):
        self.chat = SimpleNamespace(completions=_Completions(chain))


def chat_client() -> Optional[FailoverClient]:
    """None when no provider is configured (callers already handle a missing client)."""
    chain = providers()
    return FailoverClient(chain) if chain else None
