"""
Authenticated Coffee Pass API — owner configuration + staff operations.

Role split (PRD §14):
  owner   -> create/edit/activate/pause plans, void, refund, suspend
  manager -> read passes, resolve codes, create redemptions (the till job)

`OrgScopeMixin` + `IsOrgMember` give exactly that: managers read, owners write.
The two staff ACTIONS that a manager must be able to POST (resolve + redeem) opt
out of the owner-write default explicitly and re-check membership themselves —
they are not org-scoped writes to an owned resource, they are till operations.

Views here parse and authorize. Every decision, calculation, and multi-row
mutation lives in `services/`.
"""
from __future__ import annotations

import logging
import uuid

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Location, OrganizationMembership
from apps.common.mixins import OrgScopeMixin
from apps.common.permissions import IsOrgMember, user_role_in_org
from apps.common.utils import client_ip

from .models import (
    CoffeeExperience, CoffeePass, CoffeePassOTP, CoffeePassPlan,
    CoffeePassPurchase, CoffeePassRedemption, PassStatus, CoffeePassAuditEvent,
)
from .serializers import (
    CoffeeExperienceSerializer, CoffeePassPlanSerializer, MenuItemBriefSerializer,
    CoffeePassPlanWriteSerializer, CoffeePassPurchaseSerializer,
    CoffeePassRedemptionSerializer, CoffeePassSerializer,
    RedemptionCreateSerializer, RefundSerializer, SuspendSerializer,
    VerificationResolveSerializer, VoidSerializer,
)
from .services import (
    analytics_service, audit_service, plan_service, qr_service,
    redemption_service, verification_service,
)

logger = logging.getLogger(__name__)


def _correlation_id(request) -> str:
    """Stable per-request id so audit rows from one action can be joined up."""
    return request.META.get('HTTP_X_REQUEST_ID', '') or uuid.uuid4().hex


def _require_owner(request, organization_id):
    if user_role_in_org(request.user, organization_id) != OrganizationMembership.Role.OWNER:
        raise PermissionDenied('This action requires the organization owner role.')


def _resolve_location(request, organization_id, location_id):
    """Resolve a location id, refusing anything outside the caller's org."""
    if not location_id:
        return None
    location = Location.objects.filter(
        id=location_id, organization_id=organization_id,
    ).first()
    if location is None:
        raise ValidationError({'location': 'Location does not belong to your organization.'})
    return location


# ──────────────────────────────────────────────────────────────────────
# Plans (owner writes, manager reads)
# ──────────────────────────────────────────────────────────────────────
class CoffeePassPlanViewSet(OrgScopeMixin, viewsets.ModelViewSet):
    queryset = CoffeePassPlan.objects.select_related('organization', 'location')
    serializer_class = CoffeePassPlanSerializer
    permission_classes = [IsAuthenticated, IsOrgMember]

    def get_serializer_class(self):
        # Status is service-driven; the write serializer makes it read-only so a
        # PATCH can never bypass the activation guard.
        if self.action in ('update', 'partial_update'):
            return CoffeePassPlanWriteSerializer
        return CoffeePassPlanSerializer

    def get_queryset(self):
        qs = super().get_queryset().prefetch_related('eligible_items')
        plan_status = self.request.query_params.get('status')
        if plan_status:
            qs = qs.filter(status=plan_status)
        return qs

    @action(detail=True, methods=['get'], url_path='activation-preview')
    def activation_preview(self, request, pk=None):
        """Dry-run the activation rules so the owner sees the break-even first."""
        plan = self.get_object()
        return Response(plan_service.check_activation_readiness(plan))

    @action(detail=False, methods=['get'], url_path='channel-health')
    def channel_health(self, request):
        """
        Can this org actually deliver a login code to a customer?

        The public OTP endpoint must answer identically for a known and unknown
        phone, so it can never report a delivery failure. That makes "no
        WhatsApp config" an invisible outage: customers scan, request a code,
        and nothing arrives, while every HTTP response says 200. This endpoint
        is where the owner finds out — before a pilot, not after.
        """
        organization_id = request.query_params.get('organization')
        if not organization_id:
            raise ValidationError({'organization': 'This query parameter is required.'})
        if user_role_in_org(request.user, organization_id) is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        from apps.channels.models import WhatsAppConfig

        config = WhatsAppConfig.objects.filter(
            organization_id=organization_id, is_active=True,
        ).first()

        # Recent delivery outcomes are the empirical answer — a config can exist
        # and still be rejected by Meta (expired token, number not registered).
        recent = list(
            CoffeePassOTP.objects
            .filter(organization_id=organization_id)
            .order_by('-created_at')
            .values('delivery_status', 'delivery_detail', 'created_at')[:20]
        )
        failures = [r for r in recent if r['delivery_status'] in ('no_channel', 'failed')]

        return Response({
            'whatsapp_configured': config is not None,
            'whatsapp_verified': bool(getattr(config, 'is_verified', False)),
            'can_deliver_codes': config is not None,
            'recent_attempts': len(recent),
            'recent_failures': len(failures),
            'last_failure_reason': failures[0]['delivery_detail'] if failures else '',
            # A stable code the dashboard can translate, rather than parsing prose.
            # 'failing' means the MOST RECENT attempt failed — an old failure
            # followed by successes is a fixed problem, not a current one.
            'status': (
                'no_channel' if config is None
                else 'failing' if recent and recent[0]['delivery_status'] in (
                    'no_channel', 'failed')
                else 'ok'
            ),
        })

    @action(detail=False, methods=['get'], url_path='eligible-items')
    def eligible_items(self, request):
        """
        The menu items a Coffee Pass plan may cover, for the plan picker.

        The dashboard must NOT decide this by filtering the full menu itself —
        that is how food ended up on a coffee plan: a client-side filter that
        matched nothing silently fell back to showing everything. The server
        owns the definition; the UI renders what it is given, and an empty list
        means "add coffee items first", never "show all items".
        """
        organization_id = request.query_params.get('organization')
        if not organization_id:
            raise ValidationError({'organization': 'This query parameter is required.'})
        if user_role_in_org(request.user, organization_id) is None:
            # Same 404-not-403 posture as the rest of the app: never confirm
            # that an org id exists to someone outside it.
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        items = plan_service.eligible_item_queryset(organization_id)
        return Response({
            'count': items.count(),
            'eligible_item_types': sorted(plan_service.eligible_item_types()),
            'results': MenuItemBriefSerializer(items, many=True).data,
        })

    @action(detail=True, methods=['get'])
    def qr(self, request, pk=None):
        """
        The plan's QR as a PNG, ready to print and stand on a table.

        Read-only and member-visible (a manager printing a replacement card is
        the till job, not an owner-only privilege). `get_object()` is org-scoped
        by the mixin, so a cross-org id 404s before any image work happens.
        """
        plan = self.get_object()
        return self._render_qr_png(
            plan,
            builder=lambda: qr_service.generate_qr_image(
                qr_service.get_plan_entry_url(plan)
            ),
            suffix='qr',
        )

    @action(detail=True, methods=['get'])
    def poster(self, request, pk=None):
        """A printable counter card (1200x1800 PNG) with the QR embedded."""
        plan = self.get_object()
        language = request.query_params.get('language', 'zh-TW')
        return self._render_qr_png(
            plan,
            builder=lambda: qr_service.generate_poster(plan, language=language),
            suffix='poster',
        )

    def _render_qr_png(self, plan, builder, suffix):
        """
        Shared image response path for `qr` and `poster`.

        Image generation is the one place in this app that depends on optional
        native libraries (qrcode/Pillow/fonts). A failure here must produce a
        clean JSON error the UI can show — never a 500 HTML page that a browser
        would try to download as a .png.
        """
        try:
            png = builder()
        except qr_service.QRGenerationError as exc:
            logger.warning('Coffee Pass %s generation refused for plan %s: %s',
                           suffix, plan.id, exc)
            return Response({'detail': str(exc)},
                            status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        except Exception:
            logger.exception('Coffee Pass %s generation failed for plan %s',
                             suffix, plan.id)
            return Response({'detail': 'Image generation failed.'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        response = HttpResponse(png, content_type='image/png')
        # A slugified name keeps the downloaded file identifiable; the id keeps
        # it unique when two plans share a name. slugify() drops CJK entirely,
        # so fall back to the id rather than emitting "-qr.png".
        stem = slugify(plan.name) or 'coffee-pass'
        response['Content-Disposition'] = (
            f'attachment; filename="{stem}-{suffix}-{plan.id}.png"'
        )
        # Cards get reprinted often and the image is deterministic per plan,
        # but it must never be cached by a shared proxy across tenants.
        response['Cache-Control'] = 'private, max-age=300'
        return response

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        plan = self.get_object()
        _require_owner(request, plan.organization_id)
        try:
            plan_service.activate(
                plan, user=request.user, correlation_id=_correlation_id(request),
            )
        except plan_service.PlanTransitionError as exc:
            return Response(
                {'detail': exc.reason, **exc.detail},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(self.get_serializer(plan).data)

    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        """Stops new sales only — active passes stay valid, by design."""
        plan = self.get_object()
        _require_owner(request, plan.organization_id)
        try:
            plan_service.pause(
                plan, user=request.user, correlation_id=_correlation_id(request),
            )
        except plan_service.PlanTransitionError as exc:
            return Response({'detail': exc.reason}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(plan).data)


# ──────────────────────────────────────────────────────────────────────
# Passes (read + owner support actions)
# ──────────────────────────────────────────────────────────────────────
class CoffeePassViewSet(OrgScopeMixin, viewsets.ReadOnlyModelViewSet):
    queryset = CoffeePass.objects.select_related(
        'customer', 'location', 'plan', 'organization',
    )
    serializer_class = CoffeePassSerializer
    permission_classes = [IsAuthenticated, IsOrgMember]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get('status'):
            qs = qs.filter(status=params['status'])
        if params.get('customer'):
            qs = qs.filter(customer_id=params['customer'])
        search = params.get('search')
        if search:
            # Staff look people up by name or phone at the counter.
            qs = qs.filter(customer__name__icontains=search) | qs.filter(
                customer__phone__icontains=search,
            )
        return qs

    @action(detail=True, methods=['post'])
    def suspend(self, request, pk=None):
        """Owner/support hold. Reversible — distinct from cancellation."""
        coffee_pass = self.get_object()
        _require_owner(request, coffee_pass.organization_id)

        payload = SuspendSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        if coffee_pass.status != PassStatus.ACTIVE:
            return Response(
                {'detail': 'only_active_passes_can_suspend'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        coffee_pass.status = PassStatus.SUSPENDED
        coffee_pass.suspension_reason = payload.validated_data['reason'][:255]
        coffee_pass.save(update_fields=['status', 'suspension_reason', 'updated_at'])

        audit_service.record(
            organization=coffee_pass.organization, location=coffee_pass.location,
            action=CoffeePassAuditEvent.Action.PASS_SUSPENDED,
            entity=coffee_pass, actor=request.user,
            correlation_id=_correlation_id(request), ip=client_ip(request),
            metadata={'reason': payload.validated_data['reason'][:255]},
        )
        return Response(self.get_serializer(coffee_pass).data)

    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        """Lift a suspension. Expiry still applies — this never extends a pass."""
        coffee_pass = self.get_object()
        _require_owner(request, coffee_pass.organization_id)

        if coffee_pass.status != PassStatus.SUSPENDED:
            return Response(
                {'detail': 'only_suspended_passes_can_restore'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        coffee_pass.status = PassStatus.ACTIVE
        coffee_pass.suspension_reason = ''
        coffee_pass.save(update_fields=['status', 'suspension_reason', 'updated_at'])

        audit_service.record(
            organization=coffee_pass.organization, location=coffee_pass.location,
            action=CoffeePassAuditEvent.Action.PASS_RESTORED,
            entity=coffee_pass, actor=request.user,
            correlation_id=_correlation_id(request), ip=client_ip(request),
        )
        return Response(self.get_serializer(coffee_pass).data)

    @action(detail=True, methods=['get'])
    def redemptions(self, request, pk=None):
        coffee_pass = self.get_object()
        rows = coffee_pass.redemptions.select_related('redeemed_by').all()
        return Response(CoffeePassRedemptionSerializer(rows, many=True).data)


# ──────────────────────────────────────────────────────────────────────
# Purchases / experiences (owner reads)
# ──────────────────────────────────────────────────────────────────────
class CoffeePassPurchaseViewSet(OrgScopeMixin, viewsets.ReadOnlyModelViewSet):
    queryset = CoffeePassPurchase.objects.select_related('customer', 'plan', 'location')
    serializer_class = CoffeePassPurchaseSerializer
    permission_classes = [IsAuthenticated, IsOrgMember]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get('status'):
            qs = qs.filter(status=self.request.query_params['status'])
        return qs

    @action(detail=True, methods=['post'])
    def refund(self, request, pk=None):
        """
        Owner-initiated Stripe refund. The WEBHOOK does the pass cancellation —
        this only asks Stripe, so refund handling has one implementation whether
        it starts here or in the Stripe dashboard.
        """
        from decimal import Decimal

        from apps.payments.stripe_client import get_stripe

        purchase = self.get_object()
        _require_owner(request, purchase.organization_id)

        payload = RefundSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        if not purchase.activated or not purchase.stripe_payment_intent_id:
            return Response(
                {'detail': 'no_captured_payment'}, status=status.HTTP_400_BAD_REQUEST,
            )

        max_refundable = purchase.amount_hkd - purchase.refunded_amount_hkd
        amount = payload.validated_data.get('amount_hkd') or max_refundable
        if amount <= Decimal('0') or amount > max_refundable:
            return Response(
                {'detail': 'invalid_refund_amount', 'max_refundable': str(max_refundable)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            stripe = get_stripe()
            refund = stripe.Refund.create(
                payment_intent=purchase.stripe_payment_intent_id,
                amount=int(amount * 100),
                reason='requested_by_customer',
                idempotency_key=f'cp_refund_{purchase.id}_{int(amount * 100)}',
            )
        except Exception:
            logger.exception('Coffee Pass refund failed for %s', purchase.id)
            return Response(
                {'detail': 'stripe_refund_failed'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response({
            'refund_id': refund.id, 'amount_hkd': str(amount), 'status': refund.status,
        })


class CoffeeExperienceViewSet(OrgScopeMixin, viewsets.ReadOnlyModelViewSet):
    """
    Owner-facing feedback list — includes the private comment, which is exactly
    what the service-recovery workflow needs. Staff never reach this endpoint;
    their redemption preview omits it.
    """
    queryset = CoffeeExperience.objects.select_related('customer', 'location')
    serializer_class = CoffeeExperienceSerializer
    permission_classes = [IsAuthenticated, IsOrgMember]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get('sentiment'):
            qs = qs.filter(sentiment=self.request.query_params['sentiment'])
        return qs


class CoffeePassRedemptionViewSet(OrgScopeMixin, viewsets.ReadOnlyModelViewSet):
    queryset = CoffeePassRedemption.objects.select_related(
        'customer', 'location', 'coffee_pass', 'redeemed_by',
    )
    serializer_class = CoffeePassRedemptionSerializer
    permission_classes = [IsAuthenticated, IsOrgMember]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get('status'):
            qs = qs.filter(status=params['status'])
        if params.get('coffee_pass'):
            qs = qs.filter(coffee_pass_id=params['coffee_pass'])
        if params.get('missing_receipt') == 'true':
            qs = qs.filter(pos_receipt_reference='')
        return qs

    @action(detail=True, methods=['post'])
    def void(self, request, pk=None):
        """Owner-only correction. Flips status, never deletes."""
        redemption = self.get_object()
        _require_owner(request, redemption.organization_id)

        payload = VoidSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        try:
            voided = redemption_service.void(
                redemption=redemption, user=request.user,
                reason=payload.validated_data['reason'],
                correlation_id=_correlation_id(request), ip=client_ip(request),
            )
        except redemption_service.RedemptionError as exc:
            code = (
                status.HTTP_409_CONFLICT if exc.reason == 'already_voided'
                else status.HTTP_400_BAD_REQUEST
            )
            return Response({'detail': exc.reason, **exc.detail}, status=code)

        return Response(self.get_serializer(voided).data)


# ──────────────────────────────────────────────────────────────────────
# Till operations (manager-allowed POSTs)
# ──────────────────────────────────────────────────────────────────────
class StaffOperationView(APIView):
    """
    Base for till endpoints.

    These are POSTs a MANAGER must be able to make, so they cannot use the
    owner-write default. Instead each resolves the caller's organization from
    their membership explicitly — narrower than IsOrgMember's write rule, and
    intentionally so.
    """
    permission_classes = [IsAuthenticated]

    def _memberships(self, request):
        return OrganizationMembership.objects.filter(user=request.user)

    def _organization_for(self, request):
        """
        The org this staff member is acting for.

        `?organization=` is required when the user belongs to several orgs, so a
        till action is never silently attributed to the wrong tenant.
        """
        requested = request.data.get('organization') or request.query_params.get('organization')
        memberships = self._memberships(request)
        if requested:
            membership = memberships.filter(organization_id=requested).first()
            if membership is None:
                raise PermissionDenied('You are not a member of that organization.')
            return membership.organization

        found = list(memberships.select_related('organization')[:2])
        if not found:
            raise PermissionDenied('You do not belong to any organization.')
        if len(found) > 1:
            raise ValidationError({'organization': 'Specify which organization you are acting for.'})
        return found[0].organization


class VerificationResolveView(StaffOperationView):
    """
    Validate a scanned/typed code and return a redemption preview.

    Does NOT consume the code — see verification_service.resolve for why burning
    on preview would strand customers.
    """

    def post(self, request):
        payload = VerificationResolveSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        organization = self._organization_for(request)
        location = _resolve_location(
            request, organization.id, payload.validated_data.get('location'),
        )

        result = verification_service.resolve(
            payload.validated_data['code'], organization=organization, location=location,
        )
        if not result.get('valid'):
            # 200 with a reason code, not 4xx: an expired code is a normal,
            # expected outcome at a busy till, and the UI shows specific copy.
            return Response(result, status=status.HTTP_200_OK)
        return Response(result)


class RedemptionCreateView(StaffOperationView):
    """Consume the code and record the redemption. The concurrency-critical POST."""

    def post(self, request):
        payload = RedemptionCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        organization = self._organization_for(request)
        location = _resolve_location(request, organization.id, data.get('location'))

        try:
            redemption = redemption_service.redeem(
                verification_token_id=data['verification_token_id'],
                eligible_subtotal=data['eligible_subtotal_hkd'],
                user=request.user,
                location=location,
                pos_receipt_reference=data.get('pos_receipt_reference', ''),
                correlation_id=_correlation_id(request),
                ip=client_ip(request),
            )
        except redemption_service.RedemptionError as exc:
            return Response(
                {'detail': exc.reason, **exc.detail},
                status=_redemption_status(exc.reason),
            )

        return Response(
            CoffeePassRedemptionSerializer(redemption).data,
            status=status.HTTP_201_CREATED,
        )


def _redemption_status(reason: str) -> int:
    """Map a refusal reason to the most informative HTTP status."""
    return {
        'code_already_used_or_expired': status.HTTP_409_CONFLICT,
        'expired': status.HTTP_410_GONE,
        'wrong_location': status.HTTP_403_FORBIDDEN,
        'wrong_organization': status.HTTP_403_FORBIDDEN,
        'suspended': status.HTTP_403_FORBIDDEN,
        'cancelled': status.HTTP_403_FORBIDDEN,
    }.get(reason, status.HTTP_400_BAD_REQUEST)


# ──────────────────────────────────────────────────────────────────────
# Analytics (owner)
# ──────────────────────────────────────────────────────────────────────
class AnalyticsSummaryView(APIView):
    """Tenant-scoped metrics computed from persisted rows."""
    permission_classes = [IsAuthenticated, IsOrgMember]

    def get(self, request):
        from django.utils.dateparse import parse_datetime

        organization, location = _scope_from_query(request)
        date_from = parse_datetime(request.query_params.get('date_from', '') or '')
        date_to = parse_datetime(request.query_params.get('date_to', '') or '')

        return Response(analytics_service.summary(
            organization=organization, location=location,
            date_from=date_from, date_to=date_to,
        ))


class AnalyticsAnomaliesView(APIView):
    """Explainable owner alerts (never an opaque fraud score)."""
    permission_classes = [IsAuthenticated, IsOrgMember]

    def get(self, request):
        organization, location = _scope_from_query(request)
        return Response({
            'anomalies': analytics_service.anomalies(
                organization=organization, location=location,
            ),
        })


def _scope_from_query(request):
    """Resolve (organization, location) from query params against membership."""
    memberships = OrganizationMembership.objects.filter(
        user=request.user,
    ).select_related('organization')

    requested = request.query_params.get('organization')
    if requested:
        membership = memberships.filter(organization_id=requested).first()
        if membership is None:
            raise PermissionDenied('You are not a member of that organization.')
        organization = membership.organization
    else:
        first = memberships.first()
        if first is None:
            raise PermissionDenied('You do not belong to any organization.')
        organization = first.organization

    location = None
    location_id = request.query_params.get('location')
    if location_id:
        location = get_object_or_404(
            Location, id=location_id, organization_id=organization.id,
        )
    return organization, location


__all__ = [
    'CoffeePassPlanViewSet', 'CoffeePassViewSet', 'CoffeePassPurchaseViewSet',
    'CoffeeExperienceViewSet', 'CoffeePassRedemptionViewSet',
    'VerificationResolveView', 'RedemptionCreateView',
    'AnalyticsSummaryView', 'AnalyticsAnomaliesView',
]
