"""Phase 5 — API: catalog, brand kit CRUD, job create, outputs, plan gate, cross-org."""
from unittest import mock

import pytest

from apps.content_studio.models import (
    ContentGenerationJob, ContentGenerationOutput, BrandKit,
)

pytestmark = pytest.mark.django_db

USE_CASES = '/api/v1/content-studio/use-cases/'
BRAND_KITS = '/api/v1/content-studio/brand-kits/'
JOBS = '/api/v1/content-studio/jobs/'
OUTPUTS = '/api/v1/content-studio/outputs/'


# ── catalog ────────────────────────────────────────────────────────────
def test_use_case_list_visible_to_member(owner_client, use_case):
    resp = owner_client.get(USE_CASES)
    assert resp.status_code == 200
    data = resp.json()
    rows = data['results'] if isinstance(data, dict) and 'results' in data else data
    keys = {r['use_case_key'] for r in rows}
    assert 'offer_discount_poster' in keys


# ── brand kit ──────────────────────────────────────────────────────────
def test_brand_kit_create_and_get(owner_client, org):
    resp = owner_client.post(BRAND_KITS, {
        'organization': str(org.id),
        'restaurant_name': 'Bargachi',
        'brand_colors': ['#E11D48'],
        'preferred_language': 'zh-TW',
    }, format='json')
    assert resp.status_code == 201, resp.content
    assert BrandKit.objects.filter(organization=org).exists()


def test_brand_kit_rejects_too_many_colors(owner_client, org):
    resp = owner_client.post(BRAND_KITS, {
        'organization': str(org.id),
        'restaurant_name': 'X',
        'brand_colors': ['#1', '#2', '#3', '#4', '#5', '#6'],
    }, format='json')
    assert resp.status_code == 400


def test_brand_kit_rejects_bad_hex(owner_client, org):
    resp = owner_client.post(BRAND_KITS, {
        'organization': str(org.id), 'restaurant_name': 'X',
        'brand_colors': ['red'],
    }, format='json')
    assert resp.status_code == 400


# ── jobs ───────────────────────────────────────────────────────────────
def test_job_create_queues_task(owner_client, org, use_case, django_capture_on_commit_callbacks):
    with mock.patch('apps.content_studio.tasks.process_generation_job_task.delay') as delay:
        with django_capture_on_commit_callbacks(execute=True):
            resp = owner_client.post(JOBS, {
                'organization': str(org.id),
                'use_case': str(use_case.id),
                'input_payload': {'offer_title': 'Deal', 'discount_value': '50%'},
            }, format='json')
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body['status'] == 'queued'
    job = ContentGenerationJob.objects.get(id=body['id'])
    assert job.idempotency_key
    assert job.credits_estimated == 1
    delay.assert_called_once()   # on_commit fired the task


def test_job_create_missing_required_400(owner_client, org, use_case):
    resp = owner_client.post(JOBS, {
        'organization': str(org.id),
        'use_case': str(use_case.id),
        'input_payload': {'offer_title': 'Deal'},  # missing discount_value
    }, format='json')
    assert resp.status_code == 400


def test_manager_cannot_create_job(manager_client, org, use_case):
    resp = manager_client.post(JOBS, {
        'organization': str(org.id),
        'use_case': str(use_case.id),
        'input_payload': {'offer_title': 'Deal', 'discount_value': '50%'},
    }, format='json')
    assert resp.status_code == 403


def test_cancel_job(owner_client, org, use_case, owner):
    import uuid
    job = ContentGenerationJob.objects.create(
        organization=org, created_by=owner, use_case=use_case,
        input_payload={}, idempotency_key=uuid.uuid4().hex,
        status=ContentGenerationJob.Status.QUEUED,
    )
    resp = owner_client.post(f'{JOBS}{job.id}/cancel/')
    assert resp.status_code == 200
    job.refresh_from_db()
    assert job.status == ContentGenerationJob.Status.CANCELLED


def test_regenerate_creates_new_job(owner_client, org, use_case, owner):
    import uuid
    src = ContentGenerationJob.objects.create(
        organization=org, created_by=owner, use_case=use_case,
        input_payload={'offer_title': 'A', 'discount_value': 'B'},
        idempotency_key=uuid.uuid4().hex,
        status=ContentGenerationJob.Status.COMPLETED,
    )
    with mock.patch('apps.content_studio.tasks.process_generation_job_task.delay'):
        resp = owner_client.post(f'{JOBS}{src.id}/regenerate/')
    assert resp.status_code == 201
    new_id = resp.json()['id']
    assert new_id != str(src.id)
    assert ContentGenerationJob.objects.get(id=new_id).idempotency_key != src.idempotency_key


# ── outputs ────────────────────────────────────────────────────────────
def _output(org, use_case, owner):
    import uuid
    job = ContentGenerationJob.objects.create(
        organization=org, created_by=owner, use_case=use_case,
        input_payload={}, idempotency_key=uuid.uuid4().hex,
        status=ContentGenerationJob.Status.COMPLETED,
    )
    return ContentGenerationOutput.objects.create(job=job, width=64, height=64, format='PNG')


def test_output_favorite_toggle(owner_client, org, use_case, owner):
    out = _output(org, use_case, owner)
    resp = owner_client.post(f'{OUTPUTS}{out.id}/favorite/')
    assert resp.status_code == 200
    assert resp.json()['is_favorite'] is True


def test_output_download_increments(owner_client, org, use_case, owner):
    out = _output(org, use_case, owner)
    resp = owner_client.post(f'{OUTPUTS}{out.id}/download/')
    assert resp.status_code == 200
    out.refresh_from_db()
    assert out.download_count == 1


# ── plan gate + cross-org ────────────────────────────────────────────────
def test_basic_plan_blocked(basic_client, basic_org, use_case):
    resp = basic_client.post(JOBS, {
        'organization': str(basic_org.id),
        'use_case': str(use_case.id),
        'input_payload': {'offer_title': 'A', 'discount_value': 'B'},
    }, format='json')
    assert resp.status_code == 403


def test_cross_org_job_isolation(owner_client, org_b, owner_b, use_case):
    import uuid
    foreign = ContentGenerationJob.objects.create(
        organization=org_b, created_by=owner_b, use_case=use_case,
        input_payload={}, idempotency_key=uuid.uuid4().hex,
        status=ContentGenerationJob.Status.COMPLETED,
    )
    resp = owner_client.get(f'{JOBS}{foreign.id}/')
    assert resp.status_code == 404   # cross-org → 404, never leak


def test_outsider_no_access(api_client, outsider, org, use_case):
    api_client.force_authenticate(user=outsider)
    resp = api_client.get(JOBS)
    # outsider has no membership → catalog/list returns 403 (power+member gate)
    assert resp.status_code == 403
