"""Coupon redemption API."""
from django.db import transaction
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Organization, OrganizationMembership

from .models import Coupon
from .serializers import (
    CouponPublicSerializer,
    CouponRedemptionSerializer,
    RedeemCouponInputSerializer,
)


def _user_owns_org(user, organization):
    return OrganizationMembership.objects.filter(
        user=user, organization=organization, role=OrganizationMembership.Role.OWNER
    ).exists()


def _resolve(user, code, organization_id):
    """Return (coupon, organization, error_response) — error_response is a DRF Response or None."""
    try:
        coupon = Coupon.objects.get(code=code)
    except Coupon.DoesNotExist:
        return None, None, Response(
            {'detail': 'Invalid coupon code.'}, status=status.HTTP_404_NOT_FOUND
        )
    try:
        organization = Organization.objects.get(pk=organization_id)
    except Organization.DoesNotExist:
        return None, None, Response(
            {'detail': 'Organization not found.'}, status=status.HTTP_404_NOT_FOUND
        )
    if not _user_owns_org(user, organization):
        return None, None, Response(
            {'detail': 'Only an organization owner can redeem a coupon.'},
            status=status.HTTP_403_FORBIDDEN,
        )
    return coupon, organization, None


class CouponValidateView(APIView):
    """Dry-run check — does NOT redeem."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        data = RedeemCouponInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        coupon, organization, err = _resolve(
            request.user, data.validated_data['code'], data.validated_data['organization']
        )
        if err:
            return err
        ok, reason = coupon.check_redeemable(organization=organization)
        if not ok:
            return Response({'valid': False, 'detail': reason}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'valid': True, 'coupon': CouponPublicSerializer(coupon).data})


class CouponRedeemView(APIView):
    """Atomically redeem a coupon for an organization."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        data = RedeemCouponInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        coupon, organization, err = _resolve(
            request.user, data.validated_data['code'], data.validated_data['organization']
        )
        if err:
            return err

        with transaction.atomic():
            # Lock the coupon row to prevent over-redemption races.
            coupon = Coupon.objects.select_for_update().get(pk=coupon.pk)
            ok, reason = coupon.check_redeemable(organization=organization)
            if not ok:
                return Response({'detail': reason}, status=status.HTTP_400_BAD_REQUEST)
            redemption = coupon.apply_to(organization, request.user)

        return Response(
            CouponRedemptionSerializer(redemption).data, status=status.HTTP_201_CREATED
        )
