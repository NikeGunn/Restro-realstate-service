"""Phase 5 — testimonial use case requires server-side permission confirmation."""
import pytest

pytestmark = pytest.mark.django_db

JOBS = '/api/v1/content-studio/jobs/'


def test_testimonial_rejected_without_permission(owner_client, org, testimonial_use_case):
    resp = owner_client.post(JOBS, {
        'organization': str(org.id),
        'use_case': str(testimonial_use_case.id),
        'input_payload': {'review_text': 'Great!', 'reviewer_name': 'Sam'},
    }, format='json')
    assert resp.status_code == 400
    assert 'permission_confirmed' in resp.json()


def test_testimonial_rejected_when_permission_false(owner_client, org, testimonial_use_case):
    resp = owner_client.post(JOBS, {
        'organization': str(org.id),
        'use_case': str(testimonial_use_case.id),
        'input_payload': {'review_text': 'Great!', 'reviewer_name': 'Sam',
                          'permission_confirmed': False},
    }, format='json')
    assert resp.status_code == 400


def test_testimonial_accepted_with_permission(owner_client, org, testimonial_use_case):
    resp = owner_client.post(JOBS, {
        'organization': str(org.id),
        'use_case': str(testimonial_use_case.id),
        'input_payload': {'review_text': 'Great!', 'reviewer_name': 'Sam',
                          'permission_confirmed': True},
    }, format='json')
    assert resp.status_code == 201, resp.content
