"""
Lucky Draw authenticated API (Phase 2) — mounted at /api/v1/lucky_draw/.

Read = owner|manager (IsOrgMember); write/actions = owner (IsOrgOwner).
Every ViewSet uses the shared OrgScopeMixin; cross-org access returns 404.
"""
import logging

from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.mixins import OrgScopeMixin
from apps.common.permissions import IsOrgMember, IsOrgOwner

from .models import (
    LuckyDrawCampaign, LuckyDrawPrize, LuckyDrawEntry, LuckyDrawQRCode,
    CampaignStatus, EntryStatus,
)
from .serializers import (
    LuckyDrawCampaignSerializer, LuckyDrawPrizeSerializer, LuckyDrawEntrySerializer,
    LuckyDrawQRCodeSerializer, PrizeWriteSerializer, QRCodeCreateSerializer,
    RedeemSerializer,
)
from .services import qr_service, draw_engine

logger = logging.getLogger(__name__)


class LuckyDrawCampaignViewSet(OrgScopeMixin, viewsets.ModelViewSet):
    queryset = LuckyDrawCampaign.objects.all().prefetch_related('prizes')
    serializer_class = LuckyDrawCampaignSerializer
    permission_classes = [IsAuthenticated, IsOrgMember]
    filterset_fields = ['status']
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'start_date', 'name']

    # ── status transitions ────────────────────────────────────────────
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsOrgOwner])
    def activate(self, request, pk=None):
        campaign = self.get_object()
        if not campaign.prizes.filter(active=True).exists():
            return Response(
                {'detail': 'Add at least one active prize before activating.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if sum(p.weight for p in campaign.prizes.filter(active=True)) <= 0:
            return Response(
                {'detail': 'Total prize weight must be greater than zero.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        campaign.status = CampaignStatus.ACTIVE
        campaign.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(campaign).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsOrgOwner])
    def pause(self, request, pk=None):
        campaign = self.get_object()
        campaign.status = CampaignStatus.PAUSED
        campaign.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(campaign).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsOrgOwner])
    def end(self, request, pk=None):
        campaign = self.get_object()
        campaign.status = CampaignStatus.ENDED
        campaign.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(campaign).data)

    # ── prizes (nested CRUD) ──────────────────────────────────────────
    @action(detail=True, methods=['get', 'post'])
    def prizes(self, request, pk=None):
        campaign = self.get_object()
        if request.method == 'GET':
            return Response(
                LuckyDrawPrizeSerializer(campaign.prizes.all(), many=True).data
            )
        if not IsOrgOwner().has_object_permission(request, self, campaign):
            return Response(status=status.HTTP_403_FORBIDDEN)
        s = PrizeWriteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        prize = LuckyDrawPrize.objects.create(campaign=campaign, **s.validated_data)
        return Response(LuckyDrawPrizeSerializer(prize).data, status=status.HTTP_201_CREATED)

    # ── QR codes ──────────────────────────────────────────────────────
    @action(detail=True, methods=['get', 'post'], url_path='qr-codes')
    def qr_codes(self, request, pk=None):
        campaign = self.get_object()
        if request.method == 'GET':
            return Response(
                LuckyDrawQRCodeSerializer(campaign.qr_codes.all(), many=True).data
            )
        if not IsOrgOwner().has_object_permission(request, self, campaign):
            return Response(status=status.HTTP_403_FORBIDDEN)
        s = QRCodeCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        qr = self._create_qr_code(campaign, s.validated_data.get('label', ''))
        return Response(LuckyDrawQRCodeSerializer(qr).data, status=status.HTTP_201_CREATED)

    def _create_qr_code(self, campaign, label):
        from django.core.files.base import ContentFile
        from secrets import token_urlsafe
        token = token_urlsafe(24)[:64]
        qr = LuckyDrawQRCode.objects.create(campaign=campaign, label=label, url_token=token)
        try:
            png = qr_service.generate_qr_image(qr_service.get_campaign_entry_url(qr))
            qr.qr_image.save(f'{qr.id}.png', ContentFile(png), save=True)
        except Exception:
            logger.exception("QR image generation failed for qr %s", qr.id)
        return qr

    @action(detail=True, methods=['get'], url_path=r'qr-codes/(?P<qr_id>[^/.]+)/poster')
    def qr_poster(self, request, pk=None, qr_id=None):
        campaign = self.get_object()
        qr = get_object_or_404(campaign.qr_codes, pk=qr_id)
        try:
            png = qr_service.generate_poster(campaign, qr)
        except Exception:
            logger.exception("Poster generation failed for qr %s", qr.id)
            return Response({'detail': 'Poster generation failed.'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        # Cache to default storage on first generation.
        try:
            from django.core.files.base import ContentFile
            if not qr.poster_image:
                qr.poster_image.save(f'{qr.id}-poster.png', ContentFile(png), save=True)
        except Exception:
            logger.warning("Poster caching failed for qr %s", qr.id, exc_info=True)
        return HttpResponse(png, content_type='image/png')

    # ── entries (read-only, filterable) ───────────────────────────────
    @action(detail=True, methods=['get'])
    def entries(self, request, pk=None):
        campaign = self.get_object()
        qs = campaign.entries.select_related('prize', 'crm_customer').all()
        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        page = self.paginate_queryset(qs)
        ser = LuckyDrawEntrySerializer(page if page is not None else qs, many=True)
        return self.get_paginated_response(ser.data) if page is not None else Response(ser.data)

    # ── stats (overview, prize distribution, delivery rate, referral funnel) ──
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        campaign = self.get_object()
        entries = campaign.entries.all()
        total_entries = entries.count()
        drawn = entries.filter(status__in=[EntryStatus.DRAWN, EntryStatus.REDEEMED, EntryStatus.EXPIRED])
        unique_customers = entries.exclude(crm_customer__isnull=True).values('crm_customer').distinct().count()
        total_scans = campaign.qr_codes.aggregate(s=Sum('scan_count'))['s'] or 0

        # Prize distribution.
        prize_dist = list(
            entries.filter(prize__isnull=False)
            .values('prize__id', 'prize__label', 'prize__discount_percent')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        # WhatsApp delivery rate (of drawn entries with consent-eligible delivery).
        drawn_count = drawn.count()
        delivered = drawn.filter(whatsapp_sent_at__isnull=False).count()
        delivery_rate = round(delivered / drawn_count, 4) if drawn_count else 0.0

        # Referral funnel: entries -> entries that shared (referral_count>0) ->
        # referred entries -> redeemed referred entries.
        shared = entries.filter(referral_count__gt=0).count()
        referred = entries.filter(referred_by_entry__isnull=False).count()
        referred_redeemed = entries.filter(
            referred_by_entry__isnull=False, status=EntryStatus.REDEEMED
        ).count()
        redeemed_total = entries.filter(status=EntryStatus.REDEEMED).count()

        return Response({
            'total_entries': total_entries,
            'unique_customers': unique_customers,
            'total_scans': total_scans,
            'drawn_count': drawn_count,
            'redeemed_count': redeemed_total,
            'whatsapp_delivered': delivered,
            'whatsapp_delivery_rate': delivery_rate,
            'prize_distribution': [
                {
                    'prize_id': str(row['prize__id']),
                    'label': row['prize__label'] or f"{row['prize__discount_percent']}%",
                    'discount_percent': float(row['prize__discount_percent']),
                    'count': row['count'],
                }
                for row in prize_dist
            ],
            'referral_funnel': {
                'entries': total_entries,
                'shared': shared,
                'referred_entries': referred,
                'referred_redeemed': referred_redeemed,
                'conversion_rate': round(referred / shared, 4) if shared else 0.0,
            },
        })


class LuckyDrawPrizeViewSet(OrgScopeMixin, viewsets.ModelViewSet):
    queryset = LuckyDrawPrize.objects.select_related('campaign').all()
    serializer_class = LuckyDrawPrizeSerializer
    permission_classes = [IsAuthenticated, IsOrgMember]
    filterset_fields = ['campaign', 'active']

    def get_queryset(self):
        # Prizes are org-scoped via their campaign, not a direct organization FK.
        qs = LuckyDrawPrize.objects.select_related('campaign').all()
        user = self.request.user
        if not user or not user.is_authenticated:
            return qs.none()
        org_ids = self._user_org_ids()
        qs = qs.filter(campaign__organization_id__in=org_ids)
        campaign_id = self.request.query_params.get('campaign')
        if campaign_id:
            qs = qs.filter(campaign_id=campaign_id)
        return qs

    def perform_create(self, serializer):
        campaign = serializer.validated_data['campaign']
        if not IsOrgOwner().has_object_permission(self.request, self, campaign):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only the organization owner can add prizes.")
        serializer.save()


class LuckyDrawEntryViewSet(OrgScopeMixin, viewsets.ReadOnlyModelViewSet):
    queryset = LuckyDrawEntry.objects.select_related('campaign', 'prize', 'crm_customer').all()
    serializer_class = LuckyDrawEntrySerializer
    permission_classes = [IsAuthenticated, IsOrgMember]
    filterset_fields = ['campaign', 'status']
    search_fields = ['customer_name', 'phone', 'coupon_code']
    ordering_fields = ['entered_at', 'drawn_at']

    def get_queryset(self):
        qs = LuckyDrawEntry.objects.select_related('campaign', 'prize', 'crm_customer').all()
        user = self.request.user
        if not user or not user.is_authenticated:
            return qs.none()
        org_ids = self._user_org_ids()
        return qs.filter(campaign__organization_id__in=org_ids)

    @action(detail=False, methods=['post'])
    def redeem(self, request):
        """
        In-store redemption (owner|manager): enter a coupon_code -> mark redeemed.
        Logs a coupon_redeemed CRM interaction; tags buffet_customer if the
        campaign opts in.
        """
        s = RedeemSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        code = s.validated_data['coupon_code'].strip().upper()
        entry = (
            self.get_queryset()
            .filter(coupon_code=code)
            .first()
        )
        if entry is None:
            return Response({'detail': 'Coupon not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Only owner|manager of the entry's org may redeem (already org-scoped),
        # but block redemption in invalid states.
        if entry.status == EntryStatus.REDEEMED:
            return Response({'detail': 'Coupon already redeemed.', 'redeemed_at': entry.redeemed_at},
                            status=status.HTTP_409_CONFLICT)
        if entry.status == EntryStatus.EXPIRED or (
            entry.expires_at and entry.expires_at < timezone.now()
        ):
            return Response({'detail': 'Coupon expired.'}, status=status.HTTP_410_GONE)
        if entry.status != EntryStatus.DRAWN:
            return Response({'detail': 'Coupon is not redeemable.'}, status=status.HTTP_400_BAD_REQUEST)

        entry.status = EntryStatus.REDEEMED
        entry.redeemed_at = timezone.now()
        entry.redeemed_by = request.user
        entry.save(update_fields=['status', 'redeemed_at', 'redeemed_by'])

        self._post_redeem_crm(entry)
        return Response(LuckyDrawEntrySerializer(entry).data)

    def _post_redeem_crm(self, entry):
        customer = entry.crm_customer
        if customer is None:
            return
        try:
            from apps.crm.services import interaction_service
            interaction_service.log_interaction(
                customer, 'coupon_redeemed', source_channel='lucky_draw',
                summary=f"Redeemed {entry.coupon_code} "
                        f"({entry.prize.discount_percent if entry.prize else 0}% off)",
                entity_type='lucky_draw_entry', entity_id=entry.id, user=entry.redeemed_by,
            )
        except Exception:
            logger.warning("Redeem interaction log failed", exc_info=True)
        if entry.campaign.tag_redeemers_as_buffet:
            try:
                from apps.crm.models import CRMTag, CRMCustomerTag
                tag = CRMTag.objects.filter(
                    organization=customer.organization, name='buffet_customer'
                ).first()
                if tag is not None:
                    CRMCustomerTag.objects.get_or_create(customer=customer, tag=tag)
            except Exception:
                logger.warning("buffet_customer tag failed", exc_info=True)
