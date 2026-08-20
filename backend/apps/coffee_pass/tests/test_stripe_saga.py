"""
Stripe checkout → activation saga tests.

Stripe retries webhooks aggressively and will happily deliver the same event
several times. These tests prove that a payment produces EXACTLY ONE pass under
every delivery pattern we can realistically hit: duplicate, out-of-order,
retry-after-crash, and forged.

Stripe itself is mocked — we are testing OUR saga, not their API.
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.coffee_pass.models import (
    CoffeePass, CoffeePassPurchase, PassStatus, PurchaseStatus,
)
from apps.coffee_pass.services import checkout_service, webhook_service


def _session(purchase, *, payment_intent='pi_test_123', amount=12000):
    """A minimal Stripe checkout.session.completed object."""
    return {
        'id': f'cs_test_{purchase.id}',
        'client_reference_id': str(purchase.id),
        'payment_intent': payment_intent,
        'amount_total': amount,
        'payment_status': 'paid',
        'metadata': {'kind': 'coffee_pass', 'purchase_id': str(purchase.id)},
    }


def _pending_purchase(plan, customer):
    return CoffeePassPurchase.objects.create(
        organization=plan.organization, location=plan.location,
        customer=customer, plan=plan, status=PurchaseStatus.PENDING,
        plan_snapshot=plan.build_snapshot(), amount_hkd=plan.price_hkd,
    )


@pytest.fixture(autouse=True)
def no_receipt_lookup():
    """Receipt fetch is observability only — stub it so tests don't hit Stripe."""
    with patch.object(webhook_service, '_safe_receipt_url', return_value=''):
        yield


# ──────────────────────────────────────────────────────────────────────
# Checkout creation
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestCheckoutCreation:
    def _stripe_mock(self):
        stripe = MagicMock()
        stripe.checkout.Session.create.return_value = {
            'id': 'cs_test_abc', 'url': 'https://checkout.stripe.com/pay/cs_test_abc',
        }
        return stripe

    def test_creates_pending_purchase_with_frozen_snapshot(
            self, active_plan, customer, good_experience):
        with patch.object(checkout_service, 'get_stripe', return_value=self._stripe_mock()):
            result = checkout_service.create_checkout(
                plan=active_plan, customer=customer, experience=good_experience,
            )

        purchase = CoffeePassPurchase.objects.get(id=result['purchase_id'])
        assert purchase.status == PurchaseStatus.PENDING
        assert purchase.activated is False
        # The snapshot must capture the terms, not a reference to them.
        assert purchase.plan_snapshot['discount_percent'] == '30.00'
        assert len(purchase.plan_snapshot['eligible_items']) == 3

    def test_uses_a_stable_idempotency_key(self, active_plan, customer, good_experience):
        """A retried POST must return the SAME Stripe session, not open a second."""
        stripe = self._stripe_mock()
        with patch.object(checkout_service, 'get_stripe', return_value=stripe):
            result = checkout_service.create_checkout(
                plan=active_plan, customer=customer, experience=good_experience,
            )

        kwargs = stripe.checkout.Session.create.call_args.kwargs
        assert kwargs['idempotency_key'] == f'coffee_pass_checkout_{result["purchase_id"]}'
        assert kwargs['metadata']['kind'] == 'coffee_pass'

    def test_refuses_after_negative_feedback(self, active_plan, customer,
                                             negative_experience):
        """
        Server-side re-validation.

        A client can POST straight to checkout without ever seeing an offer —
        the gate must hold here too, not only on the offer endpoint.
        """
        with patch.object(checkout_service, 'get_stripe', return_value=self._stripe_mock()):
            with pytest.raises(checkout_service.CheckoutError) as exc:
                checkout_service.create_checkout(
                    plan=active_plan, customer=customer, experience=negative_experience,
                )

        assert exc.value.reason == 'quality_gate_failed'
        assert CoffeePassPurchase.objects.count() == 0

    def test_refuses_when_an_active_pass_exists(self, active_plan, customer,
                                                active_pass, good_experience):
        with patch.object(checkout_service, 'get_stripe', return_value=self._stripe_mock()):
            with pytest.raises(checkout_service.CheckoutError) as exc:
                checkout_service.create_checkout(
                    plan=active_plan, customer=customer, experience=good_experience,
                )
        assert exc.value.reason == 'active_pass_exists'

    def test_refuses_on_a_paused_plan(self, active_plan, customer, good_experience):
        from apps.coffee_pass.models import PlanStatus
        active_plan.status = PlanStatus.PAUSED
        active_plan.save(update_fields=['status'])

        with patch.object(checkout_service, 'get_stripe', return_value=self._stripe_mock()):
            with pytest.raises(checkout_service.CheckoutError) as exc:
                checkout_service.create_checkout(
                    plan=active_plan, customer=customer, experience=good_experience,
                )
        assert exc.value.reason == 'plan_not_sellable'

    def test_stripe_outage_marks_the_orphan_failed(self, active_plan, customer,
                                                   good_experience):
        """
        A purchase row whose session was never created must not sit PENDING
        forever — it would block the customer's next offer.
        """
        stripe = MagicMock()
        stripe.checkout.Session.create.side_effect = RuntimeError('stripe down')

        with patch.object(checkout_service, 'get_stripe', return_value=stripe):
            with pytest.raises(checkout_service.CheckoutError) as exc:
                checkout_service.create_checkout(
                    plan=active_plan, customer=customer, experience=good_experience,
                )

        assert exc.value.reason == 'stripe_unavailable'
        assert CoffeePassPurchase.objects.get().status == PurchaseStatus.FAILED


# ──────────────────────────────────────────────────────────────────────
# Activation idempotency — the core of the saga
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestActivation:
    def test_completed_webhook_activates_exactly_one_pass(self, active_plan, customer):
        purchase = _pending_purchase(active_plan, customer)

        result = webhook_service._handle_completed(_session(purchase))

        assert result['status'] == 'success'
        purchase.refresh_from_db()
        assert purchase.status == PurchaseStatus.PAID
        assert purchase.activated is True

        coffee_pass = CoffeePass.objects.get(purchase=purchase)
        assert coffee_pass.status == PassStatus.ACTIVE
        # 30-day window derived from the SNAPSHOT, not the live plan.
        assert (coffee_pass.expires_at - coffee_pass.starts_at).days == 30

    def test_duplicate_delivery_creates_no_second_pass(self, active_plan, customer):
        """THE Stripe-retry test. Same event twice -> one pass."""
        purchase = _pending_purchase(active_plan, customer)
        session = _session(purchase)

        first = webhook_service._handle_completed(session)
        second = webhook_service._handle_completed(session)

        assert first['status'] == 'success'
        assert second['status'] == 'duplicate'
        assert CoffeePass.objects.filter(purchase=purchase).count() == 1

    def test_five_deliveries_still_one_pass(self, active_plan, customer):
        """Stripe can retry many times over days. The latch must not tire."""
        purchase = _pending_purchase(active_plan, customer)
        session = _session(purchase)

        for _ in range(5):
            webhook_service._handle_completed(session)

        assert CoffeePass.objects.count() == 1

    def test_payment_intent_reuse_across_purchases_is_blocked(
            self, active_plan, customer, customer_2):
        """
        Defense in depth: a replayed/forged event reusing a payment intent that
        already activated a DIFFERENT purchase must be refused.
        """
        first = _pending_purchase(active_plan, customer)
        webhook_service._handle_completed(_session(first, payment_intent='pi_shared'))

        second = _pending_purchase(active_plan, customer_2)
        result = webhook_service._handle_completed(
            _session(second, payment_intent='pi_shared'))

        assert result['status'] == 'duplicate'
        assert CoffeePass.objects.count() == 1

    def test_snapshot_survives_a_later_plan_edit(self, active_plan, customer):
        """
        Plan edits after payment must not change the active pass (PRD §14).
        """
        purchase = _pending_purchase(active_plan, customer)
        webhook_service._handle_completed(_session(purchase))

        active_plan.discount_percent = Decimal('10.00')
        active_plan.price_hkd = Decimal('999.00')
        active_plan.save(update_fields=['discount_percent', 'price_hkd'])

        coffee_pass = CoffeePass.objects.get(purchase=purchase)
        assert coffee_pass.discount_percent == Decimal('30.00')

    def test_missing_purchase_reference_is_an_error_not_a_crash(self):
        result = webhook_service._handle_completed({'id': 'cs_x', 'metadata': {}})
        assert result['status'] == 'error'
        assert result['reason'] == 'missing_purchase_ref'

    def test_unknown_purchase_id_handled(self):
        import uuid
        result = webhook_service._handle_completed({
            'id': 'cs_x', 'client_reference_id': str(uuid.uuid4()), 'metadata': {},
        })
        assert result['reason'] == 'purchase_not_found'

    def test_activation_writes_an_outbox_event_not_a_direct_send(
            self, active_plan, customer):
        """
        A WhatsApp outage must never roll back a paid pass — the notification is
        a durable outbox row committed in the same transaction.
        """
        from apps.coffee_pass.models import CoffeePassOutboxEvent

        purchase = _pending_purchase(active_plan, customer)
        webhook_service._handle_completed(_session(purchase))

        event = CoffeePassOutboxEvent.objects.get(event_type='pass_activated')
        assert event.status == 'pending'
        # Privacy-safe payload: ids only, no phone/name.
        assert 'phone' not in str(event.payload)

    def test_activation_tags_the_customer_as_a_member(self, active_plan, customer):
        from apps.crm.models import CRMCustomerTag

        purchase = _pending_purchase(active_plan, customer)
        webhook_service._handle_completed(_session(purchase))

        assert CRMCustomerTag.objects.filter(
            customer=customer, tag__name='coffee_pass_member').exists()


# ──────────────────────────────────────────────────────────────────────
# Non-success events
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestFailurePaths:
    def test_expired_checkout_creates_no_pass(self, active_plan, customer):
        purchase = _pending_purchase(active_plan, customer)

        result = webhook_service._handle_expired(_session(purchase))

        assert result['status'] == 'expired'
        purchase.refresh_from_db()
        assert purchase.status == PurchaseStatus.EXPIRED
        assert CoffeePass.objects.count() == 0

    def test_late_expiry_event_never_downgrades_a_paid_order(self, active_plan, customer):
        """
        Out-of-order delivery: `expired` arriving AFTER `completed` must not
        revoke a pass the customer paid for.
        """
        purchase = _pending_purchase(active_plan, customer)
        webhook_service._handle_completed(_session(purchase))

        result = webhook_service._handle_expired(_session(purchase))

        assert result['status'] == 'skipped'
        purchase.refresh_from_db()
        assert purchase.status == PurchaseStatus.PAID
        assert CoffeePass.objects.get(purchase=purchase).status == PassStatus.ACTIVE

    def test_payment_failed_does_not_cancel_the_pending_order(self):
        """The customer may retry inside the same session; expiry is the signal."""
        result = webhook_service._handle_failed(
            {'id': 'pi_1', 'last_payment_error': {'message': 'card_declined'}})
        assert result['status'] == 'payment_failed'


# ──────────────────────────────────────────────────────────────────────
# Refunds
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestRefunds:
    def _paid(self, plan, customer, intent='pi_refund'):
        purchase = _pending_purchase(plan, customer)
        webhook_service._handle_completed(_session(purchase, payment_intent=intent))
        purchase.refresh_from_db()
        return purchase

    def test_full_refund_cancels_the_pass(self, active_plan, customer):
        purchase = self._paid(active_plan, customer)

        result = webhook_service._handle_refunded({
            'id': 'ch_1', 'payment_intent': 'pi_refund', 'amount_refunded': 12000,
        })

        assert result['pass_cancelled'] is True
        assert CoffeePass.objects.get(purchase=purchase).status == PassStatus.CANCELLED

    def test_partial_refund_keeps_the_entitlement(self, active_plan, customer):
        """
        v1 policy: only a FULL refund cancels. Clawing back a membership someone
        partly paid for is worse than absorbing the difference.
        """
        purchase = self._paid(active_plan, customer)

        result = webhook_service._handle_refunded({
            'id': 'ch_1', 'payment_intent': 'pi_refund', 'amount_refunded': 3000,
        })

        assert result['pass_cancelled'] is False
        assert CoffeePass.objects.get(purchase=purchase).status == PassStatus.ACTIVE
        purchase.refresh_from_db()
        assert purchase.refunded_amount_hkd == Decimal('30.00')

    def test_duplicate_refund_event_is_idempotent(self, active_plan, customer):
        """Stripe resends the CUMULATIVE total — only the delta may act."""
        self._paid(active_plan, customer)
        charge = {'id': 'ch_1', 'payment_intent': 'pi_refund', 'amount_refunded': 12000}

        first = webhook_service._handle_refunded(charge)
        second = webhook_service._handle_refunded(charge)

        assert first['status'] == 'refunded'
        assert second['status'] == 'duplicate'

    def test_partial_then_full_refund_escalates_once(self, active_plan, customer):
        purchase = self._paid(active_plan, customer)

        webhook_service._handle_refunded({
            'id': 'ch_1', 'payment_intent': 'pi_refund', 'amount_refunded': 3000})
        result = webhook_service._handle_refunded({
            'id': 'ch_1', 'payment_intent': 'pi_refund', 'amount_refunded': 12000})

        assert result['pass_cancelled'] is True
        purchase.refresh_from_db()
        assert purchase.status == PurchaseStatus.REFUNDED

    def test_cancelled_pass_cannot_redeem(self, active_plan, customer, manager):
        """The end-to-end consequence of a refund."""
        from apps.coffee_pass.services import entitlement_service

        purchase = self._paid(active_plan, customer)
        webhook_service._handle_refunded({
            'id': 'ch_1', 'payment_intent': 'pi_refund', 'amount_refunded': 12000})

        coffee_pass = CoffeePass.objects.get(purchase=purchase)
        assert entitlement_service.check(coffee_pass).reason_code == 'cancelled'

    def test_refund_for_unknown_intent_is_skipped(self):
        result = webhook_service._handle_refunded({
            'id': 'ch_x', 'payment_intent': 'pi_nonexistent', 'amount_refunded': 100})
        assert result['status'] == 'skipped'


# ──────────────────────────────────────────────────────────────────────
# Webhook routing + event claim
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestWebhookPlumbing:
    def test_event_claim_dedupes_then_release_allows_retry(self):
        """
        A handler crash must RELEASE the claim, otherwise Stripe's retry would
        be silently swallowed and the payment lost.
        """
        assert webhook_service.is_duplicate_event('evt_1') is False
        assert webhook_service.is_duplicate_event('evt_1') is True

        webhook_service.release_event('evt_1')
        assert webhook_service.is_duplicate_event('evt_1') is False

    def test_foreign_events_are_not_ours(self, active_plan, customer):
        """A credit-pack event on a shared endpoint must not touch Coffee Pass."""
        assert webhook_service.is_coffee_pass_event({
            'type': 'checkout.session.completed',
            'data': {'object': {'metadata': {'kind': 'credit_pack'}}},
        }) is False

    def test_our_events_are_routed_by_metadata(self):
        assert webhook_service.is_coffee_pass_event({
            'type': 'checkout.session.completed',
            'data': {'object': {'metadata': {'kind': 'coffee_pass'}}},
        }) is True

    def test_refund_event_resolved_via_payment_intent(self, active_plan, customer):
        """charge.refunded carries no metadata of ours — resolve by stored PI."""
        purchase = _pending_purchase(active_plan, customer)
        webhook_service._handle_completed(_session(purchase, payment_intent='pi_x'))

        assert webhook_service.is_coffee_pass_event({
            'type': 'charge.refunded',
            'data': {'object': {'payment_intent': 'pi_x'}},
        }) is True

    def test_missing_webhook_secret_raises(self, settings):
        settings.STRIPE_WEBHOOK_SECRET = ''
        settings.COFFEE_PASS_WEBHOOK_SECRET = ''
        with pytest.raises(ValueError):
            webhook_service.verify_and_construct_event(b'{}', 'sig')


# ──────────────────────────────────────────────────────────────────────
# Reconciliation (missed webhook recovery)
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestReconciliation:
    def test_recovers_a_payment_whose_webhook_never_arrived(self, active_plan, customer):
        """
        A webhook lost to a deploy window would otherwise mean the customer paid
        and got nothing. Recovery reuses the SAME activation handler.
        """
        purchase = _pending_purchase(active_plan, customer)
        purchase.stripe_session_id = 'cs_lost'
        purchase.created_at = timezone.now() - timezone.timedelta(minutes=30)
        purchase.save(update_fields=['stripe_session_id', 'created_at'])

        stripe = MagicMock()
        stripe.checkout.Session.retrieve.return_value = _session(purchase)

        with patch.object(webhook_service, 'get_stripe', return_value=stripe):
            result = webhook_service.reconcile_pending_purchases()

        assert result['recovered'] == 1
        assert CoffeePass.objects.filter(purchase=purchase).count() == 1

    def test_recent_pending_purchases_are_left_alone(self, active_plan, customer):
        """Give the real webhook a fair chance before probing Stripe."""
        purchase = _pending_purchase(active_plan, customer)
        purchase.stripe_session_id = 'cs_fresh'
        purchase.save(update_fields=['stripe_session_id'])

        stripe = MagicMock()
        with patch.object(webhook_service, 'get_stripe', return_value=stripe):
            result = webhook_service.reconcile_pending_purchases()

        assert result['checked'] == 0
        stripe.checkout.Session.retrieve.assert_not_called()

    def test_abandoned_checkouts_stop_blocking_new_offers(self, active_plan, customer):
        """
        A stale PENDING purchase is a hard gate on a new offer. The sweeper must
        release it, or one abandoned tab locks the customer out.
        """
        purchase = _pending_purchase(active_plan, customer)
        purchase.created_at = timezone.now() - timezone.timedelta(hours=3)
        purchase.save(update_fields=['created_at'])

        assert checkout_service.expire_stale_pending() == 1
        purchase.refresh_from_db()
        assert purchase.status == PurchaseStatus.EXPIRED
