"""
Authenticated API tests — the owner/manager/outsider/cross-org matrix.

Tenancy is the property most likely to break silently during a refactor, and
the most damaging when it does, so every resource is probed from a neighbouring
tenant. Cross-org reads must 404 (not 403) — a 403 confirms the row exists.
"""
from decimal import Decimal

import pytest

from apps.coffee_pass.models import (
    CoffeePassPlan, CoffeePassRedemption, PassStatus, PlanStatus, RedemptionStatus,
)
from apps.coffee_pass.services import redemption_service, verification_service

PLANS = '/api/v1/coffee-pass/plans/'
PASSES = '/api/v1/coffee-pass/passes/'
RESOLVE = '/api/v1/coffee-pass/verification/resolve/'
REDEEM = '/api/v1/coffee-pass/redemptions/create/'
SUMMARY = '/api/v1/coffee-pass/analytics/summary/'


# ──────────────────────────────────────────────────────────────────────
# Plans
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestPlanAPI:
    def _payload(self, org, location, items):
        return {
            'organization': str(org.id), 'location': str(location.id),
            'name': 'Coffee Pass — 30 days', 'price_hkd': '120.00',
            'discount_percent': '30.00', 'duration_days': 30,
            'eligible_items': [str(i.id) for i in items],
        }

    def test_owner_creates_a_draft_plan(self, owner_api, org, location, coffee_items):
        response = owner_api.post(
            PLANS, self._payload(org, location, coffee_items), format='json')

        assert response.status_code == 201
        assert response.data['status'] == PlanStatus.DRAFT
        # The opaque QR token is generated server-side.
        assert len(response.data['public_token']) == 32

    def test_manager_can_read_but_not_create(self, manager_api, org, location,
                                             coffee_items, draft_plan):
        assert manager_api.get(PLANS).status_code == 200
        assert manager_api.post(
            PLANS, self._payload(org, location, coffee_items), format='json',
        ).status_code == 403

    def test_outsider_sees_nothing(self, outsider_api):
        response = outsider_api.get(PLANS)
        # No membership -> 403 from IsOrgMember (matches inventory/CRM convention).
        assert response.status_code == 403

    def test_cross_org_plan_is_404_not_403(self, owner_b_api, draft_plan):
        """A 403 would confirm the row exists. Cross-tenant lookups must 404."""
        assert owner_b_api.get(f'{PLANS}{draft_plan.id}/').status_code == 404

    def test_cross_org_list_is_isolated(self, owner_b_api, draft_plan, plan_b):
        response = owner_b_api.get(PLANS)
        returned = {row['id'] for row in response.data['results']}
        assert str(plan_b.id) in returned
        assert str(draft_plan.id) not in returned

    def test_foreign_menu_item_rejected(self, owner_api, org, location, foreign_item):
        """An owner must not attach another tenant's menu item to their plan."""
        response = owner_api.post(
            PLANS, self._payload(org, location, [foreign_item]), format='json')

        assert response.status_code == 400
        assert 'eligible_items' in response.data

    def test_location_from_another_org_rejected(self, owner_api, org, location_b,
                                                coffee_items):
        response = owner_api.post(
            PLANS, self._payload(org, location_b, coffee_items), format='json')
        assert response.status_code == 400

    @pytest.mark.parametrize('field,value', [
        ('price_hkd', '0.00'),
        ('discount_percent', '80.00'),   # above the 50% ceiling
        ('discount_percent', '0.00'),
        ('duration_days', 0),
    ])
    def test_invalid_terms_rejected(self, owner_api, org, location, coffee_items,
                                    field, value):
        payload = self._payload(org, location, coffee_items)
        payload[field] = value
        assert owner_api.post(PLANS, payload, format='json').status_code == 400


@pytest.mark.django_db
class TestPlanLifecycle:
    def test_activation_preview_reports_break_even(self, owner_api, draft_plan):
        response = owner_api.get(f'{PLANS}{draft_plan.id}/activation-preview/')

        assert response.status_code == 200
        assert response.data['ready'] is True
        assert response.data['break_even']['break_even_visits'] == 10

    def test_owner_activates_a_valid_plan(self, owner_api, draft_plan):
        response = owner_api.post(f'{PLANS}{draft_plan.id}/activate/')

        assert response.status_code == 200
        draft_plan.refresh_from_db()
        assert draft_plan.status == PlanStatus.ACTIVE

    def test_cannot_activate_without_eligible_items(self, owner_api, draft_plan):
        """PRD §14: at least one eligible item is required before activation."""
        draft_plan.eligible_items.clear()
        response = owner_api.post(f'{PLANS}{draft_plan.id}/activate/')

        assert response.status_code == 400
        assert 'eligible_items_required' in response.data['errors']

    def test_cannot_activate_an_unprofitable_plan(self, owner_api, draft_plan):
        """The break-even guardrail blocks a plan no customer could benefit from."""
        draft_plan.price_hkd = Decimal('900.00')
        draft_plan.save(update_fields=['price_hkd'])

        response = owner_api.post(f'{PLANS}{draft_plan.id}/activate/')

        assert response.status_code == 400
        assert 'break_even_too_high' in response.data['errors']

    def test_owner_may_acknowledge_and_proceed(self, owner_api, draft_plan):
        """A guardrail, not a prohibition — the owner can knowingly accept it."""
        draft_plan.price_hkd = Decimal('900.00')
        draft_plan.break_even_acknowledged = True
        draft_plan.save(update_fields=['price_hkd', 'break_even_acknowledged'])

        assert owner_api.post(f'{PLANS}{draft_plan.id}/activate/').status_code == 200

    def test_manager_cannot_activate(self, manager_api, draft_plan):
        assert manager_api.post(f'{PLANS}{draft_plan.id}/activate/').status_code == 403

    def test_pausing_blocks_sales_but_keeps_passes_valid(self, owner_api, active_plan,
                                                        active_pass):
        """
        THE pause contract (PRD §14): stop new sales, honor sold entitlements.
        """
        from apps.coffee_pass.services import entitlement_service

        assert owner_api.post(f'{PLANS}{active_plan.id}/pause/').status_code == 200

        active_plan.refresh_from_db()
        assert active_plan.is_sellable is False
        # The already-sold pass is untouched.
        active_pass.refresh_from_db()
        assert entitlement_service.check(active_pass).valid is True

    def test_status_cannot_be_changed_by_a_plain_patch(self, owner_api, draft_plan):
        """
        A direct PATCH must not bypass the activation guard — otherwise the
        break-even check is trivially skippable.
        """
        response = owner_api.patch(
            f'{PLANS}{draft_plan.id}/', {'status': 'active'}, format='json')

        assert response.status_code == 200
        draft_plan.refresh_from_db()
        assert draft_plan.status == PlanStatus.DRAFT  # unchanged


# ──────────────────────────────────────────────────────────────────────
# Till operations
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestTillOperations:
    def test_manager_can_resolve_a_code(self, manager_api, active_pass, org):
        """Managers must be able to work the till — that is their whole job."""
        _, raw, _ = verification_service.mint(active_pass)

        response = manager_api.post(
            RESOLVE, {'code': raw, 'organization': str(org.id)}, format='json')

        assert response.status_code == 200
        assert response.data['valid'] is True
        assert 'verification_token_id' in response.data

    def test_resolve_never_exposes_private_feedback(self, manager_api, active_pass,
                                                   org, negative_experience):
        """
        A.9: the staff endpoint must not leak the customer's complaint text,
        even though a negative experience exists on file.
        """
        _, raw, _ = verification_service.mint(active_pass)

        response = manager_api.post(
            RESOLVE, {'code': raw, 'organization': str(org.id)}, format='json')

        body = str(response.data).lower()
        assert 'cold and bitter' not in body
        assert 'comment' not in body

    def test_invalid_code_returns_200_with_a_reason(self, manager_api, org):
        """
        An expired code at a busy till is normal, not exceptional — the UI wants
        a reason code, not an error page.
        """
        response = manager_api.post(
            RESOLVE, {'code': 'nonsense', 'organization': str(org.id)}, format='json')

        assert response.status_code == 200
        assert response.data['valid'] is False
        assert response.data['reason_code'] == 'invalid_or_expired_code'

    def test_foreign_staff_cannot_resolve_our_code(self, owner_b_api, active_pass, org_b):
        _, raw, _ = verification_service.mint(active_pass)
        response = owner_b_api.post(
            RESOLVE, {'code': raw, 'organization': str(org_b.id)}, format='json')
        assert response.data['valid'] is False

    def test_manager_creates_a_redemption(self, manager_api, active_pass, org):
        token, _, _ = verification_service.mint(active_pass)

        response = manager_api.post(REDEEM, {
            'verification_token_id': str(token.id),
            'eligible_subtotal_hkd': '100.00',
            'pos_receipt_reference': 'R-42',
            'organization': str(org.id),
        }, format='json')

        assert response.status_code == 201
        # Server-calculated, never client-supplied.
        assert response.data['discount_amount_hkd'] == '30.00'

    def test_client_cannot_dictate_the_discount(self, manager_api, active_pass, org):
        """A malicious till client sending its own discount must be ignored."""
        token, _, _ = verification_service.mint(active_pass)

        response = manager_api.post(REDEEM, {
            'verification_token_id': str(token.id),
            'eligible_subtotal_hkd': '100.00',
            'discount_amount_hkd': '99.99',   # attacker-supplied
            'organization': str(org.id),
        }, format='json')

        assert response.status_code == 201
        assert response.data['discount_amount_hkd'] == '30.00'

    def test_replayed_code_returns_409(self, manager_api, active_pass, org):
        token, _, _ = verification_service.mint(active_pass)
        payload = {
            'verification_token_id': str(token.id),
            'eligible_subtotal_hkd': '100.00', 'organization': str(org.id),
        }
        assert manager_api.post(REDEEM, payload, format='json').status_code == 201
        assert manager_api.post(REDEEM, payload, format='json').status_code == 409

    def test_subtotal_over_cap_rejected(self, manager_api, active_pass, org):
        token, _, _ = verification_service.mint(active_pass)
        response = manager_api.post(REDEEM, {
            'verification_token_id': str(token.id),
            'eligible_subtotal_hkd': '50000.00', 'organization': str(org.id),
        }, format='json')

        assert response.status_code == 400
        assert response.data['detail'] == 'subtotal_exceeds_cap'

    def test_outsider_cannot_redeem(self, outsider_api, active_pass):
        token, _, _ = verification_service.mint(active_pass)
        response = outsider_api.post(REDEEM, {
            'verification_token_id': str(token.id),
            'eligible_subtotal_hkd': '100.00',
        }, format='json')
        assert response.status_code == 403

    def test_unauthenticated_rejected(self, api, active_pass):
        token, _, _ = verification_service.mint(active_pass)
        response = api.post(REDEEM, {
            'verification_token_id': str(token.id),
            'eligible_subtotal_hkd': '100.00',
        }, format='json')
        assert response.status_code in (401, 403)


# ──────────────────────────────────────────────────────────────────────
# Passes + void
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestPassAPI:
    def test_manager_lists_passes(self, manager_api, active_pass):
        response = manager_api.get(PASSES)
        assert response.status_code == 200
        assert response.data['count'] == 1

    def test_cross_org_pass_is_404(self, owner_b_api, active_pass):
        assert owner_b_api.get(f'{PASSES}{active_pass.id}/').status_code == 404

    def test_owner_suspends_and_restores(self, owner_api, active_pass):
        suspend = owner_api.post(
            f'{PASSES}{active_pass.id}/suspend/',
            {'reason': 'Suspected card fraud'}, format='json')
        assert suspend.status_code == 200
        active_pass.refresh_from_db()
        assert active_pass.status == PassStatus.SUSPENDED

        restore = owner_api.post(f'{PASSES}{active_pass.id}/restore/')
        assert restore.status_code == 200
        active_pass.refresh_from_db()
        assert active_pass.status == PassStatus.ACTIVE

    def test_manager_cannot_suspend(self, manager_api, active_pass):
        response = manager_api.post(
            f'{PASSES}{active_pass.id}/suspend/',
            {'reason': 'Trying it on'}, format='json')
        assert response.status_code == 403

    def test_suspended_pass_cannot_redeem(self, owner_api, manager_api, active_pass, org):
        """The operational consequence of a suspension."""
        token, _, _ = verification_service.mint(active_pass)
        owner_api.post(f'{PASSES}{active_pass.id}/suspend/',
                       {'reason': 'Under review'}, format='json')

        response = manager_api.post(REDEEM, {
            'verification_token_id': str(token.id),
            'eligible_subtotal_hkd': '100.00', 'organization': str(org.id),
        }, format='json')

        assert response.status_code == 403
        assert response.data['detail'] == 'suspended'


@pytest.mark.django_db
class TestVoidAPI:
    def _redeem(self, active_pass, manager):
        token, _, _ = verification_service.mint(active_pass)
        return redemption_service.redeem(
            verification_token_id=token.id,
            eligible_subtotal=Decimal('100'), user=manager,
        )

    def test_owner_voids_with_a_reason(self, owner_api, active_pass, manager):
        redemption = self._redeem(active_pass, manager)

        response = owner_api.post(
            f'/api/v1/coffee-pass/redemptions/{redemption.id}/void/',
            {'reason': 'Customer cancelled the order'}, format='json')

        assert response.status_code == 200
        redemption.refresh_from_db()
        assert redemption.status == RedemptionStatus.VOIDED
        # Never deleted — the audit trail survives.
        assert CoffeePassRedemption.objects.filter(pk=redemption.pk).exists()

    def test_manager_cannot_void(self, manager_api, active_pass, manager):
        """Voiding is the abuse-prone action, so it is owner-only."""
        redemption = self._redeem(active_pass, manager)
        response = manager_api.post(
            f'/api/v1/coffee-pass/redemptions/{redemption.id}/void/',
            {'reason': 'Trying to hide this'}, format='json')
        assert response.status_code == 403

    def test_void_requires_a_meaningful_reason(self, owner_api, active_pass, manager):
        redemption = self._redeem(active_pass, manager)
        response = owner_api.post(
            f'/api/v1/coffee-pass/redemptions/{redemption.id}/void/',
            {'reason': 'x'}, format='json')
        assert response.status_code == 400

    def test_double_void_returns_409(self, owner_api, active_pass, manager):
        redemption = self._redeem(active_pass, manager)
        url = f'/api/v1/coffee-pass/redemptions/{redemption.id}/void/'
        payload = {'reason': 'Entered in error'}

        assert owner_api.post(url, payload, format='json').status_code == 200
        assert owner_api.post(url, payload, format='json').status_code == 409


# ──────────────────────────────────────────────────────────────────────
# Analytics
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestAnalyticsAPI:
    def test_summary_reconciles_with_fixture_rows(self, owner_api, active_pass,
                                                  manager, org):
        """
        PRD §14: analytics must reconcile to persisted records, not event counts.
        Two redemptions of HK$100 at 30% = HK$60 total discount.
        """
        for _ in range(2):
            token, _, _ = verification_service.mint(active_pass)
            redemption_service.redeem(
                verification_token_id=token.id,
                eligible_subtotal=Decimal('100'), user=manager,
            )

        response = owner_api.get(f'{SUMMARY}?organization={org.id}')

        assert response.status_code == 200
        assert response.data['redemptions']['count'] == 2
        assert response.data['redemptions']['total_discount_hkd'] == '60.00'
        assert response.data['passes']['active'] == 1

    def test_voided_redemptions_excluded_from_totals(self, owner_api, active_pass,
                                                    manager, owner, org):
        token, _, _ = verification_service.mint(active_pass)
        redemption = redemption_service.redeem(
            verification_token_id=token.id,
            eligible_subtotal=Decimal('100'), user=manager,
        )
        redemption_service.void(
            redemption=redemption, user=owner, reason='Entered in error')

        response = owner_api.get(f'{SUMMARY}?organization={org.id}')

        assert response.data['redemptions']['count'] == 0
        assert response.data['redemptions']['voided_count'] == 1
        assert response.data['redemptions']['total_discount_hkd'] == '0.00'

    def test_missing_receipt_references_are_flagged(self, owner_api, active_pass,
                                                   manager, org):
        """The dashboard highlights redemptions a POS receipt can't back up."""
        token, _, _ = verification_service.mint(active_pass)
        redemption_service.redeem(
            verification_token_id=token.id,
            eligible_subtotal=Decimal('100'), user=manager,
        )

        response = owner_api.get(f'{SUMMARY}?organization={org.id}')
        assert response.data['redemptions']['missing_receipt_reference'] == 1

    def test_cross_org_analytics_denied(self, owner_b_api, org):
        assert owner_b_api.get(f'{SUMMARY}?organization={org.id}').status_code == 403

    def test_anomalies_endpoint_returns_explainable_codes(self, owner_api, org):
        response = owner_api.get(
            f'/api/v1/coffee-pass/analytics/anomalies/?organization={org.id}')
        assert response.status_code == 200
        assert isinstance(response.data['anomalies'], list)
