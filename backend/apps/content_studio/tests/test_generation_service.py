"""Phase 5 — generation saga: reserve → confirm/refund, idempotency, store-before-expiry."""
import io
from decimal import Decimal
from unittest import mock

import pytest

from apps.content_studio.models import ContentGenerationJob, ContentGenerationOutput
from apps.content_studio.services import generation_service, provider as provider_mod

pytestmark = pytest.mark.django_db


def _png_bytes():
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (64, 64), (200, 50, 50)).save(buf, format='PNG')
    return buf.getvalue()


def _make_job(org, use_case, owner, **kw):
    import uuid
    return ContentGenerationJob.objects.create(
        organization=org, created_by=owner, use_case=use_case,
        input_payload={'offer_title': 'Deal', 'discount_value': '50%'},
        idempotency_key=kw.pop('key', uuid.uuid4().hex),
        credits_estimated=use_case.credit_cost,
        status=ContentGenerationJob.Status.QUEUED,
        **kw,
    )


def test_success_stores_outputs_and_completes(org, use_case, owner):
    job = _make_job(org, use_case, owner)
    fake = provider_mod.GenerationResult(images=[_png_bytes()], cost_usd_actual=Decimal('0.05'))
    with mock.patch.object(provider_mod, 'generate_image', return_value=fake) as gen:
        generation_service.run_job(job)
    job.refresh_from_db()
    assert job.status == ContentGenerationJob.Status.COMPLETED
    assert job.output_count == 1
    assert job.credits_used == 1
    assert job.cost_actual_usd == Decimal('0.05')
    assert ContentGenerationOutput.objects.filter(job=job).count() == 1
    gen.assert_called_once()
    # The stored output has a real asset (not a provider URL).
    out = job.outputs.first()
    assert out.asset and out.width == 64 and out.height == 64


def test_provider_failure_refunds_and_fails(org, use_case, owner):
    job = _make_job(org, use_case, owner)
    with mock.patch.object(provider_mod, 'generate_image',
                           side_effect=provider_mod.ProviderError('boom')), \
         mock.patch('apps.content_studio.services.credits.refund') as refund:
        generation_service.run_job(job)
    job.refresh_from_db()
    assert job.status == ContentGenerationJob.Status.FAILED
    assert 'boom' in job.error_message
    assert job.output_count == 0
    refund.assert_called_once()   # technical failure must refund, never charge


def test_store_called_before_any_expiry(org, use_case, owner):
    """download_and_store is invoked immediately after generation (provider URLs expire)."""
    job = _make_job(org, use_case, owner)
    fake = provider_mod.GenerationResult(images=[_png_bytes()], cost_usd_actual=None)
    with mock.patch.object(provider_mod, 'generate_image', return_value=fake), \
         mock.patch('apps.content_studio.services.image_storage.download_and_store',
                    wraps=__import__('apps.content_studio.services.image_storage',
                                     fromlist=['download_and_store']).download_and_store) as store:
        generation_service.run_job(job)
    store.assert_called_once()


def test_idempotency_no_double_generate_on_rerun(org, use_case, owner):
    job = _make_job(org, use_case, owner)
    fake = provider_mod.GenerationResult(images=[_png_bytes()], cost_usd_actual=Decimal('0.05'))
    with mock.patch.object(provider_mod, 'generate_image', return_value=fake) as gen:
        generation_service.run_job(job)
        job.refresh_from_db()
        # A duplicate task firing for a completed job must NOT regenerate.
        generation_service.run_job(job)
    assert gen.call_count == 1
    assert ContentGenerationOutput.objects.filter(job=job).count() == 1


def test_blocked_by_cap_no_charge(org, use_case, owner):
    job = _make_job(org, use_case, owner)
    from apps.content_studio.services import credits
    blocked = credits.Reservation(event_id=None, allowed=False, reason='cap reached')
    with mock.patch('apps.content_studio.services.credits.reserve', return_value=blocked), \
         mock.patch.object(provider_mod, 'generate_image') as gen:
        generation_service.run_job(job)
    job.refresh_from_db()
    assert job.status == ContentGenerationJob.Status.BLOCKED_BY_CAP
    gen.assert_not_called()   # never call the provider when blocked


def test_missing_required_field_refunds_and_fails(org, use_case, owner):
    job = _make_job(org, use_case, owner)
    job.input_payload = {'offer_title': 'only title'}  # missing discount_value
    job.save(update_fields=['input_payload'])
    with mock.patch('apps.content_studio.services.credits.refund') as refund, \
         mock.patch.object(provider_mod, 'generate_image') as gen:
        generation_service.run_job(job)
    job.refresh_from_db()
    assert job.status == ContentGenerationJob.Status.FAILED
    gen.assert_not_called()
    refund.assert_called_once()


def test_campaign_pack_generates_multiple(org, owner):
    from apps.content_studio.models import ContentUseCase, ContentPromptTemplate
    uc = ContentUseCase.objects.create(
        use_case_key='campaign_pack_test', display_name='Pack', credit_cost=4,
        required_fields=[{'key': 'campaign_theme', 'label': 'Theme', 'type': 'text'}],
        supported_formats=['square'],
    )
    ContentPromptTemplate.objects.create(use_case=uc, prompt_template='Theme {{campaign_theme}}.')
    import uuid
    job = ContentGenerationJob.objects.create(
        organization=org, created_by=owner, use_case=uc,
        input_payload={'campaign_theme': 'Summer'}, idempotency_key=uuid.uuid4().hex,
        credits_estimated=4, status=ContentGenerationJob.Status.QUEUED,
    )
    fake = provider_mod.GenerationResult(
        images=[_png_bytes(), _png_bytes(), _png_bytes(), _png_bytes()],
        cost_usd_actual=Decimal('0.20'),
    )
    with mock.patch.object(provider_mod, 'generate_image', return_value=fake):
        generation_service.run_job(job)
    job.refresh_from_db()
    assert job.output_count == 4
