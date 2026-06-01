"""
Lucky Draw PUBLIC API (Phase 2) — mounted at /public/lucky-draw/, no auth.

Two endpoints:
  GET  /public/lucky-draw/{url_token}/        -> campaign config (+ scan_count++)
  POST /public/lucky-draw/{url_token}/enter/  -> the scan→win pipeline

Throttled with the Phase 0 public scopes. The POST is idempotent (Phase 0
helper) so a flaky-mobile retry returns the prior result instead of creating a
second entry — and WhatsApp delivery is queued on_commit so the POST stays fast.
"""
import logging

from django.core.cache import cache
from django.db import transaction
from django.db.models import F
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common import idempotency
from apps.common.throttling import PublicBurstThrottle, PublicFormThrottle
from apps.common.utils import client_ip

from .models import LuckyDrawCampaign, LuckyDrawQRCode, CampaignStatus
from .serializers import PublicEntrySerializer
from .services import entry_service, qr_service

logger = logging.getLogger(__name__)

#: Cache prefix for storing the result of an idempotent enter, so a replay can
#: return the exact same payload (not just "duplicate").
_RESULT_PREFIX = 'ld:result:'
_RESULT_TTL = 86400  # 24h


# Share-message copy (zh-TW HK default). {url} is the referral link.
_SHARE_TEXT = {
    'zh-TW': "我喺呢度抽中咗 {pct}% 折扣！你都嚟試下手氣啦 👉 {url}",
    'zh-CN': "我在这里抽中了 {pct}% 折扣！你也来试试手气吧 👉 {url}",
    'en': "I just won {pct}% off! Try your luck too 👉 {url}",
}


def _get_active_campaign(url_token):
    qr = (
        LuckyDrawQRCode.objects.select_related('campaign__organization')
        .filter(url_token=url_token)
        .first()
    )
    if qr is None:
        return None, None
    return qr, qr.campaign


class PublicCampaignConfigView(APIView):
    """GET campaign config for the public entry page. Increments scan_count."""
    permission_classes = [AllowAny]
    throttle_classes = [PublicBurstThrottle]
    authentication_classes = []

    def get(self, request, url_token):
        qr, campaign = _get_active_campaign(url_token)
        if qr is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Atomic scan counter.
        LuckyDrawQRCode.objects.filter(pk=qr.pk).update(scan_count=F('scan_count') + 1)

        max_discount = max(
            [p.discount_percent for p in campaign.prizes.filter(active=True)], default=0
        )
        return Response({
            'campaign_id': str(campaign.id),
            'name': campaign.name,
            'description': campaign.description,
            'status': campaign.status,
            'is_open': campaign.status == CampaignStatus.ACTIVE,
            'requires_name': campaign.requires_name,
            'requires_phone': campaign.requires_phone,
            'requires_email': campaign.requires_email,
            'consent_text': campaign.consent_text,
            'privacy_notice_text': campaign.privacy_notice_text,
            'default_language': campaign.default_language,
            'referral_enabled': campaign.referral_enabled,
            'max_discount': float(max_discount),
            'organization_name': campaign.organization.name,
        })


class PublicEntryView(APIView):
    """POST a lucky-draw entry. Idempotent, throttled, runs the full pipeline."""
    permission_classes = [AllowAny]
    throttle_classes = [PublicFormThrottle]
    authentication_classes = []

    def post(self, request, url_token):
        qr, campaign = _get_active_campaign(url_token)
        if qr is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        s = PublicEntrySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        # Required-field validation per campaign config.
        missing = []
        if campaign.requires_name and not data['name'].strip():
            missing.append('name')
        if campaign.requires_phone and not data['phone'].strip():
            missing.append('phone')
        if campaign.requires_email and not data['email'].strip():
            missing.append('email')
        if missing:
            return Response(
                {'detail': 'missing_required_fields', 'fields': missing},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        # Idempotency: replay returns the stored prior result.
        idem_key = (data.get('idempotency_key') or '').strip()
        scoped_key = f'{campaign.id}:{idem_key}' if idem_key else ''
        if scoped_key:
            cached = cache.get(f'{_RESULT_PREFIX}{scoped_key}')
            if cached is not None:
                return Response(cached, status=status.HTTP_200_OK)
            # claim() returns False if already in-flight/seen.
            if not idempotency.claim(f'enter:{scoped_key}', ttl=_RESULT_TTL):
                cached = cache.get(f'{_RESULT_PREFIX}{scoped_key}')
                if cached is not None:
                    return Response(cached, status=status.HTTP_200_OK)
                # Claimed but no result yet (race) — treat as duplicate, no second draw.
                return Response({'detail': 'duplicate_submission'}, status=status.HTTP_409_CONFLICT)

        ip = client_ip(request)
        ua = request.META.get('HTTP_USER_AGENT', '')

        try:
            entry = entry_service.create_entry(
                campaign,
                name=data['name'], phone=data['phone'], email=data['email'],
                table_number=data['table_number'], consent_given=data['consent_given'],
                referral_token=(data.get('referral_token') or '').strip() or None,
                ip_address=ip, user_agent=ua,
            )
        except entry_service.EntryError as exc:
            if scoped_key:
                idempotency.release(f'enter:{scoped_key}')
            return Response({'detail': exc.reason}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        except Exception:
            logger.exception("Lucky-draw public entry failed for campaign %s", campaign.id)
            if scoped_key:
                idempotency.release(f'enter:{scoped_key}')
            return Response({'detail': 'entry_failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Queue WhatsApp delivery AFTER commit so the POST returns fast.
        if entry.prize is not None and campaign.deliver_coupon_via_whatsapp:
            entry_id = entry.id
            transaction.on_commit(lambda: _queue_delivery(entry_id))

        result = self._build_result(campaign, entry)
        if scoped_key:
            cache.set(f'{_RESULT_PREFIX}{scoped_key}', result, _RESULT_TTL)
        return Response(result, status=status.HTTP_201_CREATED)

    def _build_result(self, campaign, entry):
        lang = campaign.default_language if campaign.default_language in _SHARE_TEXT else 'zh-TW'
        referral_url = ''
        share_text = ''
        if campaign.referral_enabled and entry.referral_token:
            referral_url = (
                f"{qr_service.get_public_base_url().rstrip('/')}"
                f"/public/lucky-draw/{self._campaign_token(campaign)}/?ref={entry.referral_token}"
            )
            pct = float(entry.prize.discount_percent) if entry.prize else 0
            share_text = _SHARE_TEXT[lang].format(pct=_fmt(pct), url=referral_url)
        return {
            'won': entry.prize is not None,
            'discount_percent': float(entry.prize.discount_percent) if entry.prize else 0,
            'coupon_code': entry.coupon_code or '',
            'expires_at': entry.expires_at.isoformat() if entry.expires_at else None,
            'status': entry.status,
            'referral_url': referral_url,
            'referral_token': entry.referral_token if campaign.referral_enabled else '',
            'share_text': share_text,
        }

    def _campaign_token(self, campaign):
        qr = campaign.qr_codes.first()
        return qr.url_token if qr else ''


def _queue_delivery(entry_id):
    """Hand off to Celery; fall back to inline send if the task can't be queued."""
    try:
        from .tasks import send_coupon_whatsapp_task
        send_coupon_whatsapp_task.delay(str(entry_id))
    except Exception:
        logger.warning("Could not queue WhatsApp delivery for entry %s; sending inline", entry_id)
        try:
            from .models import LuckyDrawEntry
            from .services import delivery_service
            entry = LuckyDrawEntry.objects.filter(pk=entry_id).first()
            if entry:
                delivery_service.deliver_coupon_whatsapp(entry)
        except Exception:
            logger.exception("Inline WhatsApp delivery fallback failed for entry %s", entry_id)


def _fmt(value):
    s = f"{value:.2f}".rstrip('0').rstrip('.')
    return s or '0'
