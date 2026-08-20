"""
Offer decision engine — the "smart" part, made auditable.

Design rule (Appendix A.3): rules first, learning second. No ML in v1. Every
decision is an explicit object carrying a stable `reason_code`, the habit score,
and the reasons that produced it, so a decision can be explained to an owner and
tuned later without archaeology.

The scoring + break-even math here is PURE — no Django imports, no DB access, no
settings reads at module import. `decide()` is the thin Django-aware wrapper that
gathers facts and hands them to the pure core. That split is what makes the
worst-case cases (a not_good experience with a perfect routine score, a plan with
no eligible items, a zero-price item list) cheap to test exhaustively.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

# ──────────────────────────────────────────────────────────────────────
# Reason codes — STABLE. The frontend and analytics key off these strings.
# ──────────────────────────────────────────────────────────────────────
REASON_ELIGIBLE = 'eligible'
REASON_QUALITY_GATE_FAILED = 'quality_gate_failed'
REASON_ACTIVE_PASS_EXISTS = 'active_pass_exists'
REASON_LOW_EXPECTED_VALUE = 'low_expected_value'
REASON_PLAN_NOT_SELLABLE = 'plan_not_sellable'
REASON_PLAN_MISCONFIGURED = 'plan_misconfigured'
REASON_UNVERIFIED_SESSION = 'unverified_session'
REASON_CUSTOMER_BLOCKED = 'customer_blocked'
REASON_CHECKOUT_PENDING = 'checkout_pending'
REASON_NO_EXPERIENCE = 'no_experience'

#: Copy variants keyed by routine context. The OFFER ITSELF is identical for
#: everyone — discount, duration, eligibility and terms never vary. Context
#: changes wording and analytics segmentation only (no deceptive targeting).
COPY_WORK = 'work_nearby'
COPY_STUDY = 'study_nearby'
COPY_LIVE = 'live_nearby'
COPY_GENERIC = 'generic'


# ──────────────────────────────────────────────────────────────────────
# Scoring constants — tunable via settings, defaults live here so the pure
# core has no settings dependency.
# ──────────────────────────────────────────────────────────────────────
DEFAULT_SCORING = {
    'ROUTINE_NEARBY': 60,        # work / study / live nearby
    'ROUTINE_OCCASIONAL': 20,
    'PRIOR_PASS_REDEEMED': 15,   # a previous pass produced 2+ redemptions
    'PRIOR_POSITIVE_EXPERIENCE': 10,
    'PRIOR_PASS_UNUSED': -25,    # bought before, never redeemed
    'NEGATIVE_EXPERIENCE': -40,  # also a HARD block; the score is informational
    'THRESHOLD_OFFER': 40,       # >= show the normal offer
    'THRESHOLD_SOFT': 20,        # >= soft explainer, no proactive reminders
    'MAX_BREAK_EVEN_VISITS': 20, # above this the plan can't plausibly pay off
}

_NEARBY_CONTEXTS = frozenset({'work_nearby', 'study_nearby', 'live_nearby'})

_COPY_BY_CONTEXT = {
    'work_nearby': COPY_WORK,
    'study_nearby': COPY_STUDY,
    'live_nearby': COPY_LIVE,
}


# ──────────────────────────────────────────────────────────────────────
# Value objects
# ──────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class CustomerFacts:
    """Everything the engine is allowed to know. Explicitly supplied or consented."""
    sentiment: str | None = None
    routine_context: str = ''
    has_active_pass: bool = False
    has_pending_checkout: bool = False
    is_blocked: bool = False
    session_verified: bool = True
    prior_passes: int = 0
    prior_redemptions: int = 0
    prior_positive_experiences: int = 0


@dataclass(frozen=True)
class PlanFacts:
    """The plan terms being evaluated. Prices are the ACTIVE eligible menu prices."""
    is_sellable: bool = False
    price_hkd: Decimal = Decimal('0')
    discount_percent: Decimal = Decimal('0')
    duration_days: int = 30
    eligible_prices: tuple = ()
    allow_neutral_feedback: bool = False


@dataclass(frozen=True)
class BreakEven:
    """Plain-language value math shown to the customer. None when not computable."""
    average_eligible_price: Decimal | None = None
    saving_per_visit: Decimal | None = None
    break_even_visits: int | None = None

    @property
    def is_valid(self) -> bool:
        return self.break_even_visits is not None and self.break_even_visits > 0


@dataclass(frozen=True)
class OfferDecision:
    """
    The engine's output. `eligible` is the ONLY field callers may gate on; the
    rest exists to explain and to tune.
    """
    eligible: bool
    reason_code: str
    habit_score: int = 0
    reasons: tuple = ()
    break_even: BreakEven = field(default_factory=BreakEven)
    copy_variant: str = COPY_GENERIC
    soft_offer: bool = False  # score in the 20-39 band: explain, don't push

    def as_dict(self) -> dict:
        """Safe presentation payload. Contains no PII and no private comments."""
        return {
            'eligible': self.eligible,
            'reason_code': self.reason_code,
            'habit_score': self.habit_score,
            'reasons': list(self.reasons),
            'soft_offer': self.soft_offer,
            'copy_variant': self.copy_variant,
            'break_even': {
                'average_eligible_price': _money_or_none(self.break_even.average_eligible_price),
                'saving_per_visit': _money_or_none(self.break_even.saving_per_visit),
                'break_even_visits': self.break_even.break_even_visits,
            },
        }


def _money_or_none(value):
    return str(value) if value is not None else None


# ──────────────────────────────────────────────────────────────────────
# Pure core
# ──────────────────────────────────────────────────────────────────────
def calculate_break_even(price_hkd, discount_percent, eligible_prices) -> BreakEven:
    """
    break_even_visits = ceil(plan_price / (avg_eligible_price * discount%/100))

    Guards every degenerate input: no items, all-zero prices, zero discount, and
    non-numeric junk. Returns an empty BreakEven rather than raising — the caller
    treats "not computable" as "suppress the offer", never as a crash.
    """
    prices = []
    for raw in eligible_prices or ():
        try:
            value = Decimal(str(raw))
        except (InvalidOperation, TypeError, ValueError):
            continue
        if value > 0:
            prices.append(value)

    if not prices:
        return BreakEven()

    try:
        price = Decimal(str(price_hkd))
        pct = Decimal(str(discount_percent))
    except (InvalidOperation, TypeError, ValueError):
        return BreakEven()

    if price <= 0 or pct <= 0:
        return BreakEven()

    average = sum(prices) / Decimal(len(prices))
    saving = (average * pct / Decimal('100')).quantize(Decimal('0.01'))
    if saving <= 0:
        return BreakEven(average_eligible_price=average.quantize(Decimal('0.01')))

    visits = math.ceil(price / saving)
    return BreakEven(
        average_eligible_price=average.quantize(Decimal('0.01')),
        saving_per_visit=saving,
        break_even_visits=int(visits),
    )


def score_habit(customer: CustomerFacts, scoring=None) -> tuple:
    """
    Explainable additive score. Returns (score, reasons) where each reason is a
    (code, delta) pair so the UI/audit can render exactly why.
    """
    cfg = {**DEFAULT_SCORING, **(scoring or {})}
    score = 0
    reasons = []

    ctx = customer.routine_context or ''
    if ctx in _NEARBY_CONTEXTS:
        score += cfg['ROUTINE_NEARBY']
        reasons.append(('routine_nearby', cfg['ROUTINE_NEARBY']))
    elif ctx == 'occasional':
        score += cfg['ROUTINE_OCCASIONAL']
        reasons.append(('routine_occasional', cfg['ROUTINE_OCCASIONAL']))

    if customer.prior_redemptions >= 2:
        score += cfg['PRIOR_PASS_REDEEMED']
        reasons.append(('prior_pass_redeemed', cfg['PRIOR_PASS_REDEEMED']))

    if customer.prior_positive_experiences > 0:
        score += cfg['PRIOR_POSITIVE_EXPERIENCE']
        reasons.append(('prior_positive_experience', cfg['PRIOR_POSITIVE_EXPERIENCE']))

    # Bought a pass before and never used it -> selling another is poor value.
    if customer.prior_passes > 0 and customer.prior_redemptions == 0:
        score += cfg['PRIOR_PASS_UNUSED']
        reasons.append(('prior_pass_unused', cfg['PRIOR_PASS_UNUSED']))

    if customer.sentiment == 'not_good':
        score += cfg['NEGATIVE_EXPERIENCE']
        reasons.append(('negative_experience', cfg['NEGATIVE_EXPERIENCE']))

    return score, tuple(reasons)


def evaluate(customer: CustomerFacts, plan: PlanFacts, scoring=None) -> OfferDecision:
    """
    The decision. Hard gates run BEFORE scoring and short-circuit — no score,
    however high, can override a gate (asserted in tests).

    Gate order is deliberate: identity/eligibility gates first (cheapest and most
    security-relevant), then quality, then value.
    """
    cfg = {**DEFAULT_SCORING, **(scoring or {})}

    # ── Hard gates (A.3). Any true -> ineligible, no scoring. ──
    if not customer.session_verified:
        return OfferDecision(False, REASON_UNVERIFIED_SESSION)
    if customer.is_blocked:
        return OfferDecision(False, REASON_CUSTOMER_BLOCKED)
    if not plan.is_sellable:
        return OfferDecision(False, REASON_PLAN_NOT_SELLABLE)
    if customer.has_active_pass:
        return OfferDecision(False, REASON_ACTIVE_PASS_EXISTS)
    if customer.has_pending_checkout:
        return OfferDecision(False, REASON_CHECKOUT_PENDING)
    if customer.sentiment is None:
        return OfferDecision(False, REASON_NO_EXPERIENCE)

    # THE quality gate. `okay` passes only if the owner explicitly enabled it.
    if customer.sentiment == 'not_good':
        score, reasons = score_habit(customer, cfg)
        return OfferDecision(
            False, REASON_QUALITY_GATE_FAILED, habit_score=score, reasons=reasons,
        )
    if customer.sentiment == 'okay' and not plan.allow_neutral_feedback:
        return OfferDecision(False, REASON_QUALITY_GATE_FAILED)
    if customer.sentiment not in ('good', 'okay'):
        return OfferDecision(False, REASON_QUALITY_GATE_FAILED)

    # ── Value guard: a plan that can't plausibly pay off must not be sold. ──
    break_even = calculate_break_even(
        plan.price_hkd, plan.discount_percent, plan.eligible_prices,
    )
    if not break_even.is_valid:
        return OfferDecision(False, REASON_PLAN_MISCONFIGURED, break_even=break_even)
    if break_even.break_even_visits > cfg['MAX_BREAK_EVEN_VISITS']:
        return OfferDecision(False, REASON_LOW_EXPECTED_VALUE, break_even=break_even)

    # ── Scoring band ──
    score, reasons = score_habit(customer, cfg)
    copy_variant = _COPY_BY_CONTEXT.get(customer.routine_context, COPY_GENERIC)

    if score >= cfg['THRESHOLD_OFFER']:
        return OfferDecision(
            True, REASON_ELIGIBLE, habit_score=score, reasons=reasons,
            break_even=break_even, copy_variant=copy_variant, soft_offer=False,
        )
    if score >= cfg['THRESHOLD_SOFT']:
        # Still eligible to BUY — we just don't push, and never remind.
        return OfferDecision(
            True, REASON_ELIGIBLE, habit_score=score, reasons=reasons,
            break_even=break_even, copy_variant=copy_variant, soft_offer=True,
        )

    # score < 20: no proactive offer. The customer can still reach the plan from
    # the location page if the cafe chooses to show it — that's a display choice,
    # not an entitlement change.
    return OfferDecision(
        False, REASON_LOW_EXPECTED_VALUE, habit_score=score, reasons=reasons,
        break_even=break_even, copy_variant=copy_variant,
    )


# ──────────────────────────────────────────────────────────────────────
# Django-aware wrapper
# ──────────────────────────────────────────────────────────────────────
def decide(*, plan, customer, experience=None, session_verified=True, scoring=None):
    """
    Gather facts from the DB and run the pure engine.

    `experience` is the experience driving THIS offer journey. When omitted we
    fall back to the customer's latest experience at this location — a customer
    returning to the wallet shouldn't need to re-answer, but a `not_good` answer
    must still suppress the offer for that journey.
    """
    from django.conf import settings

    from ..models import (
        CoffeeExperience, CoffeePass, CoffeePassPurchase, CoffeePassRedemption,
        PassStatus, PurchaseStatus, RedemptionStatus, Sentiment,
    )

    cfg = {**DEFAULT_SCORING, **getattr(settings, 'COFFEE_PASS_SETTINGS', {}).get('SCORING', {})}
    if scoring:
        cfg.update(scoring)

    if experience is None:
        experience = (
            CoffeeExperience.objects
            .filter(customer=customer, location=plan.location)
            .order_by('-created_at')
            .first()
        )

    has_active_pass = CoffeePass.objects.filter(
        customer=customer, location=plan.location, status=PassStatus.ACTIVE,
    ).exists()

    has_pending_checkout = CoffeePassPurchase.objects.filter(
        customer=customer, plan=plan, status=PurchaseStatus.PENDING,
    ).exists()

    prior_passes = CoffeePass.objects.filter(
        customer=customer, location=plan.location,
    ).exclude(status=PassStatus.PENDING_PAYMENT).count()

    # Voided redemptions must not count as evidence the customer uses a pass.
    prior_redemptions = CoffeePassRedemption.objects.filter(
        customer=customer, location=plan.location,
        status=RedemptionStatus.REDEEMED,
    ).count()

    prior_positive = CoffeeExperience.objects.filter(
        customer=customer, location=plan.location,
        sentiment__in=[Sentiment.GOOD, Sentiment.OKAY],
    ).exclude(pk=getattr(experience, 'pk', None)).count()

    customer_facts = CustomerFacts(
        sentiment=experience.sentiment if experience else None,
        routine_context=(experience.routine_context if experience else '') or '',
        has_active_pass=has_active_pass,
        has_pending_checkout=has_pending_checkout,
        is_blocked=not customer.is_active,
        session_verified=session_verified,
        prior_passes=prior_passes,
        prior_redemptions=prior_redemptions,
        prior_positive_experiences=prior_positive,
    )

    # Only ACTIVE, in-stock items count toward the value promise the customer sees.
    eligible_prices = tuple(
        plan.eligible_items.filter(is_available=True, sold_out=False)
        .values_list('price', flat=True)
    )
    plan_facts = PlanFacts(
        is_sellable=plan.is_sellable,
        price_hkd=plan.price_hkd,
        discount_percent=plan.discount_percent,
        duration_days=plan.duration_days,
        eligible_prices=eligible_prices,
        allow_neutral_feedback=plan.allow_neutral_feedback,
    )

    return evaluate(customer_facts, plan_facts, cfg)
