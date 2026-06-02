"""
Provider abstraction for image generation.

Config-driven: the model/provider are passed in (resolved from settings or a
template row), never hardcoded. `generate_image` returns a list of raw PNG bytes
plus a usage dict (actual cost when the provider reports it). Tests mock this
function so no network call is made.

Supported provider key (May 2026): `openai_gpt_image` (GPT Image 2 / 1.5 / mini).
DALL·E is intentionally absent (removed from the API 2026-05-12).
"""
import base64
import logging
from dataclasses import dataclass, field

from django.conf import settings

logger = logging.getLogger(__name__)

# Resolution tier label → pixel size string the provider accepts.
RESOLUTION_TIERS = {
    '1k': '1024x1024',
    '2k': '2048x2048',
    '4k': '4096x4096',
}

# Aspect → size mapping per tier (square uses the tier value directly).
_ASPECT_SIZE = {
    'square': {'1k': '1024x1024', '2k': '2048x2048', '4k': '4096x4096'},
    'portrait': {'1k': '1024x1536', '2k': '1536x2048', '4k': '2048x4096'},
    'landscape': {'1k': '1536x1024', '2k': '2048x1536', '4k': '4096x2048'},
}


@dataclass
class GenerationResult:
    images: list = field(default_factory=list)   # list[bytes]
    cost_usd_actual: object = None                # Decimal | None (None → use estimate)
    provider_asset_ids: list = field(default_factory=list)


def resolve_size(resolution: str, aspect: str = 'square') -> str:
    """Map a resolution tier + aspect to a provider size string."""
    tier = resolution if resolution in RESOLUTION_TIERS else '1k'
    return _ASPECT_SIZE.get(aspect, _ASPECT_SIZE['square']).get(tier, '1024x1024')


class ProviderError(Exception):
    """Raised when the upstream provider fails (caller refunds the reservation)."""


def generate_image(*, prompt: str, negative: str = '', size: str = '1024x1024',
                   model: str, provider: str, n: int = 1) -> GenerationResult:
    """
    Generate `n` images. Returns GenerationResult with raw PNG bytes.

    Raises ProviderError on any upstream failure so the caller refunds credits
    (a technical failure must never charge). When the API key is unset we raise
    ProviderError too — there is no "free" fallback image.
    """
    if provider != 'openai_gpt_image':
        raise ProviderError(f'Unsupported provider: {provider}')

    api_key = getattr(settings, 'OPENAI_API_KEY', '')
    if not api_key:
        raise ProviderError('OPENAI_API_KEY is not configured.')

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        # gpt-image-* accepts negative steering folded into the prompt; the
        # Images API has no separate negative param, so we append it explicitly.
        full_prompt = prompt
        if negative:
            full_prompt = f'{prompt}\n\nAvoid: {negative}'
        resp = client.images.generate(
            model=model, prompt=full_prompt, size=size, n=n,
        )
        images = []
        asset_ids = []
        for item in resp.data:
            b64 = getattr(item, 'b64_json', None)
            if b64:
                images.append(base64.b64decode(b64))
            asset_ids.append(getattr(item, 'id', '') or '')
        if not images:
            raise ProviderError('Provider returned no image data.')
        # Read actual cost from the usage object when present (else None → estimate).
        cost = None
        usage = getattr(resp, 'usage', None)
        if usage is not None:
            cost = getattr(usage, 'total_cost', None) or getattr(usage, 'cost_usd', None)
        return GenerationResult(
            images=images, cost_usd_actual=cost, provider_asset_ids=asset_ids,
        )
    except ProviderError:
        raise
    except Exception as e:
        logger.exception('Image provider call failed')
        raise ProviderError(str(e)) from e
