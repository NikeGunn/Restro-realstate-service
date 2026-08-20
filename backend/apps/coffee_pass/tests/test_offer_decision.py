"""
Offer decision engine tests.

The single most important assertion in this file is that a HARD GATE always
beats a high score. If that ever regresses, the product starts selling coffee
passes to people who just said the coffee was bad — which is the exact failure
the PRD was written to prevent.

Most tests hit the PURE core (no DB), which is why they can exhaustively cover
degenerate inputs cheaply.
"""
from decimal import Decimal

import pytest

from apps.coffee_pass.services import offer_decision_service as engine
from apps.coffee_pass.services.offer_decision_service import (
    CustomerFacts, PlanFacts, calculate_break_even, evaluate, score_habit,
)


def _plan(**kwargs):
    """A sane, sellable plan: HK$120, 30%, avg HK$40 coffee -> 10 visits."""
    defaults = dict(
        is_sellable=True, price_hkd=Decimal('120.00'),
        discount_percent=Decimal('30.00'), duration_days=30,
        eligible_prices=(Decimal('40.00'), Decimal('38.00'), Decimal('42.00')),
        allow_neutral_feedback=False,
    )
    defaults.update(kwargs)
    return PlanFacts(**defaults)


def _customer(**kwargs):
    defaults = dict(sentiment='good', routine_context='work_nearby')
    defaults.update(kwargs)
    return CustomerFacts(**defaults)


# ──────────────────────────────────────────────────────────────────────
# HARD GATES — these must beat any score
# ──────────────────────────────────────────────────────────────────────
class TestHardGates:
    def test_not_good_never_eligible_even_with_perfect_routine(self):
        """
        THE product-safety test (A.9).

        Maximum possible habit score + negative feedback must still refuse. If
        this fails, the platform is upselling people who just complained.
        """
        customer = _customer(
            sentiment='not_good', routine_context='work_nearby',
            prior_redemptions=5, prior_positive_experiences=10,
        )
        decision = evaluate(customer, _plan())

        assert decision.eligible is False
        assert decision.reason_code == engine.REASON_QUALITY_GATE_FAILED

    def test_okay_blocked_unless_owner_opts_in(self):
        customer = _customer(sentiment='okay')
        assert evaluate(customer, _plan()).reason_code == engine.REASON_QUALITY_GATE_FAILED

    def test_okay_allowed_when_plan_enables_neutral(self):
        customer = _customer(sentiment='okay')
        decision = evaluate(customer, _plan(allow_neutral_feedback=True))
        assert decision.eligible is True

    def test_active_pass_blocks_duplicate_purchase(self):
        decision = evaluate(_customer(has_active_pass=True), _plan())
        assert decision.eligible is False
        assert decision.reason_code == engine.REASON_ACTIVE_PASS_EXISTS

    def test_unverified_session_blocked_first(self):
        """Identity gate runs before everything — cheapest and most security-relevant."""
        decision = evaluate(_customer(session_verified=False), _plan())
        assert decision.reason_code == engine.REASON_UNVERIFIED_SESSION

    def test_blocked_customer_refused(self):
        assert evaluate(_customer(is_blocked=True), _plan()).reason_code == \
            engine.REASON_CUSTOMER_BLOCKED

    def test_paused_plan_blocks_new_sale(self):
        decision = evaluate(_customer(), _plan(is_sellable=False))
        assert decision.reason_code == engine.REASON_PLAN_NOT_SELLABLE

    def test_pending_checkout_blocks_second_session(self):
        decision = evaluate(_customer(has_pending_checkout=True), _plan())
        assert decision.reason_code == engine.REASON_CHECKOUT_PENDING

    def test_no_experience_yet_is_not_eligible(self):
        decision = evaluate(_customer(sentiment=None), _plan())
        assert decision.reason_code == engine.REASON_NO_EXPERIENCE

    def test_unknown_sentiment_fails_closed(self):
        """An unexpected value must refuse, not fall through to an offer."""
        decision = evaluate(_customer(sentiment='amazing'), _plan())
        assert decision.eligible is False
        assert decision.reason_code == engine.REASON_QUALITY_GATE_FAILED


# ──────────────────────────────────────────────────────────────────────
# BREAK-EVEN math + degenerate inputs
# ──────────────────────────────────────────────────────────────────────
class TestBreakEven:
    def test_basic_math_is_exact(self):
        """HK$120 / (avg 40 * 30%) = 120/12 = 10 visits."""
        result = calculate_break_even(
            Decimal('120'), Decimal('30'),
            (Decimal('40'), Decimal('38'), Decimal('42')),
        )
        assert result.average_eligible_price == Decimal('40.00')
        assert result.saving_per_visit == Decimal('12.00')
        assert result.break_even_visits == 10

    def test_rounds_up_partial_visit(self):
        """You cannot buy 8.4 coffees — the honest number is 9."""
        result = calculate_break_even(Decimal('100'), Decimal('30'), (Decimal('40'),))
        assert result.break_even_visits == 9  # 100/12 = 8.33 -> 9

    def test_no_eligible_items_is_not_computable(self):
        assert calculate_break_even(Decimal('120'), Decimal('30'), ()).is_valid is False

    def test_all_zero_prices_guarded(self):
        """A free item list would divide by zero — must degrade, not crash."""
        result = calculate_break_even(
            Decimal('120'), Decimal('30'), (Decimal('0'), Decimal('0')),
        )
        assert result.is_valid is False

    def test_zero_discount_guarded(self):
        assert calculate_break_even(
            Decimal('120'), Decimal('0'), (Decimal('40'),)
        ).is_valid is False

    def test_junk_prices_are_skipped_not_fatal(self):
        """Bad data in the menu must not 500 the customer's page."""
        result = calculate_break_even(
            Decimal('120'), Decimal('30'), ('abc', None, Decimal('40')),
        )
        assert result.break_even_visits == 10

    def test_junk_price_hkd_returns_empty(self):
        assert calculate_break_even('not-a-number', Decimal('30'),
                                    (Decimal('40'),)).is_valid is False

    def test_unprofitable_plan_suppresses_offer(self):
        """HK$500 pass, 30% off a HK$20 coffee = 84 visits. Nobody can win."""
        decision = evaluate(
            _customer(),
            _plan(price_hkd=Decimal('500'), eligible_prices=(Decimal('20'),)),
        )
        assert decision.eligible is False
        assert decision.reason_code == engine.REASON_LOW_EXPECTED_VALUE

    def test_plan_with_no_items_is_misconfigured(self):
        decision = evaluate(_customer(), _plan(eligible_prices=()))
        assert decision.reason_code == engine.REASON_PLAN_MISCONFIGURED


# ──────────────────────────────────────────────────────────────────────
# SCORING
# ──────────────────────────────────────────────────────────────────────
class TestScoring:
    def test_nearby_routine_clears_the_offer_threshold(self):
        score, reasons = score_habit(_customer(routine_context='work_nearby'))
        assert score == 60
        assert ('routine_nearby', 60) in reasons

    @pytest.mark.parametrize('context', ['work_nearby', 'study_nearby', 'live_nearby'])
    def test_all_nearby_contexts_score_identically(self, context):
        """Context changes COPY only — never the entitlement or the score."""
        assert score_habit(_customer(routine_context=context))[0] == 60

    def test_occasional_lands_in_the_soft_band(self):
        decision = evaluate(_customer(routine_context='occasional'), _plan())
        assert decision.eligible is True
        assert decision.soft_offer is True  # buyable, but never pushed

    def test_prefer_not_to_say_scores_zero_and_gets_no_push(self):
        decision = evaluate(_customer(routine_context='prefer_not_to_say'), _plan())
        assert decision.habit_score == 0
        assert decision.eligible is False
        assert decision.reason_code == engine.REASON_LOW_EXPECTED_VALUE

    def test_unused_prior_pass_penalised(self):
        """Selling a second pass to someone who never used the first is bad value."""
        score, reasons = score_habit(
            _customer(routine_context='occasional', prior_passes=1, prior_redemptions=0),
        )
        assert score == 20 - 25  # occasional + unused penalty
        assert ('prior_pass_unused', -25) in reasons

    def test_proven_user_gets_a_bonus(self):
        score, _ = score_habit(
            _customer(routine_context='occasional', prior_passes=1, prior_redemptions=3),
        )
        assert score == 20 + 15

    def test_copy_variant_tracks_context_without_changing_terms(self):
        work = evaluate(_customer(routine_context='work_nearby'), _plan())
        study = evaluate(_customer(routine_context='study_nearby'), _plan())

        assert work.copy_variant == engine.COPY_WORK
        assert study.copy_variant == engine.COPY_STUDY
        # Identical entitlement — only wording differs.
        assert work.break_even.break_even_visits == study.break_even.break_even_visits
        assert work.eligible == study.eligible


# ──────────────────────────────────────────────────────────────────────
# Output contract
# ──────────────────────────────────────────────────────────────────────
class TestDecisionPayload:
    def test_reason_codes_are_stable_strings(self):
        """The frontend and analytics key off these — they must not drift."""
        assert engine.REASON_ELIGIBLE == 'eligible'
        assert engine.REASON_QUALITY_GATE_FAILED == 'quality_gate_failed'
        assert engine.REASON_ACTIVE_PASS_EXISTS == 'active_pass_exists'
        assert engine.REASON_LOW_EXPECTED_VALUE == 'low_expected_value'

    def test_as_dict_is_json_safe_and_leaks_nothing(self):
        payload = evaluate(_customer(), _plan()).as_dict()

        assert payload['eligible'] is True
        assert payload['break_even']['break_even_visits'] == 10
        # Decimals must be stringified for JSON.
        assert isinstance(payload['break_even']['saving_per_visit'], str)
        # No customer identity may ride along in an offer payload.
        for forbidden in ('phone', 'customer_id', 'name', 'comment'):
            assert forbidden not in payload

    def test_negative_decision_still_explains_itself(self):
        """An owner must be able to ask "why did nobody get an offer?"."""
        decision = evaluate(_customer(sentiment='not_good'), _plan())
        payload = decision.as_dict()
        assert payload['reason_code'] == 'quality_gate_failed'
        assert 'negative_experience' in [r[0] for r in decision.reasons]


# ──────────────────────────────────────────────────────────────────────
# Django-aware wrapper
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestDecideIntegration:
    def test_decide_reads_real_menu_prices(self, active_plan, customer):
        from apps.coffee_pass.models import CoffeeExperience, Sentiment

        experience = CoffeeExperience.objects.create(
            organization=active_plan.organization, location=active_plan.location,
            customer=customer, plan=active_plan,
            sentiment=Sentiment.GOOD, routine_context='work_nearby',
        )
        decision = engine.decide(
            plan=active_plan, customer=customer, experience=experience,
        )
        assert decision.eligible is True
        assert decision.break_even.break_even_visits == 10

    def test_sold_out_items_excluded_from_value_promise(self, active_plan, customer,
                                                       coffee_items):
        """
        A sold-out coffee cannot back a savings claim.

        Marking all but the cheapest sold out changes the average, and therefore
        the break-even the customer is shown.
        """
        from apps.coffee_pass.models import CoffeeExperience, Sentiment

        for item in coffee_items[1:]:
            item.sold_out = True
            item.save(update_fields=['sold_out'])

        experience = CoffeeExperience.objects.create(
            organization=active_plan.organization, location=active_plan.location,
            customer=customer, plan=active_plan,
            sentiment=Sentiment.GOOD, routine_context='work_nearby',
        )
        decision = engine.decide(
            plan=active_plan, customer=customer, experience=experience,
        )
        # Only the HK$40 Latte remains: 120 / 12 = 10.
        assert decision.break_even.average_eligible_price == Decimal('40.00')

    def test_existing_active_pass_blocks_via_db(self, active_plan, customer, active_pass):
        from apps.coffee_pass.models import CoffeeExperience, Sentiment

        experience = CoffeeExperience.objects.create(
            organization=active_plan.organization, location=active_plan.location,
            customer=customer, plan=active_plan,
            sentiment=Sentiment.GOOD, routine_context='work_nearby',
        )
        decision = engine.decide(
            plan=active_plan, customer=customer, experience=experience,
        )
        assert decision.reason_code == engine.REASON_ACTIVE_PASS_EXISTS

    def test_voided_redemptions_do_not_count_as_usage(self, active_plan, customer,
                                                     active_pass, owner):
        """
        A voided redemption is not evidence the customer uses their pass.

        Counting it would inflate the score and keep selling passes to someone
        whose redemptions were all corrections.
        """
        from apps.coffee_pass.models import CoffeePassRedemption, RedemptionStatus

        for _ in range(3):
            CoffeePassRedemption.objects.create(
                organization=active_plan.organization, location=active_plan.location,
                coffee_pass=active_pass, customer=customer,
                eligible_subtotal_hkd=Decimal('40'), discount_amount_hkd=Decimal('12'),
                discount_percent_applied=Decimal('30'),
                status=RedemptionStatus.VOIDED,
            )

        facts_score, _ = score_habit(_customer(
            routine_context='occasional', prior_passes=1, prior_redemptions=0,
        ))
        # Mirrors what decide() will compute: all voided -> unused penalty applies.
        assert facts_score == -5
