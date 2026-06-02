"""
Celery tasks for Content Studio.

`process_generation_job_task` runs the saga with bounded retries; a technical
failure refunds the reservation (handled inside run_job). The idempotency_key on
the job makes a retry safe — it never double-generates or double-charges.
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,           # exponential backoff via retry_backoff below
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def process_generation_job_task(self, job_id):
    """Run a single generation job. Retries on transient errors; the saga inside
    run_job refunds on terminal provider failure."""
    from apps.content_studio.models import ContentGenerationJob
    from apps.content_studio.services import generation_service

    try:
        job = ContentGenerationJob.objects.select_related(
            'use_case', 'use_case__prompt_template', 'organization', 'created_by',
        ).get(id=job_id)
    except ContentGenerationJob.DoesNotExist:
        logger.warning('Generation job %s no longer exists', job_id)
        return

    # Already terminal (e.g. a duplicate enqueue) → nothing to do.
    if job.status in ContentGenerationJob.TERMINAL_STATES:
        return

    generation_service.run_job(job)


@shared_task
def cleanup_expired_provider_urls_task():
    """Safety net: any output that somehow still lacks a stored asset gets logged.

    With download-and-store in place there should be none; this exists so an
    operator is alerted if the invariant ever breaks.
    """
    from apps.content_studio.models import ContentGenerationOutput

    orphaned = ContentGenerationOutput.objects.filter(asset='').count()
    if orphaned:
        logger.error(
            'Content Studio: %s output(s) have no stored asset — investigate.',
            orphaned,
        )
    return {'orphaned_outputs': orphaned}
