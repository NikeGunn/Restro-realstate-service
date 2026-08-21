"""
Plan lifecycle — validate, activate, pause.

The interesting rule is the break-even guard (A.6): an owner can misconfigure a
plan into something no customer can plausibly benefit from (HK$500 pass, 30% off
a HK$20 coffee = 84 visits in 30 days). Rather than silently selling it, we
block activation and make the owner acknowledge the number explicitly.

Pausing NEVER touches sold passes. That separation — "stop new sales" vs "revoke
entitlement" — is the whole reason plan terms are snapshotted at purchase.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from ..models import CoffeePassAuditEvent, PlanStatus
from . import audit_service
from .offer_decision_service import DEFAULT_SCORING, calculate_break_even

logger = logging.getLogger(__name__)


def _cfg(key, default):
    return getattr(settings, 'COFFEE_PASS_SETTINGS', {}).get(key, default)


def _max_break_even():
    scoring = getattr(settings, 'COFFEE_PASS_SETTINGS', {}).get('SCORING', {})
    return scoring.get('MAX_BREAK_EVEN_VISITS', DEFAULT_SCORING['MAX_BREAK_EVEN_VISITS'])


#: Fallback when settings carry no override. `coffee` is the intended type;
#: `drink` is tolerated for menus built before the coffee type existed. FOOD IS
#: DELIBERATELY ABSENT — a pass that discounts a rice platter is not the product,
#: and that is exactly the bug this rule exists to prevent.
DEFAULT_ELIGIBLE_ITEM_TYPES = ('coffee', 'drink')


def eligible_item_types() -> frozenset:
    """
    THE definition of "what a Coffee Pass may discount" — one function used by
    the write validators, the dashboard picker endpoint, and the tests, so those
    can never disagree.

    Driven by COFFEE_PASS_SETTINGS['ELIGIBLE_ITEM_TYPES'] (env
    COFFEE_PASS_ELIGIBLE_ITEM_TYPES), so widening eligibility later — e.g. a
    promo where a pass also covers a pastry — is a configmap edit rather than a
    code change. Read at call time, never cached at import, so a settings
    override in a test or a restarted pod takes effect immediately.
    """
    configured = getattr(settings, 'COFFEE_PASS_SETTINGS', {}).get(
        'ELIGIBLE_ITEM_TYPES'
    )
    # An empty/blank override would silently make every item ineligible and
    # brick plan creation, so treat it as "unset" and fall back to the default.
    return frozenset(configured or DEFAULT_ELIGIBLE_ITEM_TYPES)


def eligible_item_queryset(organization_id):
    """
    Every menu item in an org that a Coffee Pass plan is allowed to cover.

    Used by the API so the dashboard picker and the activation guard can never
    disagree about what counts as coffee.
    """
    from apps.restaurant.models import MenuItem

    return (
        MenuItem.objects
        .filter(
            category__organization_id=organization_id,
            item_type__in=eligible_item_types(),
        )
        .order_by('name')
    )


def validate_tenancy(plan) -> None:
    """
    A plan must be internally consistent before it can exist:
      - its location belongs to its organization;
      - every eligible MenuItem belongs to that same organization.

    MenuItem has no `organization` column — it is reached through
    `category.organization` (Phase 3 convention), so we check that path.
    """
    if plan.location.organization_id != plan.organization_id:
        raise ValidationError({'location': 'Location does not belong to this organization.'})

    if plan.pk:
        foreign = plan.eligible_items.exclude(
            category__organization_id=plan.organization_id,
        ).exists()
        if foreign:
            raise ValidationError(
                {'eligible_items': 'All eligible items must belong to this organization.'}
            )

        # A Coffee Pass may only ever discount coffee. Enforced HERE rather than
        # only in the dashboard picker, because a filter in the UI is a
        # convenience and this is an invariant: it must hold for the API, the
        # admin, a script, and a stale browser tab alike.
        non_coffee = list(
            plan.eligible_items
            .exclude(item_type__in=eligible_item_types())
            .values_list('name', flat=True)[:5]
        )
        if non_coffee:
            raise ValidationError({
                'eligible_items': (
                    'A Coffee Pass can only cover coffee items. Change the item '
                    'type to Coffee on the menu, or remove: '
                    + ', '.join(non_coffee)
                )
            })


def compute_break_even(plan):
    """Break-even over the plan's CURRENTLY available eligible items."""
    prices = tuple(
        plan.eligible_items.filter(is_available=True, sold_out=False)
        .values_list('price', flat=True)
    )
    return calculate_break_even(plan.price_hkd, plan.discount_percent, prices)


def check_activation_readiness(plan) -> dict:
    """
    Dry-run the activation rules. Returns {ready, errors[], warnings[], break_even}.

    Powers the owner's "preview before activate" UI, and activate() calls the
    same function — one implementation, so preview can never disagree with what
    actually happens.
    """
    errors, warnings = [], []

    if plan.price_hkd is None or plan.price_hkd <= 0:
        errors.append('price_must_be_positive')
    if not plan.duration_days or plan.duration_days <= 0:
        errors.append('duration_must_be_positive')
    if not (0 < plan.discount_percent <= 50):
        errors.append('discount_out_of_range')
    if not plan.eligible_items.exists():
        errors.append('eligible_items_required')

    break_even = compute_break_even(plan)
    if not break_even.is_valid:
        # No purchasable eligible item -> the value promise cannot be stated.
        errors.append('no_available_eligible_items')
    elif break_even.break_even_visits > _max_break_even():
        # A guardrail, not a hard block: the owner may knowingly proceed.
        if plan.break_even_acknowledged:
            warnings.append('break_even_high_acknowledged')
        else:
            errors.append('break_even_too_high')

    return {
        'ready': not errors,
        'errors': errors,
        'warnings': warnings,
        'break_even': {
            'average_eligible_price': (
                str(break_even.average_eligible_price)
                if break_even.average_eligible_price is not None else None
            ),
            'saving_per_visit': (
                str(break_even.saving_per_visit)
                if break_even.saving_per_visit is not None else None
            ),
            'break_even_visits': break_even.break_even_visits,
            'max_recommended_visits': _max_break_even(),
        },
    }


class PlanTransitionError(Exception):
    """Raised with a stable reason code plus the readiness detail for the UI."""

    def __init__(self, reason, detail=None):
        self.reason = reason
        self.detail = detail or {}
        super().__init__(reason)


@transaction.atomic
def activate(plan, *, user=None, correlation_id=''):
    """Validate then flip to ACTIVE. Idempotent — activating an active plan is a no-op."""
    if plan.status == PlanStatus.ACTIVE:
        return plan

    if plan.status == PlanStatus.ARCHIVED:
        raise PlanTransitionError('cannot_activate_archived')

    readiness = check_activation_readiness(plan)
    if not readiness['ready']:
        raise PlanTransitionError('activation_requirements_not_met', readiness)

    plan.status = PlanStatus.ACTIVE
    plan.save(update_fields=['status', 'updated_at'])

    audit_service.record(
        organization=plan.organization, location=plan.location,
        action=CoffeePassAuditEvent.Action.PLAN_ACTIVATED,
        entity=plan, actor=user, correlation_id=correlation_id,
        metadata={'break_even': readiness['break_even']},
    )
    return plan


@transaction.atomic
def pause(plan, *, user=None, correlation_id=''):
    """
    Stop NEW sales. Existing passes stay fully valid and redeemable — that is the
    contract we sold, and a plan edit can never claw it back.
    """
    if plan.status == PlanStatus.PAUSED:
        return plan
    if plan.status != PlanStatus.ACTIVE:
        raise PlanTransitionError('only_active_plans_can_pause')

    plan.status = PlanStatus.PAUSED
    plan.save(update_fields=['status', 'updated_at'])

    audit_service.record(
        organization=plan.organization, location=plan.location,
        action=CoffeePassAuditEvent.Action.PLAN_PAUSED,
        entity=plan, actor=user, correlation_id=correlation_id,
        metadata={'note': 'existing passes remain valid'},
    )
    return plan


def public_offer_payload(plan) -> dict:
    """
    What the PUBLIC location page may see before any customer is verified.

    Deliberately minimal: enough to decide whether to start, and nothing that
    identifies a customer or exposes internal configuration.
    """
    break_even = compute_break_even(plan)
    return {
        'plan_id': str(plan.id),
        'name': plan.name,
        'description': plan.description,
        'price_hkd': str(plan.price_hkd),
        'currency': plan.currency,
        'discount_percent': str(plan.discount_percent),
        'duration_days': plan.duration_days,
        'is_sellable': plan.is_sellable,
        'allow_neutral_feedback': plan.allow_neutral_feedback,
        'location_name': plan.location.name,
        'organization_name': plan.organization.name,
        'eligible_item_names': list(
            plan.eligible_items.filter(is_available=True, sold_out=False)
            .values_list('name', flat=True)[:20]
        ),
        'break_even_visits': break_even.break_even_visits,
        'average_eligible_price': (
            str(break_even.average_eligible_price)
            if break_even.average_eligible_price is not None else None
        ),
    }
