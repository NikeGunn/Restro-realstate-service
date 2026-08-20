"""
PUBLIC Coffee Pass API — mounted at /public/coffee-pass/, no dashboard auth.

Zero-trust surface (A.1 #6). Every endpoint here assumes a hostile caller:

- The location token is opaque and grants ONLY the public offer view.
- Anything touching customer data requires an OTP-verified session token, which
  is bound to exactly one CRMCustomer and is not a dashboard JWT.
- Responses never contain another customer's data, a raw verification hash, an
  internal note, or a feedback comment.
- The OTP endpoints return the SAME response whether or not a phone is known, so
  this surface cannot enumerate customers.
- Every endpoint is throttled with the Phase 0 public scopes.

The Stripe webhook lives here too because Stripe is an unauthenticated caller:
its signature verification REPLACES CSRF, which is why the view is csrf_exempt.
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common import idempotency
from apps.common.throttling import (
    PublicBurstThrottle, PublicFormThrottle, PublicSustainedThrottle,
)
from apps.common.utils import client_ip

from .models import CoffeePassPlan, PassStatus, PlanStatus
from .serializers import (
    PublicCheckoutSerializer, PublicExperienceSerializer,
    PublicPassSerializer, PublicRequestCodeSerializer, PublicVerifyCodeSerializer,
)
from .services import (
    checkout_service, experience_service, identity_service, plan_service,
    verification_service, webhook_service,
)

logger = logging.getLogger(__name__)

#: Header carrying the signed customer session minted by verify-code.
SESSION_HEADER = 'HTTP_X_COFFEE_PASS_SESSION'

#: Generic OTP response. Identical for known and unknown phones — the entire
#: point is that a caller learns nothing about who is a customer.
GENERIC_OTP_RESPONSE = {'detail': 'code_sent_if_eligible'}


class PublicBase(APIView):
    """Shared plumbing: no auth, throttled, session-aware."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PublicBurstThrottle, PublicSustainedThrottle]

    def get_plan(self, public_token):
        """Resolve the QR token to a plan. Any non-archived plan is viewable."""
        return (
            CoffeePassPlan.objects
            .select_related('organization', 'location')
            .prefetch_related('eligible_items')
            .filter(public_token=public_token)
            .exclude(status=PlanStatus.ARCHIVED)
            .first()
        )

    def get_customer(self, request):
        """Resolve the signed session header to a CRMCustomer, or None."""
        return identity_service.resolve_session(request.META.get(SESSION_HEADER, ''))

    def unauthorized(self):
        return Response({'detail': 'session_required'}, status=status.HTTP_401_UNAUTHORIZED)


class PublicOfferView(PublicBase):
    """
    GET the location's public offer. Pre-authentication, so it exposes ONLY
    plan terms — never whether the viewer is a known customer.
    """

    def get(self, request, public_token):
        plan = self.get_plan(public_token)
        if plan is None:
            return Response({'detail': 'not_found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(plan_service.public_offer_payload(plan))


class PublicRequestCodeView(PublicBase):
    """
    POST a phone number, receive an OTP by WhatsApp.

    ALWAYS returns the same generic body. Rate limiting is enforced per-phone and
    per-IP inside the service, on top of this endpoint's form throttle.
    """
    throttle_classes = [PublicFormThrottle]

    def post(self, request, public_token):
        plan = self.get_plan(public_token)
        if plan is None:
            return Response({'detail': 'not_found'}, status=status.HTTP_404_NOT_FOUND)

        payload = PublicRequestCodeSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        try:
            otp, code = identity_service.request_code(
                organization=plan.organization,
                phone=payload.validated_data['phone'],
                ip=client_ip(request),
            )
        except identity_service.OTPError as exc:
            if exc.reason == 'rate_limited':
                # The ONE case worth telling the truth about — otherwise the user
                # retries forever against a wall.
                return Response(
                    {'detail': 'rate_limited'},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )
            # Invalid phone etc. -> stay generic, reveal nothing.
            return Response(GENERIC_OTP_RESPONSE)

        _deliver_code(plan, otp.phone, code)
        return Response(GENERIC_OTP_RESPONSE)


def _deliver_code(plan, phone, code):
    """
    Send the OTP over the org's WhatsApp channel.

    With no active WhatsApp config the code is logged server-side and the caller
    still sees a generic success. That keeps the endpoint enumeration-safe and
    lets an org pilot Coffee Pass before WhatsApp is provisioned.
    """
    from apps.channels.whatsapp_service import WhatsAppService

    text = (
        f'☕ {plan.organization.name}\n'
        f'Coffee Pass verification code: {code}\n'
        f'Valid for 5 minutes. Do not share this code.'
    )
    try:
        service = WhatsAppService.get_for_organization(plan.organization)
        if service is None:
            logger.warning(
                'Coffee Pass OTP: no WhatsApp config for org %s; code not delivered',
                plan.organization_id,
            )
            return
        service.send_message(phone, text)
    except Exception:
        # Delivery failure must not leak through the generic response.
        logger.warning('Coffee Pass OTP delivery failed', exc_info=True)


class PublicVerifyCodeView(PublicBase):
    """POST phone + code -> a short-lived signed session token."""
    throttle_classes = [PublicFormThrottle]

    def post(self, request, public_token):
        plan = self.get_plan(public_token)
        if plan is None:
            return Response({'detail': 'not_found'}, status=status.HTTP_404_NOT_FOUND)

        payload = PublicVerifyCodeSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        try:
            customer = identity_service.verify_code(
                organization=plan.organization,
                phone=payload.validated_data['phone'],
                code=payload.validated_data['code'],
            )
        except identity_service.OTPError:
            # One generic failure for wrong/expired/exhausted — never say which.
            return Response(
                {'detail': 'invalid_code'}, status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({
            'session': identity_service.issue_session(customer),
            'customer_name': customer.name,
            'has_active_pass': _active_pass(customer, plan.location) is not None,
        })


class PublicExperienceView(PublicBase):
    """
    POST the post-visit answer. Returns the offer decision.

    THE quality gate: a `not_good` answer returns eligible=false and triggers
    service recovery instead of an offer.
    """
    throttle_classes = [PublicFormThrottle]

    def post(self, request, public_token):
        plan = self.get_plan(public_token)
        if plan is None:
            return Response({'detail': 'not_found'}, status=status.HTTP_404_NOT_FOUND)

        customer = self.get_customer(request)
        if customer is None:
            return self.unauthorized()
        if customer.organization_id != plan.organization_id:
            # A session from another tenant must never act here.
            return self.unauthorized()

        payload = PublicExperienceSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        experience, decision = experience_service.submit(
            plan=plan, customer=customer,
            sentiment=data['sentiment'],
            comment=data.get('comment', ''),
            routine_context=data.get('routine_context', ''),
            source='qr',
            ip=client_ip(request),
        )

        return Response({
            'experience_id': str(experience.id),
            'offer': decision.as_dict(),
            # The client uses this to route to the acknowledgement screen.
            'service_recovery': data['sentiment'] == 'not_good',
        }, status=status.HTTP_201_CREATED)


class PublicCheckoutView(PublicBase):
    """
    POST to open a Stripe Checkout session.

    Idempotent at the cache layer so a double-tap can't open two sessions; the
    DB constraints remain the authoritative backstop.
    """
    throttle_classes = [PublicFormThrottle]

    def post(self, request, public_token):
        plan = self.get_plan(public_token)
        if plan is None:
            return Response({'detail': 'not_found'}, status=status.HTTP_404_NOT_FOUND)

        customer = self.get_customer(request)
        if customer is None or customer.organization_id != plan.organization_id:
            return self.unauthorized()

        payload = PublicCheckoutSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        idem_key = (payload.validated_data.get('idempotency_key') or '').strip()
        scoped = f'cp:checkout:{plan.id}:{customer.id}:{idem_key}' if idem_key else ''
        if scoped and not idempotency.claim(scoped, ttl=900):
            return Response(
                {'detail': 'duplicate_submission'}, status=status.HTTP_409_CONFLICT,
            )

        try:
            result = checkout_service.create_checkout(
                plan=plan, customer=customer,
                experience=experience_service.latest_for(customer, plan.location),
                ip=client_ip(request),
            )
        except checkout_service.CheckoutError as exc:
            if scoped:
                idempotency.release(scoped)
            return Response(
                {'detail': exc.reason, **exc.detail},
                status=status.HTTP_409_CONFLICT
                if exc.reason == 'active_pass_exists' else status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            logger.exception('Coffee Pass checkout failed for plan %s', plan.id)
            if scoped:
                idempotency.release(scoped)
            return Response(
                {'detail': 'checkout_failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(result, status=status.HTTP_201_CREATED)


class PublicWalletView(PublicBase):
    """GET the verified customer's own passes at this location."""

    def get(self, request, public_token):
        plan = self.get_plan(public_token)
        if plan is None:
            return Response({'detail': 'not_found'}, status=status.HTTP_404_NOT_FOUND)

        customer = self.get_customer(request)
        if customer is None or customer.organization_id != plan.organization_id:
            return self.unauthorized()

        from .models import CoffeePass
        passes = (
            CoffeePass.objects
            .select_related('location', 'plan')
            # Scoped to THIS customer — the session cannot widen the query.
            .filter(customer=customer, location=plan.location)
            .exclude(status=PassStatus.PENDING_PAYMENT)
            .order_by('-created_at')
        )
        return Response({
            'passes': PublicPassSerializer(passes, many=True).data,
            'customer_name': customer.name,
        })


class PublicVerificationMintView(PublicBase):
    """
    POST to mint a fresh ~90s code for one of the customer's own passes.

    The raw token is returned ONCE, here, and never stored — only its hash is.
    """
    throttle_classes = [PublicFormThrottle]

    def post(self, request, public_token, pass_id):
        plan = self.get_plan(public_token)
        if plan is None:
            return Response({'detail': 'not_found'}, status=status.HTTP_404_NOT_FOUND)

        customer = self.get_customer(request)
        if customer is None or customer.organization_id != plan.organization_id:
            return self.unauthorized()

        from .models import CoffeePass
        # Ownership is enforced in the QUERY, so another customer's pass id is a
        # 404 rather than a permission error that confirms it exists.
        coffee_pass = CoffeePass.objects.filter(
            id=pass_id, customer=customer, organization_id=plan.organization_id,
        ).first()
        if coffee_pass is None:
            return Response({'detail': 'not_found'}, status=status.HTTP_404_NOT_FOUND)

        try:
            token, raw, fallback = verification_service.mint(coffee_pass)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)

        return Response({
            'qr_payload': raw,
            'fallback_code': fallback,
            'expires_at': token.expires_at.isoformat(),
            'ttl_seconds': int((token.expires_at - _now()).total_seconds()),
        })


def _now():
    from django.utils import timezone
    return timezone.now()


def _active_pass(customer, location):
    from .models import CoffeePass
    from django.utils import timezone
    return CoffeePass.objects.filter(
        customer=customer, location=location,
        status=PassStatus.ACTIVE, expires_at__gt=timezone.now(),
    ).first()


# ──────────────────────────────────────────────────────────────────────
# Stripe webhook
# ──────────────────────────────────────────────────────────────────────
@method_decorator(csrf_exempt, name='dispatch')
class StripeWebhookView(APIView):
    """
    Stripe's callback. CSRF-exempt BECAUSE signature verification is strictly
    stronger — Stripe cannot send a CSRF token, and a forged payload fails the
    HMAC check regardless of session state.

    Never throttled: dropping a real payment event is far worse than absorbing
    a burst, and the signature already gates who may call this.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def post(self, request):
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')
        if not sig_header:
            return Response(
                {'detail': 'missing_signature'}, status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            event = webhook_service.verify_and_construct_event(request.body, sig_header)
        except Exception:
            logger.warning('Coffee Pass webhook signature verification failed')
            return Response(
                {'detail': 'invalid_signature'}, status=status.HTTP_400_BAD_REQUEST,
            )

        # Not ours (e.g. an AI-credit purchase on a shared endpoint) -> 200 so
        # Stripe stops retrying, but do nothing.
        if not webhook_service.is_coffee_pass_event(event):
            return Response({'status': 'ignored'})

        event_id = event.get('id', '')
        if webhook_service.is_duplicate_event(event_id):
            return Response({'status': 'duplicate'})

        try:
            result = webhook_service.handle_event(event)
        except Exception:
            logger.exception('Coffee Pass webhook handler failed', extra={'event': event_id})
            # Release the claim and 500 so Stripe RETRIES — swallowing this
            # would silently lose a paid pass.
            webhook_service.release_event(event_id)
            return Response(
                {'detail': 'handler_error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        webhook_service.mark_event_processed(event_id)

        # Deliver notifications only AFTER the activation transaction commits.
        if result.get('status') == 'success':
            transaction.on_commit(_drain_outbox_soon)

        return Response(result)


def _drain_outbox_soon():
    """Nudge the outbox worker; inline fallback keeps dev usable without Celery."""
    try:
        from .tasks import process_outbox_task
        process_outbox_task.delay()
    except Exception:
        logger.info('Could not queue outbox drain; the beat schedule will pick it up')
