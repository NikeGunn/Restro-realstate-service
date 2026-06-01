"""
Idempotency helper (Phase 0).

Backed by Redis via Django's cache (`cache.add()` is an atomic SET-if-absent).
Used by public money-like POSTs (lucky-draw entry, generation jobs) so a retry
on a flaky mobile network doesn't create a duplicate.

Safety: if the cache backend is unavailable, we FAIL OPEN (treat the key as
fresh and allow processing) rather than 500 the request. A duplicate under a
cache outage is far less bad than a hard error on the customer-facing path,
and DB-level uniqueness constraints are the real backstop anyway.
"""
import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)

#: Namespace so idempotency keys never collide with other cache entries.
_PREFIX = 'idem:'


def claim(key: str, ttl: int = 86400) -> bool:
    """
    Atomically claim an idempotency key.

    Returns True  -> this is the FIRST time we've seen the key; proceed.
    Returns False -> the key was already claimed; caller should return the
                     prior/cached result instead of re-processing.

    `ttl` is seconds (default 24h). On cache error, returns True (fail-open).
    """
    if not key:
        # No key supplied -> cannot dedupe; treat as fresh.
        return True
    try:
        # cache.add only sets (and returns True) if the key is absent.
        return bool(cache.add(f'{_PREFIX}{key}', '1', ttl))
    except Exception:
        logger.warning('Idempotency cache unavailable; failing open for key=%s', key)
        return True


def release(key: str) -> None:
    """
    Release a claimed key early (e.g. processing failed and a retry SHOULD be
    allowed to re-run). Best-effort; never raises.
    """
    if not key:
        return
    try:
        cache.delete(f'{_PREFIX}{key}')
    except Exception:
        logger.warning('Idempotency cache release failed for key=%s', key)


# Backwards-friendly alias matching the spec's name in REQUIREMENTS.md (§ Phase 0).
def idempotent(key: str, ttl: int = 86400) -> bool:
    """Alias for claim(): returns False if the key was already seen."""
    return claim(key, ttl)
