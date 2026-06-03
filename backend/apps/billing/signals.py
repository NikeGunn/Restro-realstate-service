"""
Billing signals — bootstrap a credit wallet for every new organization.

One-directional and failure-safe: a failure here must NEVER block the org
save. The backfill migration (0003) covers existing orgs; this covers new ones.
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.accounts.models import Organization

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Organization, dispatch_uid='billing_bootstrap_balance')
def bootstrap_billing_for_org(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        from .services.provisioning import ensure_billing_for_org
        ensure_billing_for_org(instance)
    except Exception:  # never block the org save
        logger.exception('billing bootstrap failed for org %s', instance.pk)
