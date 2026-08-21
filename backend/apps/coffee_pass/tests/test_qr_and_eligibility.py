"""
QR generation + the coffee-only eligibility invariant.

Two features that arrived together because they share a root cause: the owner
could not produce a printable QR from the dashboard, and the plan picker would
silently offer FOOD as "eligible coffee" when a menu had no drinks. A live plan
was found selling 30% off a HK$175 mixed platter.

The eligibility tests here are the regression net for that bug, asserted at the
layer that actually holds it — the API — not just in the React filter.
"""
from decimal import Decimal

import pytest
from django.test import override_settings

from apps.coffee_pass.models import CoffeePassPlan, PlanStatus
from apps.coffee_pass.services import plan_service, qr_service

pytestmark = pytest.mark.django_db

PLANS_URL = '/api/v1/coffee-pass/plans/'

#: Minimal valid PNG magic number — proves we returned a real image, not HTML.
PNG_MAGIC = b'\x89PNG\r\n\x1a\n'


# ──────────────────────────────────────────────────────────────────────
# QR service
# ──────────────────────────────────────────────────────────────────────
class TestQRService:
    def test_entry_url_points_at_the_public_customer_page(self, draft_plan):
        url = qr_service.get_plan_entry_url(draft_plan)
        assert url.endswith(f'/public/coffee-pass/{draft_plan.public_token}/')
        # No PII in a string that gets printed and glued to a table.
        assert str(draft_plan.id) not in url
        assert draft_plan.organization.name not in url

    def test_unsaved_plan_refuses_rather_than_minting_a_dead_qr(self):
        """A QR that 404s is worse than no QR — it gets printed before anyone notices."""
        orphan = CoffeePassPlan(
            name='No token', price_hkd=Decimal('120.00'),
            discount_percent=Decimal('30.00'), duration_days=30,
        )
        orphan.public_token = ''
        with pytest.raises(qr_service.QRGenerationError):
            qr_service.get_plan_entry_url(orphan)

    def test_generate_qr_returns_real_png_bytes(self, draft_plan):
        png = qr_service.generate_qr_image(qr_service.get_plan_entry_url(draft_plan))
        assert png.startswith(PNG_MAGIC)
        assert len(png) > 100

    def test_generate_poster_returns_real_png_bytes(self, draft_plan):
        png = qr_service.generate_poster(draft_plan)
        assert png.startswith(PNG_MAGIC)
        # A 1200x1800 card is substantially bigger than a bare QR.
        assert len(png) > 5000

    @pytest.mark.parametrize('language', ['zh-TW', 'zh-CN', 'en'])
    def test_poster_renders_in_every_supported_language(self, draft_plan, language):
        assert qr_service.generate_poster(draft_plan, language=language).startswith(PNG_MAGIC)

    def test_unknown_language_falls_back_instead_of_crashing(self, draft_plan):
        """A bad ?language= from a URL must not 500 the print button."""
        assert qr_service.generate_poster(draft_plan, language='klingon').startswith(PNG_MAGIC)

    def test_poster_survives_emoji_and_very_long_names(self, org, location, coffee_items):
        """
        Worst case: Noto CJK has no colour-emoji glyphs and a 200-char name has
        no natural wrap point. Neither may produce an exception or a card with
        text running off the edge.
        """
        # Exactly the column maximum (200) — the longest name that can exist.
        long_name = ('☕' * 5 + 'A Very Long Cafe Name ' * 9)[:200]
        plan = CoffeePassPlan.objects.create(
            organization=org, location=location, name=long_name,
            price_hkd=Decimal('120.00'), discount_percent=Decimal('30.00'),
            duration_days=30,
        )
        plan.eligible_items.set(coffee_items)
        org.name = '🏆 Bagaicha Restaurant & Bar 餐廳' * 3
        assert qr_service.generate_poster(plan).startswith(PNG_MAGIC)

    def test_poster_renders_cjk_org_name(self, org, location, coffee_items):
        plan = CoffeePassPlan.objects.create(
            organization=org, location=location, name='咖啡通行證',
            price_hkd=Decimal('120.00'), discount_percent=Decimal('30.00'),
            duration_days=30,
        )
        plan.eligible_items.set(coffee_items)
        assert qr_service.generate_poster(plan).startswith(PNG_MAGIC)

    @override_settings(PUBLIC_BASE_URL='https://cafe.example.com/')
    def test_entry_url_honors_configured_origin_without_double_slash(self, draft_plan):
        url = qr_service.get_plan_entry_url(draft_plan)
        assert url.startswith('https://cafe.example.com/public/coffee-pass/')
        assert '//public' not in url


# ──────────────────────────────────────────────────────────────────────
# QR / poster endpoints
# ──────────────────────────────────────────────────────────────────────
class TestQREndpoints:
    def test_owner_downloads_qr_png(self, owner_api, active_plan):
        resp = owner_api.get(f'{PLANS_URL}{active_plan.id}/qr/')
        assert resp.status_code == 200
        assert resp['Content-Type'] == 'image/png'
        assert b''.join(resp.streaming_content
                        if resp.streaming else [resp.content]).startswith(PNG_MAGIC)
        assert 'attachment;' in resp['Content-Disposition']

    def test_owner_downloads_poster_png(self, owner_api, active_plan):
        resp = owner_api.get(f'{PLANS_URL}{active_plan.id}/poster/')
        assert resp.status_code == 200
        assert resp['Content-Type'] == 'image/png'
        assert resp.content.startswith(PNG_MAGIC)

    def test_manager_may_print_a_replacement_card(self, manager_api, active_plan):
        """Reprinting a spilled-on counter card is the till job, not an owner privilege."""
        assert manager_api.get(f'{PLANS_URL}{active_plan.id}/qr/').status_code == 200

    def test_draft_plan_qr_is_available_before_activation(self, owner_api, draft_plan):
        """Owners print cards while setting up; the QR resolves once activated."""
        assert owner_api.get(f'{PLANS_URL}{draft_plan.id}/qr/').status_code == 200

    def test_cross_org_plan_qr_is_404_not_403(self, owner_api, plan_b):
        """Never confirm that another tenant's plan id exists."""
        assert owner_api.get(f'{PLANS_URL}{plan_b.id}/qr/').status_code == 404

    def test_outsider_cannot_download_qr(self, outsider_api, active_plan):
        assert outsider_api.get(f'{PLANS_URL}{active_plan.id}/qr/').status_code in (403, 404)

    def test_anonymous_cannot_download_qr(self, api, active_plan):
        """The QR itself is public, but the dashboard endpoint still needs auth."""
        assert api.get(f'{PLANS_URL}{active_plan.id}/qr/').status_code in (401, 403)

    def test_generation_failure_returns_json_not_a_broken_png(
            self, owner_api, active_plan, monkeypatch):
        """
        Worst case: Pillow/qrcode missing or a font blows up in the prod image.
        The browser must get a readable JSON error, never a 500 HTML page saved
        as a .png file.
        """
        def boom(*a, **kw):
            raise RuntimeError('libpng exploded')

        monkeypatch.setattr(qr_service, 'generate_poster', boom)
        resp = owner_api.get(f'{PLANS_URL}{active_plan.id}/poster/')
        assert resp.status_code == 500
        assert resp['Content-Type'].startswith('application/json')
        assert 'detail' in resp.json()

    def test_missing_token_surfaces_as_422(self, owner_api, active_plan, monkeypatch):
        def refuse(*a, **kw):
            raise qr_service.QRGenerationError('Plan has no public_token; save the plan first.')

        monkeypatch.setattr(qr_service, 'generate_qr_image', refuse)
        resp = owner_api.get(f'{PLANS_URL}{active_plan.id}/qr/')
        assert resp.status_code == 422
        assert 'public_token' in resp.json()['detail']

    def test_filename_is_stable_and_unique_for_cjk_names(
            self, owner_api, org, location, coffee_items):
        """slugify() drops CJK entirely — the id must keep the filename usable."""
        plan = CoffeePassPlan.objects.create(
            organization=org, location=location, name='咖啡通行證',
            price_hkd=Decimal('120.00'), discount_percent=Decimal('30.00'),
            duration_days=30, status=PlanStatus.ACTIVE,
        )
        plan.eligible_items.set(coffee_items)
        disposition = owner_api.get(f'{PLANS_URL}{plan.id}/qr/')['Content-Disposition']
        assert str(plan.id) in disposition
        assert disposition.endswith('.png"')

    def test_qr_is_never_cached_by_a_shared_proxy(self, owner_api, active_plan):
        cache_control = owner_api.get(f'{PLANS_URL}{active_plan.id}/qr/')['Cache-Control']
        assert 'private' in cache_control


# ──────────────────────────────────────────────────────────────────────
# Eligible-items endpoint (replaces the client-side filter)
# ──────────────────────────────────────────────────────────────────────
class TestEligibleItemsEndpoint:
    def test_returns_coffee_and_drink_but_never_food(
            self, owner_api, org, coffee_items, espresso_item, food_item):
        resp = owner_api.get(f'{PLANS_URL}eligible-items/', {'organization': org.id})
        assert resp.status_code == 200
        names = {i['name'] for i in resp.json()['results']}
        assert 'Espresso' in names
        assert 'Latte' in names
        assert 'Mixed Platter' not in names

    def test_empty_menu_returns_empty_list_not_the_whole_menu(
            self, owner_api, org, food_item):
        """
        THE regression test. Previously the UI filter matched nothing and fell
        back to every item, which is how food became pass-eligible in production.
        An org with no coffee must get zero results — never a food list.
        """
        resp = owner_api.get(f'{PLANS_URL}eligible-items/', {'organization': org.id})
        assert resp.status_code == 200
        assert resp.json()['count'] == 0
        assert resp.json()['results'] == []

    def test_response_advertises_the_eligible_types(self, owner_api, org, coffee_items):
        body = owner_api.get(f'{PLANS_URL}eligible-items/', {'organization': org.id}).json()
        assert 'coffee' in body['eligible_item_types']
        assert 'food' not in body['eligible_item_types']

    def test_other_orgs_items_are_never_listed(
            self, owner_api, org, coffee_items, foreign_item):
        body = owner_api.get(f'{PLANS_URL}eligible-items/', {'organization': org.id}).json()
        assert 'Rival Latte' not in {i['name'] for i in body['results']}

    def test_asking_about_another_org_is_404(self, owner_api, org_b, plan_b):
        resp = owner_api.get(f'{PLANS_URL}eligible-items/', {'organization': org_b.id})
        assert resp.status_code == 404

    def test_missing_organization_param_is_400(self, owner_api):
        assert owner_api.get(f'{PLANS_URL}eligible-items/').status_code == 400

    def test_manager_may_read_the_picker(self, manager_api, org, coffee_items):
        assert manager_api.get(
            f'{PLANS_URL}eligible-items/', {'organization': org.id}).status_code == 200

    @override_settings(COFFEE_PASS_SETTINGS={'ELIGIBLE_ITEM_TYPES': ('coffee', 'drink', 'food')})
    def test_widening_eligibility_is_a_config_change(
            self, owner_api, org, coffee_items, food_item):
        """
        Future-proofing: a promo where a pass also covers a pastry must be a
        configmap edit, not a code change and redeploy.
        """
        body = owner_api.get(f'{PLANS_URL}eligible-items/', {'organization': org.id}).json()
        assert 'Mixed Platter' in {i['name'] for i in body['results']}


# ──────────────────────────────────────────────────────────────────────
# The invariant: the SERVER refuses food, whatever the client sends
# ──────────────────────────────────────────────────────────────────────
class TestCoffeeOnlyInvariant:
    def _payload(self, org, location, items):
        return {
            'organization': str(org.id), 'location': str(location.id),
            'name': 'Coffee Pass — 30 days', 'price_hkd': '120.00',
            'discount_percent': '30.00', 'duration_days': 30,
            'eligible_items': [str(i.id) for i in items],
        }

    def test_creating_a_plan_with_food_is_rejected(
            self, owner_api, org, location, coffee_items, food_item):
        """A stale browser tab or a direct API call must not resurrect the bug."""
        resp = owner_api.post(
            PLANS_URL, self._payload(org, location, coffee_items + [food_item]),
            format='json',
        )
        assert resp.status_code == 400
        assert 'Mixed Platter' in str(resp.json()['eligible_items'])

    def test_creating_a_plan_with_only_coffee_succeeds(
            self, owner_api, org, location, espresso_item):
        resp = owner_api.post(
            PLANS_URL, self._payload(org, location, [espresso_item]), format='json',
        )
        assert resp.status_code == 201

    def test_legacy_drink_items_still_work(
            self, owner_api, org, location, coffee_items):
        """Menus built before the coffee type existed must not break."""
        resp = owner_api.post(
            PLANS_URL, self._payload(org, location, coffee_items), format='json',
        )
        assert resp.status_code == 201

    def test_patching_food_onto_an_existing_plan_is_rejected(
            self, owner_api, draft_plan, coffee_items, food_item):
        resp = owner_api.patch(
            f'{PLANS_URL}{draft_plan.id}/',
            {'eligible_items': [str(i.id) for i in coffee_items + [food_item]]},
            format='json',
        )
        assert resp.status_code == 400
        draft_plan.refresh_from_db()
        assert food_item not in draft_plan.eligible_items.all()

    def test_error_message_names_the_offending_items(
            self, owner_api, org, location, food_item):
        """The owner must be told which item to fix, not just 'invalid'."""
        detail = str(owner_api.post(
            PLANS_URL, self._payload(org, location, [food_item]), format='json',
        ).json()['eligible_items'])
        assert 'Mixed Platter' in detail
        assert 'Coffee' in detail

    def test_service_layer_rejects_food_even_bypassing_the_serializer(
            self, draft_plan, food_item):
        """
        The invariant must hold for the admin, a management command, and a
        Celery task — anything that never touches DRF.
        """
        from django.core.exceptions import ValidationError

        draft_plan.eligible_items.add(food_item)
        with pytest.raises(ValidationError) as exc:
            plan_service.validate_tenancy(draft_plan)
        assert 'Mixed Platter' in str(exc.value)

    def test_eligible_item_types_defaults_when_setting_is_blank(self):
        """A blank override must not brick plan creation for every tenant."""
        with override_settings(COFFEE_PASS_SETTINGS={'ELIGIBLE_ITEM_TYPES': ()}):
            assert plan_service.eligible_item_types() == frozenset(
                plan_service.DEFAULT_ELIGIBLE_ITEM_TYPES
            )

    def test_food_is_never_eligible_by_default(self):
        assert 'food' not in plan_service.eligible_item_types()
        assert 'coffee' in plan_service.eligible_item_types()
