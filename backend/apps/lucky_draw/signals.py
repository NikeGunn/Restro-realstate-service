"""
Lucky Draw signals (Phase 2).

One receiver, lazy-connected in AppConfig.ready(): when a campaign is created,
ensure the CRM system tags this app relies on (lucky_draw_lead, buffet_customer)
exist for the org. CRM already seeds them on org creation; this is a defensive
backfill so a brand-new org that somehow lacks them still works. The receiver
imports CRM lazily and never blocks the campaign save (wrap + log).
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def connect_signals():
    from .models import LuckyDrawCampaign

    @receiver(post_save, sender=LuckyDrawCampaign, dispatch_uid='lucky_draw_campaign_created')
    def _ensure_system_tags(sender, instance, created, **kwargs):
        if not created:
            return
        try:
            from apps.crm.models import CRMTag
            for name in ('lucky_draw_lead', 'buffet_customer'):
                CRMTag.objects.get_or_create(
                    organization=instance.organization, name=name,
                    defaults={'is_system': True},
                )
        except Exception:
            logger.warning("Lucky-draw system-tag ensure failed", exc_info=True)
