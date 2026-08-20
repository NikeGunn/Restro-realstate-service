"""
Audit + transactional outbox writers.

Both are deliberately tiny and failure-shaped differently:

- `record()` writes an append-only audit row. It NEVER raises: losing an audit
  line must not fail a payment or a redemption. Failures are logged loudly.
- `enqueue()` writes an outbox row INSIDE the caller's transaction and DOES
  propagate integrity errors it can't resolve, because the outbox row is the
  durable promise that a notification will be attempted. A duplicate
  idempotency_key is the one expected case and is swallowed (already promised).
"""
from __future__ import annotations

import hashlib
import logging

from django.db import IntegrityError, transaction

from ..models import CoffeePassAuditEvent, CoffeePassOutboxEvent, OutboxStatus

logger = logging.getLogger(__name__)


def hash_value(value: str) -> str:
    """SHA-256 hex. Used for IPs and tokens so nothing sensitive sits at rest."""
    if not value:
        return ''
    return hashlib.sha256(str(value).encode('utf-8')).hexdigest()


def record(*, organization, action, entity, location=None, actor=None,
           actor_customer=None, correlation_id='', metadata=None, ip=None):
    """
    Append one audit event. Returns the row, or None if the write failed.

    `entity` may be a model instance or None; we store its type name + pk so the
    trail survives the row being deleted.
    """
    try:
        return CoffeePassAuditEvent.objects.create(
            organization=organization,
            location=location,
            action=action,
            entity_type=type(entity).__name__ if entity is not None else '',
            entity_id=getattr(entity, 'pk', None),
            actor=actor if (actor and getattr(actor, 'is_authenticated', False)) else None,
            actor_customer=actor_customer,
            correlation_id=(correlation_id or '')[:64],
            metadata=metadata or {},
            ip_hash=hash_value(ip) if ip else '',
        )
    except Exception:
        # Never let auditing break the business transaction it describes.
        logger.exception('Coffee Pass audit write failed', extra={'action': action})
        return None


def enqueue(*, organization, event_type, aggregate, payload=None,
            idempotency_key=None, available_at=None):
    """
    Write a notification/analytics intent in the CALLER's transaction.

    The unique idempotency_key is what makes retry-safety real: a webhook
    delivered twice produces one outbox row, therefore one WhatsApp message.
    Default key is `{event_type}:{aggregate_pk}` — override when one aggregate
    can legitimately emit the same event type more than once.
    """
    aggregate_id = getattr(aggregate, 'pk', None)
    key = idempotency_key or f'{event_type}:{aggregate_id}'

    try:
        # Nested atomic: a duplicate key marks only THIS savepoint as broken,
        # leaving the caller's outer transaction usable.
        with transaction.atomic():
            return CoffeePassOutboxEvent.objects.create(
                organization=organization,
                event_type=event_type,
                aggregate_type=type(aggregate).__name__ if aggregate is not None else '',
                aggregate_id=aggregate_id,
                payload=payload or {},
                idempotency_key=key[:120],
                status=OutboxStatus.PENDING,
                **({'available_at': available_at} if available_at else {}),
            )
    except IntegrityError:
        # Already promised by an earlier (or concurrent) delivery — that's the
        # idempotency working, not an error.
        logger.info('Outbox event already enqueued', extra={'key': key})
        return None
