"""
AI engine Celery tasks — agent memory consolidation.
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def summarize_customer_memory_task(self, organization_id: str, key: str):
    from apps.accounts.models import Organization
    from .agent.memory import summarize_customer

    try:
        summarize_customer(Organization.objects.get(id=organization_id), key)
    except Exception as exc:
        logger.exception("Memory summary failed for %s/%s", organization_id, key)
        raise self.retry(exc=exc)


@shared_task
def summarize_daily_memories_task():
    """Nightly: fold every customer chat from the last day into long-term memory."""
    from apps.messaging.models import Conversation
    from .agent.memory import customer_key

    since = timezone.now() - timedelta(hours=26)
    seen = set()
    convs = Conversation.objects.filter(
        organization__business_type='real_estate', messages__created_at__gte=since,
    ).select_related('organization').distinct()
    for conv in convs:
        key = (str(conv.organization_id), customer_key(conv))
        if key in seen:
            continue
        seen.add(key)
        summarize_customer_memory_task.delay(*key)
    logger.info("Queued %d customer memory summaries", len(seen))
    return len(seen)
