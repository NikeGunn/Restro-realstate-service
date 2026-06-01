"""
Interaction logging service (Phase 1).

Every touchpoint becomes an append-only CRMInteraction row. Booking/walk-in
interactions also bump visit_count and auto-apply the frequent_customer tag.
"""
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from ..models import CRMInteraction, CRMCustomer, CRMTag, CRMCustomerTag, InteractionType

FREQUENT_THRESHOLD = getattr(settings, 'CRM_FREQUENT_THRESHOLD', 5)

# Interaction types that represent a real visit.
_VISIT_TYPES = {InteractionType.BOOKING, InteractionType.WALK_IN}


@transaction.atomic
def log_interaction(customer, interaction_type, source_channel='', summary='',
                    entity_type=None, entity_id=None, user=None):
    """
    Append a CRMInteraction. Updates last_interaction_at; bumps visit_count for
    visit-type interactions and auto-tags frequent customers.
    """
    interaction = CRMInteraction.objects.create(
        organization=customer.organization,
        customer=customer,
        interaction_type=interaction_type,
        source_channel=source_channel or '',
        summary=(summary or '')[:500],
        related_entity_type=entity_type or '',
        related_entity_id=entity_id,
        created_by=user,
    )

    # Update aggregates with a single locked write to avoid lost updates.
    locked = CRMCustomer.objects.select_for_update().get(pk=customer.pk)
    update_fields = ['last_interaction_at', 'updated_at']
    locked.last_interaction_at = timezone.now()

    if interaction_type in _VISIT_TYPES:
        CRMCustomer.objects.filter(pk=locked.pk).update(visit_count=F('visit_count') + 1)
        locked.refresh_from_db(fields=['visit_count'])

    locked.save(update_fields=update_fields)

    if interaction_type in _VISIT_TYPES and locked.visit_count >= FREQUENT_THRESHOLD:
        _apply_frequent_tag(locked)

    return interaction


def _apply_frequent_tag(customer):
    """Idempotently apply the `frequent_customer` system tag."""
    tag = CRMTag.objects.filter(
        organization=customer.organization, name='frequent_customer'
    ).first()
    if tag is None:
        return
    CRMCustomerTag.objects.get_or_create(customer=customer, tag=tag)
