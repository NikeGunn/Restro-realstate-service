"""
Public customer flow + notification tests.

Two themes:

1. The public surface is zero-trust. It must not enumerate customers, must not
   accept a session from another tenant, and must never return another
   customer's pass.
2. Negative feedback must be a dead end for selling — no offer, no checkout, no
   promotional message — while still being fully captured for service recovery.
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.coffee_pass.models import (
    CoffeeExperience, CoffeePassOutboxEvent, OutboxStatus, PassStatus, Sentiment,
)
from apps.coffee_pass.public_views import SESSION_HEADER
from apps.coffee_pass.services import (
    experience_service, identity_service, notification_service,
)


def _url(plan, suffix=''):
    return f'/public/coffee-pass/{plan.public_token}/{suffix}'


def _session_header(customer):
    return {SESSION_HEADER: identity_service.issue_session(customer)}


@pytest.fixture(autouse=True)
def no_whatsapp():
    """Never hit the network in tests; assert on the call instead."""
    with patch('apps.channels.whatsapp_service.WhatsAppService.get_for_organization',
               return_value=None):
        yield


# ──────────────────────────────────────────────────────────────────────
# Public offer + OTP
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestPublicOffer:
    def test_offer_is_readable_without_a_session(self, api, active_plan):
        """The QR landing page must work before anyone identifies themselves."""
        response = api.get(_url(active_plan, 'offer/'))

        assert response.status_code == 200
        assert response.data['price_hkd'] == '120.00'
        assert response.data['break_even_visits'] == 10

    def test_offer_exposes_no_customer_data(self, api, active_plan, customer,
                                            active_pass):
        """Pre-auth, the page must not hint at who is a customer."""
        response = api.get(_url(active_plan, 'offer/'))
        body = str(response.data)

        assert customer.name not in body
        assert customer.phone not in body

    def test_unknown_token_404s(self, api):
        assert api.get('/public/coffee-pass/deadbeef/offer/').status_code == 404

    def test_customer_page_renders_standalone_html(self, client, active_plan):
        """The page must not depend on the React admin bundle."""
        response = client.get(_url(active_plan))

        assert response.status_code == 200
        content = response.content.decode()
        assert '<!DOCTYPE html>' in content
        assert '/static/js/' not in content  # no admin bundle

    def test_unknown_token_page_404s_gracefully(self, client):
        response = client.get('/public/coffee-pass/nope/')
        assert response.status_code == 404
        assert b'Not available' in response.content


@pytest.mark.django_db
class TestPublicOTP:
    def test_response_is_identical_for_known_and_unknown_numbers(self, api, active_plan,
                                                                customer):
        """
        THE enumeration test.

        A caller must not be able to tell whether a phone belongs to a customer.
        Both responses must be byte-identical.
        """
        known = api.post(_url(active_plan, 'auth/request-code/'),
                         {'phone': customer.phone}, format='json')
        unknown = api.post(_url(active_plan, 'auth/request-code/'),
                           {'phone': '+85298887777'}, format='json')

        assert known.status_code == unknown.status_code == 200
        assert known.data == unknown.data

    def test_invalid_phone_also_returns_generic_success(self, api, active_plan):
        response = api.post(_url(active_plan, 'auth/request-code/'),
                            {'phone': 'not-a-phone'}, format='json')
        assert response.status_code == 200
        assert response.data['detail'] == 'code_sent_if_eligible'

    def test_verify_returns_a_session(self, api, active_plan, org):
        _, code = identity_service.request_code(
            organization=org, phone='+85251234567')

        response = api.post(_url(active_plan, 'auth/verify-code/'),
                            {'phone': '+85251234567', 'code': code}, format='json')

        assert response.status_code == 200
        assert identity_service.resolve_session(response.data['session']) is not None

    def test_wrong_code_gives_one_generic_failure(self, api, active_plan, org):
        identity_service.request_code(organization=org, phone='+85251234567')
        response = api.post(_url(active_plan, 'auth/verify-code/'),
                            {'phone': '+85251234567', 'code': '000000'}, format='json')

        assert response.status_code == 400
        assert response.data['detail'] == 'invalid_code'

    def test_existing_member_is_flagged_so_the_ui_shows_the_wallet(
            self, api, active_plan, customer, active_pass, org):
        """PRD §14: a customer with an active pass sees their wallet, not an offer."""
        _, code = identity_service.request_code(
            organization=org, phone=customer.phone)

        response = api.post(_url(active_plan, 'auth/verify-code/'),
                            {'phone': customer.phone, 'code': code}, format='json')

        assert response.data['has_active_pass'] is True


# ──────────────────────────────────────────────────────────────────────
# Experience — the quality gate end to end
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestPublicExperience:
    def test_good_feedback_yields_an_eligible_offer(self, api, active_plan, customer):
        response = api.post(
            _url(active_plan, 'experiences/'),
            {'sentiment': 'good', 'routine_context': 'work_nearby'},
            format='json', **_session_header(customer))

        assert response.status_code == 201
        assert response.data['offer']['eligible'] is True
        assert response.data['service_recovery'] is False

    def test_not_good_gives_no_offer_and_triggers_recovery(self, api, active_plan,
                                                          customer):
        """
        THE product-safety path.

        Bad coffee -> acknowledgement, a CRM tag, and an outbox event that is
        explicitly NOT promotional. No offer, ever.
        """
        response = api.post(
            _url(active_plan, 'experiences/'),
            {'sentiment': 'not_good', 'comment': 'Cold and bitter',
             'routine_context': 'work_nearby'},
            format='json', **_session_header(customer))

        assert response.status_code == 201
        assert response.data['offer']['eligible'] is False
        assert response.data['offer']['reason_code'] == 'quality_gate_failed'
        assert response.data['service_recovery'] is True

        # Captured for the owner, tagged for the workflow.
        from apps.crm.models import CRMCustomerTag
        assert CRMCustomerTag.objects.filter(
            customer=customer, tag__name='coffee_negative_feedback').exists()

    def test_negative_feedback_blocks_checkout_too(self, api, active_plan, customer):
        """The gate must hold even if the client skips the offer screen."""
        api.post(_url(active_plan, 'experiences/'),
                 {'sentiment': 'not_good', 'comment': 'Burnt'},
                 format='json', **_session_header(customer))

        response = api.post(_url(active_plan, 'checkout/'), {},
                            format='json', **_session_header(customer))

        assert response.status_code == 400
        assert response.data['detail'] == 'quality_gate_failed'

    def test_recovery_message_contains_no_promotion(self, api, active_plan, customer):
        """A customer who complained must never be marketed to about the pass."""
        api.post(_url(active_plan, 'experiences/'),
                 {'sentiment': 'not_good', 'comment': 'Bad'},
                 format='json', **_session_header(customer))

        text = notification_service.render(
            experience_service.EVENT_FEEDBACK_NEGATIVE, 'en',
            {'location': 'Central Branch'})

        lowered = text.lower()
        for promo_word in ('coffee pass', 'discount', 'buy', '30%', 'offer'):
            assert promo_word not in lowered

    def test_comment_is_never_echoed_to_the_public_response(self, api, active_plan,
                                                           customer):
        response = api.post(
            _url(active_plan, 'experiences/'),
            {'sentiment': 'not_good', 'comment': 'SECRET-COMPLAINT-TEXT'},
            format='json', **_session_header(customer))
        assert 'SECRET-COMPLAINT-TEXT' not in str(response.data)

    def test_session_required(self, api, active_plan):
        response = api.post(_url(active_plan, 'experiences/'),
                            {'sentiment': 'good'}, format='json')
        assert response.status_code == 401

    def test_session_from_another_tenant_rejected(self, api, active_plan, customer_b):
        """A valid session must not act on a different organization's plan."""
        response = api.post(_url(active_plan, 'experiences/'), {'sentiment': 'good'},
                            format='json', **_session_header(customer_b))
        assert response.status_code == 401

    def test_invalid_sentiment_rejected(self, api, active_plan, customer):
        response = api.post(_url(active_plan, 'experiences/'),
                            {'sentiment': 'fantastic'},
                            format='json', **_session_header(customer))
        assert response.status_code == 400


# ──────────────────────────────────────────────────────────────────────
# Wallet
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestPublicWallet:
    def test_customer_sees_their_own_pass(self, api, active_plan, customer, active_pass):
        response = api.get(_url(active_plan, 'wallet/'), **_session_header(customer))

        assert response.status_code == 200
        assert len(response.data['passes']) == 1
        assert response.data['passes'][0]['id'] == str(active_pass.id)

    def test_customer_never_sees_another_customers_pass(self, api, active_plan,
                                                       customer, customer_2,
                                                       active_pass):
        """Hard isolation: the session cannot widen the query."""
        response = api.get(_url(active_plan, 'wallet/'), **_session_header(customer_2))

        assert response.status_code == 200
        assert response.data['passes'] == []

    def test_mint_returns_a_short_lived_code(self, api, active_plan, customer,
                                            active_pass):
        response = api.post(
            _url(active_plan, f'wallet/{active_pass.id}/verification/'),
            {}, format='json', **_session_header(customer))

        assert response.status_code == 200
        assert response.data['ttl_seconds'] <= 90
        assert len(response.data['fallback_code']) == 6

    def test_cannot_mint_for_someone_elses_pass(self, api, active_plan, customer_2,
                                                active_pass):
        """
        404 (not 403): confirming the pass exists would leak that another
        customer holds one.
        """
        response = api.post(
            _url(active_plan, f'wallet/{active_pass.id}/verification/'),
            {}, format='json', **_session_header(customer_2))
        assert response.status_code == 404

    def test_expired_pass_cannot_mint(self, api, active_plan, customer, active_pass):
        active_pass.expires_at = timezone.now() - timezone.timedelta(days=1)
        active_pass.save(update_fields=['expires_at'])

        response = api.post(
            _url(active_plan, f'wallet/{active_pass.id}/verification/'),
            {}, format='json', **_session_header(customer))
        assert response.status_code == 409


# ──────────────────────────────────────────────────────────────────────
# Webhook endpoint security
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestWebhookEndpoint:
    URL = '/public/coffee-pass/stripe/webhook/'

    def test_missing_signature_rejected(self, api):
        assert api.post(self.URL, {}, format='json').status_code == 400

    def test_forged_signature_rejected(self, api, settings):
        """Signature verification REPLACES CSRF here — it must be strict."""
        settings.STRIPE_WEBHOOK_SECRET = 'whsec_test'
        response = api.post(self.URL, data='{"id":"evt_x"}',
                            content_type='application/json',
                            HTTP_STRIPE_SIGNATURE='t=1,v1=forged')
        assert response.status_code == 400

    def test_endpoint_is_csrf_exempt(self):
        from apps.coffee_pass.public_views import StripeWebhookView
        assert getattr(StripeWebhookView.as_view(), 'csrf_exempt', False) is True


# ──────────────────────────────────────────────────────────────────────
# Notifications: consent, cadence, quality suppression
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestNotificationGates:
    def test_transactional_messages_bypass_marketing_consent(self, customer):
        """
        A receipt is owed to a paying customer regardless of marketing
        preference — conflating the two would hide receipts from people.
        """
        allowed, reason = notification_service.may_send(
            experience_service.EVENT_PASS_ACTIVATED, customer)

        assert allowed is True
        assert reason == 'transactional'

    def test_marketing_requires_explicit_consent(self, customer):
        allowed, reason = notification_service.may_send(
            experience_service.EVENT_EXPIRY_REMINDER, customer)

        assert allowed is False
        assert reason == 'no_marketing_consent'

    def test_marketing_allowed_once_consent_is_given(self, customer):
        from apps.crm.models import ConsentSource
        from apps.crm.services import consent_service

        consent_service.record_consent(
            customer, True, ConsentSource.MANUAL, channels=['whatsapp'])

        allowed, _ = notification_service.may_send(
            experience_service.EVENT_EXPIRY_REMINDER, customer)
        assert allowed is True

    def test_recent_bad_experience_suppresses_a_reminder(self, customer, location,
                                                        active_plan):
        """
        A.6: quality is re-checked at SEND time. Someone who had a bad coffee
        yesterday must not get a "come back" nudge today, consent or not.
        """
        from apps.crm.models import ConsentSource
        from apps.crm.services import consent_service

        consent_service.record_consent(
            customer, True, ConsentSource.MANUAL, channels=['whatsapp'])
        CoffeeExperience.objects.create(
            organization=active_plan.organization, location=location,
            customer=customer, sentiment=Sentiment.NOT_GOOD,
        )

        allowed, reason = notification_service.may_send(
            experience_service.EVENT_EXPIRY_REMINDER, customer, location=location)

        assert allowed is False
        assert reason == 'recent_negative_experience'

    def test_customer_without_a_phone_is_skipped(self, org):
        from apps.crm.models import CRMCustomer, CustomerSource

        emailer = CRMCustomer.objects.create(
            organization=org, name='Email Only', email='a@b.test',
            source=CustomerSource.MANUAL)

        allowed, reason = notification_service.may_send(
            experience_service.EVENT_PASS_ACTIVATED, emailer)
        assert allowed is False
        assert reason == 'no_channel'

    def test_inactive_customer_is_skipped(self, customer):
        customer.is_active = False
        customer.save(update_fields=['is_active'])

        allowed, reason = notification_service.may_send(
            experience_service.EVENT_PASS_ACTIVATED, customer)
        assert reason == 'customer_inactive'


@pytest.mark.django_db
class TestOutboxDelivery:
    def _event(self, org, customer, coffee_pass, event_type):
        return CoffeePassOutboxEvent.objects.create(
            organization=org, event_type=event_type,
            aggregate_type='CoffeePass', aggregate_id=coffee_pass.id,
            payload={'customer_id': str(customer.id), 'pass_id': str(coffee_pass.id)},
            idempotency_key=f'{event_type}:{coffee_pass.id}',
        )

    def test_delivery_marks_sent_when_whatsapp_succeeds(self, org, customer,
                                                        active_pass):
        event = self._event(org, customer, active_pass,
                            experience_service.EVENT_PASS_ACTIVATED)

        service = MagicMock()
        service.send_message.return_value = 'wamid.123'
        with patch('apps.channels.whatsapp_service.WhatsAppService.get_for_organization',
                   return_value=service):
            result = notification_service.deliver(event)

        assert result['status'] == 'sent'
        event.refresh_from_db()
        assert event.status == OutboxStatus.SENT

    def test_send_failure_schedules_a_retry_not_a_loss(self, org, customer, active_pass):
        """
        A failed WhatsApp send must never lose the intent — it backs off and
        retries, and the paid pass is untouched.
        """
        event = self._event(org, customer, active_pass,
                            experience_service.EVENT_PASS_ACTIVATED)

        service = MagicMock()
        service.send_message.return_value = None  # provider failure
        with patch('apps.channels.whatsapp_service.WhatsAppService.get_for_organization',
                   return_value=service):
            result = notification_service.deliver(event)

        assert result['status'] == 'failed'
        event.refresh_from_db()
        assert event.status == OutboxStatus.PENDING
        assert event.attempt_count == 1
        assert event.available_at > timezone.now()  # backoff applied

    def test_attempts_are_bounded(self, org, customer, active_pass, settings):
        """After the ceiling the row stays FAILED for an operator to see."""
        settings.COFFEE_PASS_SETTINGS = {
            **settings.COFFEE_PASS_SETTINGS, 'OUTBOX_MAX_ATTEMPTS': 2,
        }
        event = self._event(org, customer, active_pass,
                            experience_service.EVENT_PASS_ACTIVATED)

        service = MagicMock()
        service.send_message.return_value = None
        with patch('apps.channels.whatsapp_service.WhatsAppService.get_for_organization',
                   return_value=service):
            for _ in range(2):
                event.refresh_from_db()
                notification_service.deliver(event)

        event.refresh_from_db()
        assert event.status == OutboxStatus.FAILED

    def test_no_whatsapp_config_is_a_skip_not_a_crash(self, org, customer, active_pass):
        """Many orgs run Coffee Pass without WhatsApp; the pass is unaffected."""
        event = self._event(org, customer, active_pass,
                            experience_service.EVENT_PASS_ACTIVATED)
        result = notification_service.deliver(event)
        assert result['status'] == 'failed'  # retried, never raised

    def test_delivery_never_raises(self, org, customer, active_pass):
        """A crash here must not poison the whole batch."""
        event = self._event(org, customer, active_pass,
                            experience_service.EVENT_PASS_ACTIVATED)

        with patch.object(notification_service, '_deliver_inner',
                          side_effect=RuntimeError('boom')):
            result = notification_service.deliver(event)

        assert result['status'] == 'failed'

    def test_reminder_skipped_when_the_pass_is_no_longer_active(self, org, customer,
                                                               active_pass):
        """State is re-checked at send time, not at enqueue time."""
        from apps.crm.models import ConsentSource
        from apps.crm.services import consent_service

        consent_service.record_consent(
            customer, True, ConsentSource.MANUAL, channels=['whatsapp'])
        active_pass.status = PassStatus.CANCELLED
        active_pass.save(update_fields=['status'])

        event = self._event(org, customer, active_pass,
                            experience_service.EVENT_EXPIRY_REMINDER)
        result = notification_service.deliver(event)

        assert result['status'] == 'skipped'
        assert result['reason'] == 'pass_not_active'
