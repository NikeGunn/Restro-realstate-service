"""
When an organization changes business (restaurant <-> real estate), what the AI remembered about its
customers belongs to the old business. Keeping it is how a land agency's agent ended up "remembering"
restaurant bookings. Facts and summaries are cleared; messages, leads and appointments are kept.
"""
import logging

from django.db.models.signals import pre_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(pre_save, sender='accounts.Organization')
def reset_customer_memory_on_business_change(sender, instance, **kwargs):
    if not instance.pk:
        return
    old = sender.objects.filter(pk=instance.pk).values_list('business_type', flat=True).first()
    if old is None or old == instance.business_type:
        return
    from apps.ai_engine.models import AgentMemory

    cleared = AgentMemory.objects.filter(organization_id=instance.pk, subject_type='customer').update(
        facts=[], summary='', summarized_until=None)
    logger.warning("Org %s changed business %s -> %s: cleared %s customer memories",
                   instance.pk, old, instance.business_type, cleared)
