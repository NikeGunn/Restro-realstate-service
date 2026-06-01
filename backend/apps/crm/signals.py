"""
CRM signal integrations (Phase 1).

All cross-app receivers are lazy-connected from apps.py::ready(). They never
import restaurant/messaging at module level and never block the originating
save (every receiver wraps its work in try/except + log).
"""
import logging

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

# System tags seeded per organization.
_SYSTEM_TAG_COLORS = {
    'lucky_draw_lead': '#F59E0B',
    'wifi_lead': '#10B981',
    'buffet_customer': '#8B5CF6',
    'frequent_customer': '#3B82F6',
    'vip': '#EF4444',
    'inactive_customer': '#6B7280',
    'birthday_this_month': '#EC4899',
}


def seed_system_tags(organization):
    """Idempotently create the system tags (+ a default segment) for an org."""
    from .models import CRMTag, CRMSegment
    for name, color in _SYSTEM_TAG_COLORS.items():
        CRMTag.objects.get_or_create(
            organization=organization, name=name,
            defaults={'color': color, 'is_system': True},
        )
    CRMSegment.objects.get_or_create(
        organization=organization,
        name='All consenting customers',
        defaults={
            'description': 'Customers who have given marketing consent.',
            'filter_rules': {
                'logic': 'AND',
                'rules': [{'field': 'marketing_consent_status', 'op': 'eq', 'value': 'given'}],
            },
        },
    )


def connect_signals():
    """Wire up all CRM receivers. Called once from AppConfig.ready()."""
    from apps.accounts.models import Organization

    @receiver(post_save, sender=Organization, dispatch_uid='crm_seed_system_tags')
    def _on_org_created(sender, instance, created, **kwargs):
        if not created:
            return
        try:
            seed_system_tags(instance)
        except Exception:
            logger.exception('CRM: seeding system tags failed for org %s', instance.pk)

    _connect_booking_signal()
    _connect_conversation_signal()


def _connect_booking_signal():
    if not getattr(settings, 'CRM_AUTO_SYNC_BOOKINGS', True):
        return
    try:
        from apps.restaurant.models import Booking
    except Exception:
        logger.warning('CRM: restaurant.Booking unavailable; booking sync disabled')
        return

    @receiver(post_save, sender=Booking, dispatch_uid='crm_sync_booking')
    def _on_booking_save(sender, instance, created, **kwargs):
        try:
            _sync_booking(instance)
        except Exception:
            logger.exception('CRM: booking sync failed for booking %s', instance.pk)


def _connect_conversation_signal():
    if not getattr(settings, 'CRM_AUTO_SYNC_CONVERSATIONS', True):
        return
    try:
        from apps.messaging.models import Conversation
    except Exception:
        logger.warning('CRM: messaging.Conversation unavailable; conversation sync disabled')
        return

    @receiver(post_save, sender=Conversation, dispatch_uid='crm_sync_conversation')
    def _on_conversation_save(sender, instance, created, **kwargs):
        if not created:
            return
        try:
            _sync_conversation(instance)
        except Exception:
            logger.exception('CRM: conversation sync failed for conversation %s', instance.pk)


def _sync_booking(booking):
    """Upsert a customer + log a booking interaction when a booking lands."""
    from apps.restaurant.models import Booking
    from .services import customer_service, interaction_service
    from .models import InteractionType

    status = booking.status
    if status not in (Booking.Status.CONFIRMED, Booking.Status.COMPLETED):
        return
    if not booking.customer_phone and not booking.customer_email:
        return

    customer, _ = customer_service.get_or_create_customer(
        booking.organization,
        phone=booking.customer_phone or None,
        email=booking.customer_email or None,
        defaults={'name': booking.customer_name, 'source': 'booking'},
    )
    interaction_service.log_interaction(
        customer, InteractionType.BOOKING, source_channel='booking',
        summary=f'Booking on {booking.booking_date}',
        entity_type='restaurant.Booking', entity_id=booking.id,
    )
    if status == Booking.Status.COMPLETED:
        from .models import CRMCustomer
        CRMCustomer.objects.filter(pk=customer.pk).update(
            last_visit_date=booking.booking_date
        )


def _sync_conversation(conversation):
    """Upsert a customer + log a message interaction for whatsapp/instagram convos."""
    from apps.messaging.models import Channel
    from .services import customer_service, interaction_service
    from .models import InteractionType

    channel = conversation.channel
    if channel not in (Channel.WHATSAPP, Channel.INSTAGRAM):
        return
    if not conversation.customer_phone and not conversation.customer_email:
        return

    customer, _ = customer_service.get_or_create_customer(
        conversation.organization,
        phone=conversation.customer_phone or None,
        email=conversation.customer_email or None,
        defaults={
            'name': conversation.customer_name or 'Customer',
            'source': channel,
            'preferred_language': conversation.detected_language or '',
        },
    )
    itype = (
        InteractionType.WHATSAPP_MESSAGE if channel == Channel.WHATSAPP
        else InteractionType.INSTAGRAM_MESSAGE
    )
    interaction_service.log_interaction(
        customer, itype, source_channel=channel,
        summary='New conversation', entity_type='messaging.Conversation',
        entity_id=conversation.id,
    )
