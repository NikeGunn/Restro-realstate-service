"""
Billing API views — mounted at /api/v1/billing/.

All org-scoped via OrgScopeMixin (members read; owner-only writes where noted).
This is a reporting + limit-management surface; the credit saga is server-side
only (never mutated through the API).
"""
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied, NotFound

from apps.common.mixins import OrgScopeMixin
from apps.common.permissions import IsOrgMember, user_role_in_org
from apps.accounts.models import OrganizationMembership

from .models import (
    UsageCreditBalance, UsageEvent, UsageLimit, MonthlyUsageSummary,
)
from .serializers import (
    UsageCreditBalanceSerializer, UsageEventSerializer,
    UsageLimitSerializer, MonthlyUsageSummarySerializer,
)
from .services.provisioning import ensure_billing_for_org


def _resolve_org(request):
    """Resolve the org for a single-org view from ?organization= (validated against
    membership) or the user's sole org. 404 if it can't be determined / not a member.
    """
    org_ids = list(
        OrganizationMembership.objects.filter(user=request.user)
        .values_list('organization_id', flat=True)
    )
    if not org_ids:
        raise PermissionDenied('You are not a member of any organization.')
    requested = request.query_params.get('organization')
    if requested:
        if requested not in {str(x) for x in org_ids}:
            raise NotFound()
        org_id = requested
    elif len(org_ids) == 1:
        org_id = org_ids[0]
    else:
        raise NotFound('Specify ?organization= (you belong to several).')
    from apps.accounts.models import Organization
    return Organization.objects.get(pk=org_id)


class CreditBalanceView(APIView):
    """GET — the org's current credit wallet (free/paid/reserved + cap status)."""
    permission_classes = [IsAuthenticated, IsOrgMember]

    def get(self, request):
        org = _resolve_org(request)
        balance = UsageCreditBalance.objects.filter(organization=org).first()
        if balance is None:
            balance = ensure_billing_for_org(org)
        return Response(UsageCreditBalanceSerializer(balance).data)


class UsageSummaryView(APIView):
    """GET — current-month spend, credits remaining, cap status, by-module rollup."""
    permission_classes = [IsAuthenticated, IsOrgMember]

    def get(self, request):
        org = _resolve_org(request)
        balance = UsageCreditBalance.objects.filter(organization=org).first()
        if balance is None:
            balance = ensure_billing_for_org(org)
        limit = UsageLimit.objects.filter(organization=org).first()

        # By-module breakdown over this period (success events only).
        from django.db.models import Sum, Count
        rows = (
            UsageEvent.objects
            .filter(organization=org, status='success',
                    created_at__date__gte=balance.period_start)
            .values('module')
            .annotate(
                credits=Sum('credits_used'),
                billable_hkd=Sum('billable_amount_hkd'),
                count=Count('id'),
            )
        )
        by_module = {
            r['module']: {
                'credits': r['credits'] or 0,
                'billable_hkd': str(r['billable_hkd'] or 0),
                'count': r['count'] or 0,
            } for r in rows
        }

        cap = float(limit.monthly_ai_spend_cap_hkd) if limit else 200.0
        spend = float(balance.current_estimated_spend_hkd)
        return Response({
            'organization': str(org.id),
            'period_start': balance.period_start,
            'free_credits_remaining': balance.free_credits_remaining,
            'paid_credits_remaining': balance.paid_credits_remaining,
            'reserved_credits': balance.reserved_credits,
            'total_available': balance.total_available,
            'free_credits_used_this_month': balance.free_credits_used_this_month,
            'paid_credits_used_this_month': balance.paid_credits_used_this_month,
            'current_estimated_spend_hkd': str(balance.current_estimated_spend_hkd),
            'monthly_ai_spend_cap_hkd': str(cap),
            'spend_percent_of_cap': round((spend / cap) * 100, 1) if cap else 0,
            'cap_status': balance.cap_status,
            'by_module': by_module,
        })


class UsageLimitView(APIView):
    """GET (members) / PATCH (owner only) — spend cap + alert threshold."""
    permission_classes = [IsAuthenticated, IsOrgMember]

    def get(self, request):
        org = _resolve_org(request)
        limit = UsageLimit.objects.filter(organization=org).first()
        if limit is None:
            ensure_billing_for_org(org)
            limit = UsageLimit.objects.get(organization=org)
        return Response(UsageLimitSerializer(limit).data)

    def patch(self, request):
        org = _resolve_org(request)
        # Owner-only write.
        if user_role_in_org(request.user, org.id) != OrganizationMembership.Role.OWNER:
            raise PermissionDenied('Only the organization owner can change usage limits.')
        limit = UsageLimit.objects.filter(organization=org).first()
        if limit is None:
            ensure_billing_for_org(org)
            limit = UsageLimit.objects.get(organization=org)
        ser = UsageLimitSerializer(limit, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()

        # A cap change can move the band → recompute immediately.
        balance = UsageCreditBalance.objects.filter(organization=org).first()
        if balance is not None:
            from .services import cap_monitor
            cap_monitor.recompute_cap_status(balance, persist=True)
        return Response(ser.data)


class UsageEventViewSet(OrgScopeMixin, viewsets.ReadOnlyModelViewSet):
    """Read-only usage ledger. Filter ?module= ?event_type= ?status=."""
    queryset = UsageEvent.objects.select_related('organization').all()
    serializer_class = UsageEventSerializer
    permission_classes = [IsAuthenticated, IsOrgMember]

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get('module'):
            qs = qs.filter(module=p['module'])
        if p.get('event_type'):
            qs = qs.filter(event_type=p['event_type'])
        if p.get('status'):
            qs = qs.filter(status=p['status'])
        return qs


class MonthlyUsageSummaryViewSet(OrgScopeMixin, viewsets.ReadOnlyModelViewSet):
    """Read-only last-12-months rollup."""
    queryset = MonthlyUsageSummary.objects.select_related('organization').all()
    serializer_class = MonthlyUsageSummarySerializer
    permission_classes = [IsAuthenticated, IsOrgMember]
