"""
True-concurrency tests — real threads, real Postgres row locks.

These use `transaction=True` (a real committed DB, not the fast wrapped-in-a-
rollback fixture) plus a `Barrier` so the threads genuinely collide instead of
running one after another. That is the only way to prove the locking claims;
a sequential test would pass even with the locks removed.

Two races cost real money if they ever regress:
  1. Two tills scanning the same customer's phone at the same instant.
  2. Two Stripe webhook deliveries landing on two workers simultaneously.
"""
import threading
from decimal import Decimal

import pytest
from django.db import connections, transaction
from django.utils import timezone

from apps.coffee_pass.models import (
    CoffeePass, CoffeePassPurchase, CoffeePassRedemption, PassStatus, PurchaseStatus,
)
from apps.coffee_pass.services import redemption_service, verification_service, webhook_service


def _run_concurrently(target, count):
    """
    Run `target(index)` in `count` threads that all start at the same moment.

    Each thread closes its own DB connection afterwards — Django does not do
    this for non-request threads, and leaked connections make later tests hang.
    """
    barrier = threading.Barrier(count)
    results, errors = [], []
    lock = threading.Lock()

    def wrapper(index):
        try:
            barrier.wait(timeout=10)
            outcome = target(index)
            with lock:
                results.append(outcome)
        except Exception as exc:  # noqa: BLE001 - we assert on these
            with lock:
                errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=wrapper, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    return results, errors


@pytest.mark.django_db(transaction=True)
class TestConcurrentRedemption:
    def test_two_tills_same_code_exactly_one_redemption(self, active_pass, manager):
        """
        THE till race.

        Two staff scan the same code in the same instant. The conditional UPDATE
        in verification_service.consume() means exactly one gets rowcount 1;
        the other must be refused. Anything else double-discounts the cafe.
        """
        token, _, _ = verification_service.mint(active_pass)

        def attempt(_index):
            try:
                redemption_service.redeem(
                    verification_token_id=token.id,
                    eligible_subtotal=Decimal('100'), user=manager,
                )
                return 'redeemed'
            except redemption_service.RedemptionError as exc:
                return exc.reason

        results, errors = _run_concurrently(attempt, 2)

        assert not errors, f'Unexpected exceptions: {errors}'
        assert results.count('redeemed') == 1, f'Expected exactly one winner, got {results}'
        assert results.count('code_already_used_or_expired') == 1
        assert CoffeePassRedemption.objects.count() == 1

    def test_five_simultaneous_scans_still_one_redemption(self, active_pass, manager):
        """A frantic barista tapping five times must not create five discounts."""
        token, _, _ = verification_service.mint(active_pass)

        def attempt(_index):
            try:
                redemption_service.redeem(
                    verification_token_id=token.id,
                    eligible_subtotal=Decimal('50'), user=manager,
                )
                return 'redeemed'
            except redemption_service.RedemptionError as exc:
                return exc.reason

        results, errors = _run_concurrently(attempt, 5)

        assert not errors, f'Unexpected exceptions: {errors}'
        assert results.count('redeemed') == 1
        assert CoffeePassRedemption.objects.count() == 1

    def test_distinct_codes_both_succeed(self, active_plan, customer, customer_2, manager):
        """
        Sanity check on the lock's SCOPE.

        Two different customers redeeming at once must BOTH succeed — if this
        fails, the locking is too coarse and would serialize the whole cafe.
        """
        from apps.coffee_pass.tests.conftest import make_active_pass

        pass_a = make_active_pass(active_plan, customer)
        pass_b = make_active_pass(active_plan, customer_2)
        token_a, _, _ = verification_service.mint(pass_a)
        token_b, _, _ = verification_service.mint(pass_b)
        tokens = [token_a, token_b]

        def attempt(index):
            try:
                redemption_service.redeem(
                    verification_token_id=tokens[index].id,
                    eligible_subtotal=Decimal('40'), user=manager,
                )
                return 'redeemed'
            except redemption_service.RedemptionError as exc:
                return exc.reason

        results, errors = _run_concurrently(attempt, 2)

        assert not errors, f'Unexpected exceptions: {errors}'
        assert results.count('redeemed') == 2
        assert CoffeePassRedemption.objects.count() == 2


@pytest.mark.django_db(transaction=True)
class TestConcurrentWebhook:
    def _pending(self, plan, customer):
        return CoffeePassPurchase.objects.create(
            organization=plan.organization, location=plan.location,
            customer=customer, plan=plan, status=PurchaseStatus.PENDING,
            plan_snapshot=plan.build_snapshot(), amount_hkd=plan.price_hkd,
        )

    def test_simultaneous_deliveries_activate_exactly_one_pass(
            self, active_plan, customer, monkeypatch):
        """
        THE webhook race.

        Stripe delivers the same event to two workers at once. The
        select_for_update + one-way `activated` latch must yield ONE pass.
        The customer paid once; they get one membership.
        """
        monkeypatch.setattr(webhook_service, '_safe_receipt_url', lambda pi: '')

        purchase = self._pending(active_plan, customer)
        session = {
            'id': f'cs_{purchase.id}',
            'client_reference_id': str(purchase.id),
            'payment_intent': 'pi_concurrent',
            'amount_total': 12000,
            'metadata': {'kind': 'coffee_pass', 'purchase_id': str(purchase.id)},
        }

        def deliver(_index):
            return webhook_service._handle_completed(session)['status']

        results, errors = _run_concurrently(deliver, 2)

        assert not errors, f'Unexpected exceptions: {errors}'
        assert CoffeePass.objects.filter(purchase=purchase).count() == 1
        assert results.count('success') == 1
        assert results.count('duplicate') == 1

    def test_four_deliveries_still_one_pass(self, active_plan, customer, monkeypatch):
        monkeypatch.setattr(webhook_service, '_safe_receipt_url', lambda pi: '')

        purchase = self._pending(active_plan, customer)
        session = {
            'id': f'cs_{purchase.id}',
            'client_reference_id': str(purchase.id),
            'payment_intent': 'pi_storm',
            'amount_total': 12000,
            'metadata': {'kind': 'coffee_pass', 'purchase_id': str(purchase.id)},
        }

        def deliver(_index):
            return webhook_service._handle_completed(session)['status']

        _, errors = _run_concurrently(deliver, 4)

        assert not errors, f'Unexpected exceptions: {errors}'
        assert CoffeePass.objects.count() == 1
        purchase.refresh_from_db()
        assert purchase.activated is True


@pytest.mark.django_db(transaction=True)
class TestDatabaseConstraints:
    def test_active_pass_uniqueness_is_enforced_by_the_database(
            self, active_plan, customer):
        """
        The partial unique index is the AUTHORITATIVE backstop.

        Even if every service-level check were bypassed, Postgres must refuse a
        second ACTIVE pass for the same (customer, location, plan).
        """
        from django.db.utils import IntegrityError

        from apps.coffee_pass.tests.conftest import make_active_pass

        make_active_pass(active_plan, customer)

        with pytest.raises(IntegrityError):
            make_active_pass(active_plan, customer)

    def test_expired_passes_do_not_block_a_new_one(self, active_plan, customer):
        """
        The constraint is PARTIAL (status='active') on purpose: a customer whose
        pass expired must be able to buy again.
        """
        from apps.coffee_pass.tests.conftest import make_active_pass

        old = make_active_pass(active_plan, customer)
        old.status = PassStatus.EXPIRED
        old.save(update_fields=['status'])

        fresh = make_active_pass(active_plan, customer)
        assert fresh.status == PassStatus.ACTIVE
        assert CoffeePass.objects.filter(customer=customer).count() == 2

    def test_stripe_session_id_is_unique_when_present(self, active_plan, customer,
                                                     customer_2):
        """Two purchases can never claim the same Stripe session."""
        from django.db.utils import IntegrityError

        first = CoffeePassPurchase.objects.create(
            organization=active_plan.organization, location=active_plan.location,
            customer=customer, plan=active_plan, amount_hkd=Decimal('120'),
            stripe_session_id='cs_duplicate',
        )
        assert first.pk

        with pytest.raises(IntegrityError):
            CoffeePassPurchase.objects.create(
                organization=active_plan.organization, location=active_plan.location,
                customer=customer_2, plan=active_plan, amount_hkd=Decimal('120'),
                stripe_session_id='cs_duplicate',
            )

    def test_blank_stripe_ids_are_unconstrained(self, active_plan, customer, customer_2):
        """
        Pending orders have no session id yet. The constraint is partial so many
        blank rows coexist — otherwise only one customer could ever be mid-checkout.
        """
        for buyer in (customer, customer_2):
            CoffeePassPurchase.objects.create(
                organization=active_plan.organization, location=active_plan.location,
                customer=buyer, plan=active_plan, amount_hkd=Decimal('120'),
            )
        assert CoffeePassPurchase.objects.filter(stripe_session_id='').count() == 2

    def test_outbox_idempotency_key_is_unique(self, active_plan, customer):
        """One delivery intent per key — the guarantee behind "notify only once"."""
        from django.db.utils import IntegrityError

        from apps.coffee_pass.models import CoffeePassOutboxEvent

        CoffeePassOutboxEvent.objects.create(
            organization=active_plan.organization, event_type='pass_activated',
            aggregate_type='CoffeePass', idempotency_key='dup_key',
        )
        with pytest.raises(IntegrityError):
            CoffeePassOutboxEvent.objects.create(
                organization=active_plan.organization, event_type='pass_activated',
                aggregate_type='CoffeePass', idempotency_key='dup_key',
            )

    def test_verification_token_hash_is_unique(self, active_pass):
        from django.db.utils import IntegrityError

        from apps.coffee_pass.models import CoffeePassVerificationToken

        CoffeePassVerificationToken.objects.create(
            coffee_pass=active_pass, token_hash='a' * 64,
            expires_at=timezone.now() + timezone.timedelta(seconds=90),
        )
        with pytest.raises(IntegrityError):
            CoffeePassVerificationToken.objects.create(
                coffee_pass=active_pass, token_hash='a' * 64,
                expires_at=timezone.now() + timezone.timedelta(seconds=90),
            )
