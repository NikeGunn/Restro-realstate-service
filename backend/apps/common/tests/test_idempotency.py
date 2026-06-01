"""
Idempotency helper tests (Phase 0).
"""
import pytest

from apps.common.idempotency import claim, release, idempotent

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    from django.core.cache import cache
    cache.clear()
    yield
    cache.clear()


def test_first_claim_true_second_false():
    key = 'order-abc-123'
    assert claim(key) is True       # first time -> proceed
    assert claim(key) is False      # replay -> caller returns cached result


def test_idempotent_alias_matches_claim():
    key = 'job-xyz-789'
    assert idempotent(key) is True
    assert idempotent(key) is False


def test_empty_key_always_fresh():
    assert claim('') is True
    assert claim('') is True        # no key -> cannot dedupe, always proceed


def test_distinct_keys_independent():
    assert claim('key-a') is True
    assert claim('key-b') is True   # different key, independent


def test_release_allows_reclaim():
    key = 'retryable-job'
    assert claim(key) is True
    assert claim(key) is False
    release(key)
    assert claim(key) is True       # after release, can be claimed again


def test_fails_open_when_cache_errors(monkeypatch):
    # Simulate a cache backend outage: claim() must fail OPEN (return True),
    # never raise, so the public path doesn't 500.
    from apps.common import idempotency

    def _boom(*a, **k):
        raise RuntimeError('redis down')

    monkeypatch.setattr(idempotency.cache, 'add', _boom)
    assert claim('whatever') is True
