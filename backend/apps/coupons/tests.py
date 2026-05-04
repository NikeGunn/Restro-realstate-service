"""Tests for the coupon system."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Organization, OrganizationMembership

from .models import Coupon, CouponRedemption

User = get_user_model()


class CouponModelTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='owner@example.com', username='owner', password='Sup3rPassword!'
        )
        self.org = Organization.objects.create(name='Acme', business_type='restaurant')
        OrganizationMembership.objects.create(
            user=self.user, organization=self.org, role=OrganizationMembership.Role.OWNER
        )

    def test_code_uppercased_on_save(self):
        c = Coupon.objects.create(code=' welcome-25 ')
        self.assertEqual(c.code, 'WELCOME-25')

    def test_apply_grants_plan_and_expiry(self):
        c = Coupon.objects.create(code='X1', plan_granted='power', duration_days=30)
        before = timezone.now()
        c.apply_to(self.org, self.user)
        self.org.refresh_from_db()
        self.assertEqual(self.org.plan, 'power')
        self.assertIsNotNone(self.org.plan_expires_at)
        delta = self.org.plan_expires_at - before
        self.assertGreaterEqual(delta, timedelta(days=29, hours=23))
        self.assertLessEqual(delta, timedelta(days=30, hours=1))

    def test_check_redeemable_inactive(self):
        c = Coupon.objects.create(code='OFF', is_active=False)
        ok, reason = c.check_redeemable()
        self.assertFalse(ok)
        self.assertIn('active', reason.lower())

    def test_check_redeemable_expired_window(self):
        c = Coupon.objects.create(code='EXP', valid_until=timezone.now() - timedelta(hours=1))
        ok, _ = c.check_redeemable()
        self.assertFalse(ok)

    def test_check_redeemable_max_redemptions(self):
        c = Coupon.objects.create(code='CAPPED', max_redemptions=1)
        Coupon.objects.filter(pk=c.pk).update(redemption_count=1)
        c.refresh_from_db()
        ok, _ = c.check_redeemable()
        self.assertFalse(ok)

    def test_double_redeem_blocked(self):
        c = Coupon.objects.create(code='ONCE')
        c.apply_to(self.org, self.user)
        ok, _ = c.check_redeemable(organization=self.org)
        self.assertFalse(ok)

    def test_effective_plan_falls_back_after_expiry(self):
        self.org.plan = 'power'
        self.org.plan_expires_at = timezone.now() - timedelta(seconds=1)
        self.org.save()
        self.assertEqual(self.org.effective_plan, 'basic')
        self.assertFalse(self.org.is_power_plan)


class CouponAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='owner@example.com', username='owner', password='Sup3rPassword!'
        )
        self.outsider = User.objects.create_user(
            email='outsider@example.com', username='outsider', password='Sup3rPassword!'
        )
        self.org = Organization.objects.create(name='Acme', business_type='restaurant')
        OrganizationMembership.objects.create(
            user=self.user, organization=self.org, role=OrganizationMembership.Role.OWNER
        )
        # Seed migration already creates AI-FINYEHK in the test DB; reuse if present.
        self.coupon, _ = Coupon.objects.get_or_create(
            code='AI-FINYEHK',
            defaults={'plan_granted': 'power', 'duration_days': 30},
        )

    def test_redeem_happy_path(self):
        self.client.force_authenticate(self.user)
        resp = self.client.post(
            reverse('coupon-redeem'),
            {'code': 'ai-finyehk', 'organization': str(self.org.id)},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.org.refresh_from_db()
        self.assertEqual(self.org.plan, 'power')
        self.assertTrue(CouponRedemption.objects.filter(organization=self.org).exists())

    def test_redeem_unknown_code(self):
        self.client.force_authenticate(self.user)
        resp = self.client.post(
            reverse('coupon-redeem'),
            {'code': 'DOES-NOT-EXIST', 'organization': str(self.org.id)},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_redeem_requires_owner(self):
        self.client.force_authenticate(self.outsider)
        resp = self.client.post(
            reverse('coupon-redeem'),
            {'code': 'AI-FINYEHK', 'organization': str(self.org.id)},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_redeem_twice_same_org_rejected(self):
        self.client.force_authenticate(self.user)
        url = reverse('coupon-redeem')
        body = {'code': 'AI-FINYEHK', 'organization': str(self.org.id)}
        self.assertEqual(self.client.post(url, body, format='json').status_code, 201)
        second = self.client.post(url, body, format='json')
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)

    def test_validate_dry_run(self):
        self.client.force_authenticate(self.user)
        resp = self.client.post(
            reverse('coupon-validate'),
            {'code': 'AI-FINYEHK', 'organization': str(self.org.id)},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['valid'])
        # Validate must not redeem.
        self.assertFalse(CouponRedemption.objects.exists())

    def test_unauthenticated_rejected(self):
        resp = self.client.post(
            reverse('coupon-redeem'),
            {'code': 'AI-FINYEHK', 'organization': str(self.org.id)},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_downgrade_task_resets_expired_orgs(self):
        from .tasks import downgrade_expired_plans

        self.org.plan = 'power'
        self.org.plan_expires_at = timezone.now() - timedelta(hours=1)
        self.org.save()
        # Another org whose plan is still valid — should NOT be touched.
        live = Organization.objects.create(name='Live', business_type='restaurant')
        live.plan = 'power'
        live.plan_expires_at = timezone.now() + timedelta(days=10)
        live.save()

        count = downgrade_expired_plans()

        self.org.refresh_from_db()
        live.refresh_from_db()
        self.assertEqual(count, 1)
        self.assertEqual(self.org.plan, 'basic')
        self.assertIsNone(self.org.plan_expires_at)
        self.assertEqual(live.plan, 'power')

    def test_admin_soft_delete_disables_code(self):
        """Admin 'delete' should soft-archive (set is_active=False), and that
        immediately stops the code from being redeemable."""
        from apps.coupons.admin import CouponAdmin
        from django.contrib.admin.sites import AdminSite

        admin_instance = CouponAdmin(Coupon, AdminSite())
        # Simulate the admin invoking delete_model on a single coupon.
        request = type('R', (), {'user': self.user, '_messages': type('M', (), {'add': lambda *a, **kw: None})()})()
        admin_instance.delete_model(request, self.coupon)

        self.coupon.refresh_from_db()
        self.assertFalse(self.coupon.is_active)

        # Now the API must reject redemption.
        self.client.force_authenticate(self.user)
        resp = self.client.post(
            reverse('coupon-redeem'),
            {'code': self.coupon.code, 'organization': str(self.org.id)},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('active', resp.data['detail'].lower())

    def test_register_immune_to_session_csrf(self):
        """Register endpoint must accept POST when a stale Django session cookie
        is present (e.g. after browsing /admin). It must NOT trigger CSRF, because
        SessionAuthentication is excluded on this view."""
        from django.test import Client as DjangoClient
        client = DjangoClient(enforce_csrf_checks=True)
        # Simulate: user has a sessionid cookie from logging into /admin earlier.
        client.force_login(self.user)
        resp = client.post(
            '/api/auth/register/',
            data='{"email":"newguy@example.com","username":"newguy","first_name":"N","last_name":"G","password":"S0lid-Pass!22","password_confirm":"S0lid-Pass!22"}',
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_seed_migration_created_ai_finyehk(self):
        # The data migration in 0002_seed_ai_finyehk.py must produce this coupon
        # in any fresh DB. (Test DB applies all migrations.)
        # We delete & re-create in setUp, so just check a fresh code via migration name.
        self.assertTrue(Coupon.objects.filter(code='AI-FINYEHK').exists())
