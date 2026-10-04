"""Real-estate Celery tasks."""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='apps.realestate.tasks.appointment_notifications_task')
def appointment_notifications_task():
    """Every 5 min: viewing reminders (~1h before) + missed-viewing follow-ups."""
    from .appointment_notifications import send_due_reminders, send_missed_followups

    reminders = send_due_reminders()
    followups = send_missed_followups()
    if reminders or followups:
        logger.info("Appointment notifications: %s reminder(s), %s follow-up(s)", reminders, followups)
    return {'reminders': reminders, 'followups': followups}
