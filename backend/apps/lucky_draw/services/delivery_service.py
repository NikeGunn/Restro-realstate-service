"""
Delivery service (Phase 2) — 🇭🇰 loop 1: WhatsApp coupon + expiry reminder.

The single rule: NEVER send a marketing-channel push without
crm.consent_service.has_marketing_consent(customer, 'whatsapp') returning True.
Failures are logged, not raised — delivery is downstream of the entry, it must
never break the customer-facing POST or a scheduled sweep.
"""
import logging

from django.utils import timezone

from ..models import LuckyDrawEntry

logger = logging.getLogger(__name__)


# Localized coupon-delivery copy (zh-TW HK default).
_COUPON_MSG = {
    'zh-TW': (
        "🎉 恭喜！你贏得 {pct}% 折扣優惠！\n"
        "優惠碼：{code}\n"
        "有效期至：{expiry}\n"
        "到店出示即可使用。"
    ),
    'zh-CN': (
        "🎉 恭喜！你赢得 {pct}% 折扣优惠！\n"
        "优惠码：{code}\n"
        "有效期至：{expiry}\n"
        "到店出示即可使用。"
    ),
    'en': (
        "🎉 Congrats! You won a {pct}% discount!\n"
        "Coupon code: {code}\n"
        "Valid until: {expiry}\n"
        "Show this in-store to redeem."
    ),
}

_REMINDER_MSG = {
    'zh-TW': "⏰ 提提你：你的 {pct}% 折扣優惠碼 {code} 將於 {expiry} 到期，記得使用！",
    'zh-CN': "⏰ 提醒：你的 {pct}% 折扣优惠码 {code} 将于 {expiry} 到期，记得使用！",
    'en': "⏰ Reminder: your {pct}% coupon {code} expires on {expiry}. Don't miss it!",
}


def _lang_for(entry):
    cust = entry.crm_customer
    lang = (cust.preferred_language if cust else '') or entry.campaign.default_language
    return lang if lang in _COUPON_MSG else 'zh-TW'


def _whatsapp_number(entry):
    cust = entry.crm_customer
    if cust and cust.whatsapp_number:
        return cust.whatsapp_number
    if cust and cust.phone:
        return cust.phone
    return entry.phone or None


def _send(org, to, text):
    """Resolve the org's WhatsApp service and send. Returns the message id or None."""
    from apps.channels.whatsapp_service import WhatsAppService
    service = WhatsAppService.get_for_organization(org)
    if service is None:
        logger.info("Lucky-draw delivery skipped: no active WhatsApp config for org %s", org.id)
        return None
    return service.send_message(to=to, text=text)


def deliver_coupon_whatsapp(entry):
    """
    Send the coupon over WhatsApp IFF the campaign opts in, the customer has
    marketing consent for whatsapp, and a number exists. Sets whatsapp_sent_at
    and logs a 'whatsapp_coupon_sent' CRM interaction. Returns True if sent.
    """
    try:
        campaign = entry.campaign
        if not campaign.deliver_coupon_via_whatsapp:
            return False
        if entry.whatsapp_sent_at is not None:
            return False  # idempotent — already delivered
        if not entry.coupon_code or entry.prize is None:
            return False

        customer = entry.crm_customer
        if customer is None:
            return False

        from apps.crm.services import consent_service
        if not consent_service.has_marketing_consent(customer, 'whatsapp'):
            logger.info("Lucky-draw coupon NOT sent (no whatsapp consent) entry=%s", entry.id)
            return False

        to = _whatsapp_number(entry)
        if not to:
            return False

        lang = _lang_for(entry)
        expiry = entry.expires_at.strftime('%Y-%m-%d') if entry.expires_at else '—'
        text = _COUPON_MSG[lang].format(
            pct=_fmt_pct(entry.prize.discount_percent), code=entry.coupon_code, expiry=expiry,
        )

        msg_id = _send(campaign.organization, to, text)
        if not msg_id:
            return False

        entry.whatsapp_sent_at = timezone.now()
        entry.save(update_fields=['whatsapp_sent_at'])

        _log_interaction(customer, 'whatsapp_coupon_sent',
                         f"Coupon {entry.coupon_code} ({entry.prize.discount_percent}% off) sent via WhatsApp")
        return True
    except Exception:
        logger.exception("Lucky-draw WhatsApp delivery failed for entry %s", getattr(entry, 'id', '?'))
        return False


def send_expiry_reminder(entry):
    """
    Send a 'your coupon is about to expire' nudge. Same consent gate. Sets
    reminder_sent_at so it only fires once. Returns True if sent.
    """
    try:
        if entry.reminder_sent_at is not None:
            return False
        if entry.status != 'drawn' or not entry.coupon_code or entry.prize is None:
            return False

        customer = entry.crm_customer
        if customer is None:
            return False

        from apps.crm.services import consent_service
        if not consent_service.has_marketing_consent(customer, 'whatsapp'):
            return False

        to = _whatsapp_number(entry)
        if not to:
            return False

        lang = _lang_for(entry)
        expiry = entry.expires_at.strftime('%Y-%m-%d') if entry.expires_at else '—'
        text = _REMINDER_MSG[lang].format(
            pct=_fmt_pct(entry.prize.discount_percent), code=entry.coupon_code, expiry=expiry,
        )
        msg_id = _send(entry.campaign.organization, to, text)
        if not msg_id:
            return False

        entry.reminder_sent_at = timezone.now()
        entry.save(update_fields=['reminder_sent_at'])
        return True
    except Exception:
        logger.exception("Lucky-draw expiry reminder failed for entry %s", getattr(entry, 'id', '?'))
        return False


def _fmt_pct(value):
    """Render 10.00 -> '10', 12.50 -> '12.5'."""
    s = f"{value:.2f}".rstrip('0').rstrip('.')
    return s or '0'


def _log_interaction(customer, interaction_type, summary):
    try:
        from apps.crm.services import interaction_service
        interaction_service.log_interaction(
            customer, interaction_type, source_channel='whatsapp', summary=summary,
        )
    except Exception:
        logger.warning("Lucky-draw interaction log failed", exc_info=True)
