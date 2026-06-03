"""
Stripe payment views — credit-pack purchases + webhook.

Security posture:
- The webhook is the ONLY unauthenticated mutating endpoint; CSRF is exempt
  because Stripe can't send a CSRF token — the signature verification REPLACES
  CSRF (a forged body fails construct_event → 400).
- Checkout creation is owner-only + rate-limited; org membership is verified.
- The publishable key is the only Stripe key ever returned to a client.
- No internal details (tracebacks/keys) leak in error responses.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied, NotFound

from apps.accounts.models import Organization, OrganizationMembership
from apps.common.mixins import OrgScopeMixin
from apps.common.permissions import IsOrgMember, user_role_in_org

from .throttling import CheckoutThrottle
from .models import CreditPack, CreditPurchase
from .serializers import (
    CreditPackSerializer, CreditPurchaseSerializer,
    CheckoutRequestSerializer, RefundRequestSerializer,
)
from .services import CreditCheckoutService, StripeRefundService, StripeWebhookService

logger = logging.getLogger(__name__)


def _require_owner(user, org_id):
    if user_role_in_org(user, org_id) != OrganizationMembership.Role.OWNER:
        raise PermissionDenied('Only the organization owner can do this.')


class StripeConfigView(APIView):
    """Return the publishable key (never the secret) for Stripe.js init."""
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({'publishable_key': settings.STRIPE_PUBLISHABLE_KEY})


class CreditPackViewSet(viewsets.ReadOnlyModelViewSet):
    """Sellable credit packs — readable by any authenticated member."""
    queryset = CreditPack.objects.filter(is_active=True)
    serializer_class = CreditPackSerializer
    permission_classes = [IsAuthenticated]


class CreateCheckoutSessionView(APIView):
    """Owner-only: start a Stripe Checkout for a credit pack."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [CheckoutThrottle]

    def post(self, request):
        ser = CheckoutRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        org_id = str(data['organization'])
        # Membership + owner check (cross-org → 404, not a member → 404).
        if not OrganizationMembership.objects.filter(
            user=request.user, organization_id=org_id,
        ).exists():
            raise NotFound()
        _require_owner(request.user, org_id)

        try:
            org = Organization.objects.get(id=org_id)
            pack = CreditPack.objects.get(id=data['pack'], is_active=True)
        except (Organization.DoesNotExist, CreditPack.DoesNotExist):
            raise NotFound()

        if not settings.STRIPE_SECRET_KEY:
            return Response({'detail': 'Payment system is not configured.'},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)

        try:
            result = CreditCheckoutService.create_checkout_session(
                organization=org, pack=pack, user=request.user,
                success_url=data.get('success_url') or None,
                cancel_url=data.get('cancel_url') or None,
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.error('Stripe checkout creation failed', exc_info=True)
            return Response({'detail': 'Payment service temporarily unavailable.'},
                            status=status.HTTP_502_BAD_GATEWAY)
        return Response(result)


@method_decorator(csrf_exempt, name='dispatch')
class StripeWebhookView(View):
    """Stripe webhook. CSRF-exempt; signature verification replaces CSRF."""

    def post(self, request) -> HttpResponse:
        sig = request.META.get('HTTP_STRIPE_SIGNATURE', '')
        if not sig:
            logger.warning('Stripe webhook without signature header')
            return HttpResponse(status=400)

        try:
            event = StripeWebhookService.verify_and_construct_event(request.body, sig)
        except ValueError:
            logger.warning('Stripe webhook: invalid payload / not configured')
            return HttpResponse(status=400)
        except Exception as e:
            logger.warning('Stripe webhook signature verification failed: %s', e)
            return HttpResponse(status=400)

        # Layer 1 idempotency: atomically claim the event id.
        if StripeWebhookService.is_duplicate_event(event['id']):
            return JsonResponse({'status': 'duplicate'})

        try:
            result = StripeWebhookService.handle_event(event)
        except Exception:
            # Release the claim so Stripe's retry is processed (not masked), and
            # 5xx so Stripe knows to retry.
            StripeWebhookService.release_event(event['id'])
            logger.error('Stripe webhook processing failed', exc_info=True)
            return HttpResponse(status=500)

        StripeWebhookService.mark_event_processed(event['id'])
        return JsonResponse(result)


class CreditPurchaseViewSet(OrgScopeMixin, viewsets.ReadOnlyModelViewSet):
    """Read-only purchase history, org-scoped."""
    queryset = CreditPurchase.objects.select_related('pack', 'organization').all()
    serializer_class = CreditPurchaseSerializer
    permission_classes = [IsAuthenticated, IsOrgMember]


class RefundView(APIView):
    """Owner-only refund of a credit purchase."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = RefundRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        try:
            purchase = CreditPurchase.objects.select_related('organization').get(
                id=data['purchase'])
        except CreditPurchase.DoesNotExist:
            raise NotFound()

        # Must be a member of the purchase's org, and owner to refund.
        if not OrganizationMembership.objects.filter(
            user=request.user, organization_id=purchase.organization_id,
        ).exists():
            raise NotFound()
        _require_owner(request.user, purchase.organization_id)

        try:
            result = StripeRefundService.create_refund(
                purchase=purchase,
                amount_hkd=data.get('amount_hkd'),
                reason=data.get('reason', 'requested_by_customer'),
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.error('Stripe refund failed', exc_info=True)
            return Response({'detail': 'Refund processing failed.'},
                            status=status.HTTP_502_BAD_GATEWAY)
        return Response(result)
