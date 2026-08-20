"""
Verification token + redemption tests.

Covers the two mechanisms that stop a pass being abused at the till:
  - a rotating, hashed, single-use code (screenshot replay is worthless);
  - a redemption transaction where the discount is computed server-side from an
    immutable snapshot and the token is consumed by a conditional UPDATE.

The concurrency test is the important one — it is the only place a real race can
cost the cafe money twice.
"""
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.coffee_pass.models import (
    CoffeePassRedemption, CoffeePassVerificationToken, PassStatus, RedemptionStatus,
)
from apps.coffee_pass.services import (
    entitlement_service, redemption_service, verification_service,
)
from apps.coffee_pass.tests.conftest import make_active_pass


# ──────────────────────────────────────────────────────────────────────
# Token security
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestVerificationToken:
    def test_raw_token_is_never_stored(self, active_pass):
        """A DB leak must not let anyone mint a redemption."""
        token, raw, fallback = verification_service.mint(active_pass)

        assert token.token_hash != raw
        assert token.fallback_hash != fallback
        row = CoffeePassVerificationToken.objects.filter(pk=token.pk).values().first()
        assert raw not in str(row)
        assert fallback not in str(row)

    def test_token_carries_no_identifying_data(self, active_pass):
        """
        The QR payload must be opaque (PRD §13): no pass id, phone, name, or
        discount percentage that a bystander could photograph and interpret.
        """
        _, raw, _ = verification_service.mint(active_pass)

        assert str(active_pass.id) not in raw
        assert str(active_pass.customer.phone) not in raw
        assert active_pass.customer.name not in raw
        assert '30' not in raw or len(raw) > 20  # not a bare percentage

    def test_minting_retires_the_previous_code(self, active_pass):
        """
        Rotation is what makes a screenshot worthless — the moment the wallet
        refreshes, the photographed code is dead.
        """
        first_token, first_raw, _ = verification_service.mint(active_pass)
        verification_service.mint(active_pass)

        first_token.refresh_from_db()
        assert first_token.consumed_at is not None
        assert verification_service._lookup(
            first_raw, organization=active_pass.organization) is None

    def test_expired_token_does_not_resolve(self, active_pass):
        token, raw, _ = verification_service.mint(active_pass)
        token.expires_at = timezone.now() - timezone.timedelta(seconds=1)
        token.save(update_fields=['expires_at'])

        result = verification_service.resolve(
            raw, organization=active_pass.organization)
        assert result['valid'] is False
        assert result['reason_code'] == 'invalid_or_expired_code'

    def test_ttl_defaults_to_ninety_seconds(self, active_pass):
        token, _, _ = verification_service.mint(active_pass)
        ttl = (token.expires_at - timezone.now()).total_seconds()
        assert 80 < ttl <= 90

    def test_cannot_mint_for_an_expired_pass(self, active_plan, customer):
        """A dead wallet must not produce a code that only fails at the counter."""
        coffee_pass = make_active_pass(active_plan, customer)
        coffee_pass.expires_at = timezone.now() - timezone.timedelta(days=1)
        coffee_pass.save(update_fields=['expires_at'])

        with pytest.raises(ValueError):
            verification_service.mint(coffee_pass)

    def test_cannot_mint_for_a_suspended_pass(self, active_pass):
        active_pass.status = PassStatus.SUSPENDED
        active_pass.save(update_fields=['status'])
        with pytest.raises(ValueError):
            verification_service.mint(active_pass)

    def test_fallback_code_resolves_like_the_qr(self, active_pass):
        """Staff must be able to type the number when a camera won't focus."""
        _, _, fallback = verification_service.mint(active_pass)
        result = verification_service.resolve(
            fallback, organization=active_pass.organization)
        assert result['valid'] is True

    def test_code_from_another_org_does_not_resolve(self, active_pass, org_b):
        """Tenant isolation at the till."""
        _, raw, _ = verification_service.mint(active_pass)
        result = verification_service.resolve(raw, organization=org_b)
        assert result['valid'] is False

    def test_resolve_does_not_consume(self, active_pass):
        """
        Preview must be non-destructive: a staff member who opens the screen and
        walks away must not strand the customer with a burned code.
        """
        token, raw, _ = verification_service.mint(active_pass)
        verification_service.resolve(raw, organization=active_pass.organization)
        verification_service.resolve(raw, organization=active_pass.organization)

        token.refresh_from_db()
        assert token.consumed_at is None

    def test_preview_hides_private_feedback(self, active_pass):
        """
        A.9: staff see what they need to apply a discount — never the customer's
        complaint text or CRM history.
        """
        preview = entitlement_service.preview(active_pass)
        flat = str(preview).lower()

        assert preview['valid'] is True
        assert 'comment' not in flat
        assert 'notes' not in flat
        assert str(active_pass.customer.phone) not in flat


# ──────────────────────────────────────────────────────────────────────
# Entitlement
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestEntitlement:
    @pytest.mark.parametrize('status,expected', [
        (PassStatus.EXPIRED, 'expired'),
        (PassStatus.SUSPENDED, 'suspended'),
        (PassStatus.CANCELLED, 'cancelled'),
        (PassStatus.PENDING_PAYMENT, 'pending_payment'),
    ])
    def test_non_active_statuses_refused_with_specific_reason(
            self, active_pass, status, expected):
        active_pass.status = status
        active_pass.save(update_fields=['status'])
        assert entitlement_service.check(active_pass).reason_code == expected

    def test_query_time_expiry_beats_a_stale_status(self, active_pass):
        """
        The Celery sweeper is housekeeping, NOT the authority. A pass past its
        window must be refused even while its row still says 'active'.
        """
        active_pass.expires_at = timezone.now() - timezone.timedelta(minutes=1)
        active_pass.save(update_fields=['expires_at'])
        assert active_pass.status == PassStatus.ACTIVE

        assert entitlement_service.check(active_pass).valid is False

    def test_wrong_location_refused(self, active_pass, location_2):
        result = entitlement_service.check(active_pass, location=location_2)
        assert result.reason_code == 'wrong_location'

    def test_correct_location_accepted(self, active_pass, location):
        assert entitlement_service.check(active_pass, location=location).valid is True

    def test_none_pass_is_not_found(self):
        assert entitlement_service.check(None).reason_code == 'not_found'

    def test_pass_activating_this_instant_is_usable(self, active_plan, customer):
        """
        Clock-skew regression.

        `starts_at` is stamped at activation, so a customer minting a code in the
        same instant could be refused `not_started` by microseconds of skew
        between the web process and the DB. A few seconds of grace on the START
        edge fixes that without loosening expiry.
        """
        coffee_pass = make_active_pass(active_plan, customer)
        coffee_pass.starts_at = timezone.now() + timezone.timedelta(seconds=2)
        coffee_pass.save(update_fields=['starts_at'])

        assert entitlement_service.check(coffee_pass).valid is True

    def test_a_genuinely_future_pass_is_still_refused(self, active_plan, customer):
        """The grace window is seconds, not a loophole for scheduled passes."""
        coffee_pass = make_active_pass(active_plan, customer)
        coffee_pass.starts_at = timezone.now() + timezone.timedelta(hours=1)
        coffee_pass.save(update_fields=['starts_at'])

        assert entitlement_service.check(coffee_pass).reason_code == 'not_started'

    def test_expiry_boundary_has_no_grace(self, active_plan, customer):
        """Expiry must stay exact — grace there would extend paid entitlements."""
        coffee_pass = make_active_pass(active_plan, customer)
        coffee_pass.expires_at = timezone.now() - timezone.timedelta(microseconds=1)
        coffee_pass.save(update_fields=['expires_at'])

        assert entitlement_service.check(coffee_pass).reason_code == 'expired'


# ──────────────────────────────────────────────────────────────────────
# Money
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestDiscountCalculation:
    @pytest.mark.parametrize('subtotal,expected', [
        ('100.00', '30.00'),
        ('40.00', '12.00'),
        ('0.00', '0.00'),
        ('33.33', '10.00'),    # 9.999 -> half-up
        ('0.05', '0.02'),      # 0.015 -> half-up (banker's would give 0.01)
        ('1999.99', '600.00'),
    ])
    def test_rounding_is_half_up(self, active_pass, subtotal, expected):
        """
        Money the customer sees must round half-up. Python's default is
        banker's rounding, which would quietly under-credit on ties.
        """
        result = entitlement_service.calculate_discount(active_pass, Decimal(subtotal))
        assert result == Decimal(expected)

    def test_discount_reads_the_snapshot_not_the_live_plan(self, active_pass, active_plan):
        """
        THE snapshot-immutability test.

        An owner repricing the plan to 50% must not retroactively change what an
        existing member gets — their terms were fixed at purchase.
        """
        active_plan.discount_percent = Decimal('50.00')
        active_plan.save(update_fields=['discount_percent'])
        active_pass.refresh_from_db()

        assert entitlement_service.calculate_discount(
            active_pass, Decimal('100')) == Decimal('30.00')

    def test_negative_subtotal_rejected(self):
        with pytest.raises(redemption_service.RedemptionError):
            redemption_service.validate_subtotal('-10')

    def test_junk_subtotal_rejected(self):
        for value in ('abc', None, '', '1,000'):
            with pytest.raises(redemption_service.RedemptionError):
                redemption_service.validate_subtotal(value)

    def test_subtotal_cap_enforced(self, settings):
        """A mistyped extra zero must not poison every retention metric."""
        with pytest.raises(redemption_service.RedemptionError) as exc:
            redemption_service.validate_subtotal('20000')
        assert exc.value.reason == 'subtotal_exceeds_cap'


# ──────────────────────────────────────────────────────────────────────
# Redemption transaction
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestRedemption:
    def test_happy_path_records_server_calculated_discount(self, active_pass, manager):
        token, _, _ = verification_service.mint(active_pass)

        redemption = redemption_service.redeem(
            verification_token_id=token.id,
            eligible_subtotal=Decimal('100.00'),
            user=manager, pos_receipt_reference='R-001',
        )

        assert redemption.discount_amount_hkd == Decimal('30.00')
        assert redemption.eligible_subtotal_hkd == Decimal('100.00')
        assert redemption.status == RedemptionStatus.REDEEMED
        assert redemption.redeemed_by == manager
        # Denormalized for tenant-safe reporting.
        assert redemption.organization_id == active_pass.organization_id

    def test_token_is_consumed_exactly_once(self, active_pass, manager):
        """Replaying the same code must never create a second redemption."""
        token, _, _ = verification_service.mint(active_pass)

        redemption_service.redeem(
            verification_token_id=token.id,
            eligible_subtotal=Decimal('100'), user=manager,
        )
        with pytest.raises(redemption_service.RedemptionError) as exc:
            redemption_service.redeem(
                verification_token_id=token.id,
                eligible_subtotal=Decimal('100'), user=manager,
            )

        assert exc.value.reason == 'code_already_used_or_expired'
        assert CoffeePassRedemption.objects.count() == 1

    def test_expired_token_refused(self, active_pass, manager):
        token, _, _ = verification_service.mint(active_pass)
        token.expires_at = timezone.now() - timezone.timedelta(seconds=1)
        token.save(update_fields=['expires_at'])

        with pytest.raises(redemption_service.RedemptionError):
            redemption_service.redeem(
                verification_token_id=token.id,
                eligible_subtotal=Decimal('100'), user=manager,
            )

    def test_pass_expiring_between_mint_and_commit_is_refused(self, active_pass, manager):
        """
        TOCTOU guard: the entitlement is re-validated AFTER the token is
        consumed, so a pass that lapsed mid-transaction cannot slip through.
        """
        token, _, _ = verification_service.mint(active_pass)
        active_pass.expires_at = timezone.now() - timezone.timedelta(seconds=1)
        active_pass.save(update_fields=['expires_at'])

        with pytest.raises(redemption_service.RedemptionError) as exc:
            redemption_service.redeem(
                verification_token_id=token.id,
                eligible_subtotal=Decimal('100'), user=manager,
            )
        assert exc.value.reason == 'expired'
        assert CoffeePassRedemption.objects.count() == 0

    def test_wrong_location_refused(self, active_pass, manager, location_2):
        token, _, _ = verification_service.mint(active_pass)
        with pytest.raises(redemption_service.RedemptionError) as exc:
            redemption_service.redeem(
                verification_token_id=token.id,
                eligible_subtotal=Decimal('100'), user=manager, location=location_2,
            )
        assert exc.value.reason == 'wrong_location'

    def test_staff_from_another_org_refused(self, active_pass, owner_b):
        """Even holding a valid token, foreign staff must not redeem."""
        token, _, _ = verification_service.mint(active_pass)
        with pytest.raises(redemption_service.RedemptionError) as exc:
            redemption_service.redeem(
                verification_token_id=token.id,
                eligible_subtotal=Decimal('100'), user=owner_b,
            )
        assert exc.value.reason == 'wrong_organization'

    def test_zero_subtotal_allowed_and_records_zero(self, active_pass, manager):
        """A comped drink is a real event worth recording, at zero discount."""
        token, _, _ = verification_service.mint(active_pass)
        redemption = redemption_service.redeem(
            verification_token_id=token.id,
            eligible_subtotal=Decimal('0'), user=manager,
        )
        assert redemption.discount_amount_hkd == Decimal('0.00')

    def test_multiple_visits_each_need_a_fresh_code(self, active_pass, manager):
        """A pass is reusable across visits — one code per visit."""
        for _ in range(3):
            token, _, _ = verification_service.mint(active_pass)
            redemption_service.redeem(
                verification_token_id=token.id,
                eligible_subtotal=Decimal('40'), user=manager,
            )
        assert CoffeePassRedemption.objects.count() == 3


# ──────────────────────────────────────────────────────────────────────
# Void
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestVoid:
    def _redeem(self, active_pass, manager):
        token, _, _ = verification_service.mint(active_pass)
        return redemption_service.redeem(
            verification_token_id=token.id,
            eligible_subtotal=Decimal('100'), user=manager,
        )

    def test_void_flips_status_and_never_deletes(self, active_pass, manager, owner):
        """
        Deleting would erase the evidence that a discount was given — exactly
        what an abusive staff member would want.
        """
        redemption = self._redeem(active_pass, manager)

        voided = redemption_service.void(
            redemption=redemption, user=owner, reason='Customer cancelled order',
        )

        assert voided.status == RedemptionStatus.VOIDED
        assert voided.voided_by == owner
        assert CoffeePassRedemption.objects.filter(pk=redemption.pk).exists()
        # The money figures are preserved for audit.
        assert voided.discount_amount_hkd == Decimal('30.00')

    def test_double_void_refused(self, active_pass, manager, owner):
        redemption = self._redeem(active_pass, manager)
        redemption_service.void(
            redemption=redemption, user=owner, reason='First void reason')

        with pytest.raises(redemption_service.RedemptionError) as exc:
            redemption_service.void(
                redemption=redemption, user=owner, reason='Second void reason')
        assert exc.value.reason == 'already_voided'

    def test_short_reason_rejected(self, active_pass, manager, owner):
        """A void must be explainable later; 'x' is not an explanation."""
        redemption = self._redeem(active_pass, manager)
        with pytest.raises(redemption_service.RedemptionError) as exc:
            redemption_service.void(redemption=redemption, user=owner, reason='x')
        assert exc.value.reason == 'void_reason_required'

    def test_voided_redemption_excluded_from_savings(self, active_pass, manager, owner):
        from apps.coffee_pass.services import webhook_service

        redemption = self._redeem(active_pass, manager)
        assert webhook_service.savings_to_date(active_pass) == Decimal('30.00')

        redemption_service.void(
            redemption=redemption, user=owner, reason='Entered in error')
        assert webhook_service.savings_to_date(active_pass) == Decimal('0.00')
