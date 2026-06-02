"""
Generation orchestrator — the reserve → confirm-or-refund saga (REQUIREMENTS § Phase 5).

Called by the Celery task. The flow, in order:
  1. Reserve credits via the credit adapter (idempotent on job.idempotency_key).
     Blocked by cap/credits → status=blocked_by_cap, NO charge, return.
  2. Build the prompt (pure) → call the provider.
  3. On provider success: store every image immediately (provider URLs expire),
     CONFIRM the reservation with the actual cost, status=completed.
  4. On provider failure: REFUND the reservation, status=failed, NO net charge.
     (A technical failure must never charge.)

Idempotency: if the job already has outputs (a retry after a partial success),
we do not regenerate or double-charge.
"""
import logging
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from . import credits, prompt_builder, provider as provider_mod, image_storage

logger = logging.getLogger(__name__)


def _resolution_tier(resolution: str) -> str:
    """'2048x2048' / '2k' → '2k'. Defaults to '1k'."""
    if resolution in ('1k', '2k', '4k'):
        return resolution
    width = resolution.split('x')[0] if 'x' in resolution else '1024'
    try:
        w = int(width)
    except ValueError:
        return '1k'
    if w >= 4096:
        return '4k'
    if w >= 2048:
        return '2k'
    return '1k'


def _cost_estimate_usd(resolution: str, count: int) -> Decimal:
    tier = _resolution_tier(resolution)
    per = settings.CONTENT_STUDIO['COST_ESTIMATE_USD'].get(tier, Decimal('0.05'))
    return Decimal(per) * count


def run_job(job) -> None:
    """Run a ContentGenerationJob to a terminal state. Safe to retry."""
    from apps.content_studio.models import ContentGenerationJob

    # Idempotency guard: a completed job (e.g. a duplicate task) is a no-op.
    if job.status == ContentGenerationJob.Status.COMPLETED and job.outputs.exists():
        return

    template = getattr(job.use_case, 'prompt_template', None)
    brand_kit = getattr(job.organization, 'brand_kit', None)
    image_count = job.use_case.credit_cost  # campaign_pack → 4 images, 4 credits
    resolution = job.output_resolution or settings.CONTENT_STUDIO['DEFAULT_RESOLUTION']

    job.provider = (template.resolved_provider() if template
                    else settings.CONTENT_STUDIO['DEFAULT_PROVIDER'])
    job.model = (template.resolved_model() if template
                 else settings.CONTENT_STUDIO['IMAGE_MODEL_QUALITY'])
    job.cost_estimated_usd = _cost_estimate_usd(resolution, image_count)

    # 1. Reserve credits (idempotent on idempotency_key).
    reservation = credits.reserve(
        organization=job.organization,
        credits=job.credits_estimated,
        cost_usd_estimate=job.cost_estimated_usd,
        reference_id=job.id,
        idempotency_key=job.idempotency_key,
        user=job.created_by,
        provider=job.provider,
        model=job.model,
    )
    if not reservation.allowed:
        job.status = ContentGenerationJob.Status.BLOCKED_BY_CAP
        job.error_message = reservation.reason or 'Spend cap or credit limit reached.'
        job.save(update_fields=['status', 'error_message', 'provider', 'model',
                                'cost_estimated_usd', 'updated_at'])
        return
    if reservation.event_id:
        job.usage_event_id = reservation.event_id

    # 2. Build the prompt and call the provider.
    job.status = ContentGenerationJob.Status.PROCESSING
    try:
        prompt, negative = prompt_builder.build_prompt(
            job.use_case, job.input_payload, brand_kit,
        )
    except ValueError as e:
        credits.refund(event_id=job.usage_event_id)
        job.status = ContentGenerationJob.Status.FAILED
        job.error_message = str(e)
        job.save(update_fields=['status', 'error_message', 'usage_event_id',
                                'provider', 'model', 'cost_estimated_usd', 'updated_at'])
        return

    job.generated_prompt = prompt
    job.negative_prompt = negative
    job.save(update_fields=['status', 'generated_prompt', 'negative_prompt',
                            'provider', 'model', 'cost_estimated_usd',
                            'usage_event_id', 'updated_at'])

    size = provider_mod.resolve_size(_resolution_tier(resolution), job.aspect)
    try:
        result = provider_mod.generate_image(
            prompt=prompt, negative=negative, size=size,
            model=job.model, provider=job.provider, n=image_count,
        )
    except provider_mod.ProviderError as e:
        # 4. Technical failure → refund, no charge.
        credits.refund(event_id=job.usage_event_id)
        job.status = ContentGenerationJob.Status.FAILED
        job.error_message = str(e)
        job.save(update_fields=['status', 'error_message', 'updated_at'])
        return

    # 3. Store every image immediately (provider URLs expire ~1h).
    stored = 0
    for index, raw in enumerate(result.images):
        asset_id = (result.provider_asset_ids[index]
                    if index < len(result.provider_asset_ids) else '')
        image_storage.download_and_store(raw, job, index, asset_id)
        stored += 1

    cost_actual = (Decimal(result.cost_usd_actual)
                   if result.cost_usd_actual is not None
                   else job.cost_estimated_usd)

    # Confirm the reservation with the actual cost.
    credits.confirm(
        event_id=job.usage_event_id,
        credits_actual=job.credits_estimated,
        cost_usd_actual=cost_actual,
    )

    job.status = ContentGenerationJob.Status.COMPLETED
    job.output_count = stored
    job.credits_used = job.credits_estimated
    job.cost_actual_usd = cost_actual
    job.completed_at = timezone.now()
    job.save(update_fields=['status', 'output_count', 'credits_used',
                            'cost_actual_usd', 'completed_at', 'updated_at'])
