"""
Experience capture — the quality gate, plus service recovery.

Product rule (PRD §1): Coffee Pass is a reward for a good experience, never a
consolation prize for a bad one. So `not_good` must do three things atomically:
capture the issue, notify the owner's recovery workflow, and suppress every
offer and promotional reminder arising from that visit.

Everything CRM-facing goes through the existing CRM services — this app never
writes a second customer identity, tag, or consent path of its own.
"""
from __future__ import annotations

import logging

from django.db import transaction

from apps.crm.models import InteractionType
from apps.crm.services import interaction_service

from ..models import CoffeeExperience, CoffeePassAuditEvent, Sentiment
from . import audit_service

logger = logging.getLogger(__name__)

#: CRM tags this app manages. Created on demand; never hardcoded elsewhere.
TAG_MEMBER = 'coffee_pass_member'
TAG_EXPIRED = 'coffee_pass_expired'
TAG_NEGATIVE = 'coffee_negative_feedback'

#: Outbox event types (the notification worker switches on these).
EVENT_FEEDBACK_NEGATIVE = 'feedback_negative'
EVENT_PASS_ACTIVATED = 'pass_activated'
EVENT_REDEMPTION_CREATED = 'redemption_created'
EVENT_EXPIRY_REMINDER = 'expiry_reminder'


def ensure_tag(organization, name, color='#8B5CF6'):
    """
    Idempotently get-or-create a CRM tag. Returns None on failure — tagging is
    enrichment, and must never break feedback capture or a payment.
    """
    from apps.crm.models import CRMTag
    try:
        tag, _ = CRMTag.objects.get_or_create(
            organization=organization, name=name,
            defaults={'color': color, 'is_system': False},
        )
        return tag
    except Exception:
        logger.warning('Could not ensure CRM tag %s', name, exc_info=True)
        return None


def apply_tag(customer, name, color='#8B5CF6') -> bool:
    """Attach a tag to a customer. Failure-safe; returns whether it stuck."""
    from apps.crm.models import CRMCustomerTag
    tag = ensure_tag(customer.organization, name, color)
    if tag is None:
        return False
    try:
        CRMCustomerTag.objects.get_or_create(customer=customer, tag=tag)
        return True
    except Exception:
        logger.warning('Could not apply CRM tag %s', name, exc_info=True)
        return False


def remove_tag(customer, name) -> bool:
    """Detach a tag (e.g. member -> expired). Failure-safe."""
    from apps.crm.models import CRMCustomerTag, CRMTag
    try:
        tag = CRMTag.objects.filter(organization=customer.organization, name=name).first()
        if tag is None:
            return False
        CRMCustomerTag.objects.filter(customer=customer, tag=tag).delete()
        return True
    except Exception:
        logger.warning('Could not remove CRM tag %s', name, exc_info=True)
        return False


def _log_interaction(customer, summary, entity=None):
    """
    Write a CRM interaction through the existing service.

    Uses MANUAL_NOTE with structured metadata rather than inventing a new
    InteractionType value: adding an enum member would be a migration on a table
    the whole platform writes to, for no analytic gain here.
    """
    try:
        interaction_service.log_interaction(
            customer,
            InteractionType.MANUAL_NOTE,
            source_channel='coffee_pass',
            summary=summary[:500],
            entity_type=type(entity).__name__ if entity is not None else '',
            entity_id=getattr(entity, 'pk', None),
        )
    except Exception:
        logger.warning('CRM interaction write failed', exc_info=True)


@transaction.atomic
def submit(*, plan, customer, sentiment, comment='', routine_context='',
           source='qr', correlation_id='', ip=None):
    """
    Record one verified post-visit response.

    Returns (experience, decision). The decision is computed here — not in the
    view — so every caller (public API, staff entry, a future WhatsApp flow) gets
    the identical gate. A `not_good` answer additionally enqueues the recovery
    notification inside this same transaction.
    """
    from . import offer_decision_service

    if sentiment not in Sentiment.values:
        raise ValueError('invalid_sentiment')

    experience = CoffeeExperience.objects.create(
        organization=plan.organization,
        location=plan.location,
        customer=customer,
        plan=plan,
        sentiment=sentiment,
        comment=(comment or '').strip()[:1000],
        routine_context=routine_context or '',
        source=source,
    )

    audit_service.record(
        organization=plan.organization, location=plan.location,
        action=CoffeePassAuditEvent.Action.EXPERIENCE_SUBMITTED,
        entity=experience, actor_customer=customer,
        correlation_id=correlation_id, ip=ip,
        # Metadata carries the SENTIMENT but never the free-text comment —
        # audit rows are widely readable, the comment is not.
        metadata={'sentiment': sentiment, 'routine_context': routine_context or ''},
    )

    if sentiment == Sentiment.NOT_GOOD:
        _handle_negative(plan, customer, experience)
        # Hard stop: no scoring, no offer, no promotional follow-up.
        decision = offer_decision_service.OfferDecision(
            eligible=False,
            reason_code=offer_decision_service.REASON_QUALITY_GATE_FAILED,
        )
        return experience, decision

    _log_interaction(
        customer, f'Coffee experience: {sentiment} at {plan.location.name}', experience,
    )

    decision = offer_decision_service.decide(
        plan=plan, customer=customer, experience=experience, session_verified=True,
    )
    if decision.eligible:
        experience.offer_shown_at = experience.offer_shown_at or _now()
        experience.save(update_fields=['offer_shown_at'])
    return experience, decision


def _now():
    from django.utils import timezone
    return timezone.now()


def _handle_negative(plan, customer, experience):
    """
    Service recovery. Tag + interaction make it visible in the owner's existing
    CRM workflow; the outbox event drives an acknowledgement message that must
    contain NO Coffee Pass promotion.
    """
    apply_tag(customer, TAG_NEGATIVE, color='#EF4444')
    _log_interaction(
        customer,
        f'Negative coffee experience reported at {plan.location.name} — service recovery needed',
        experience,
    )
    audit_service.enqueue(
        organization=plan.organization,
        event_type=EVENT_FEEDBACK_NEGATIVE,
        aggregate=experience,
        # Privacy-safe payload: ids only. The comment stays in the DB row, read
        # by the owner in the dashboard — never copied into a notification.
        payload={
            'experience_id': str(experience.id),
            'customer_id': str(customer.id),
            'location_id': str(plan.location_id),
        },
    )


def latest_for(customer, location):
    """The customer's most recent experience at a location (drives the gate)."""
    return (
        CoffeeExperience.objects
        .filter(customer=customer, location=location)
        .order_by('-created_at')
        .first()
    )


def has_recent_negative(customer, location, *, days=7) -> bool:
    """
    Used by the notification worker to re-check quality AT SEND TIME.

    A customer who had a bad visit after a reminder was queued must not receive
    that reminder — state at enqueue time is not good enough (A.6).
    """
    from django.utils import timezone
    cutoff = timezone.now() - timezone.timedelta(days=days)
    return CoffeeExperience.objects.filter(
        customer=customer, location=location,
        sentiment=Sentiment.NOT_GOOD, created_at__gte=cutoff,
    ).exists()
