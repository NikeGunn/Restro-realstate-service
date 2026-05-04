"""
Coupon code system.

A `Coupon` is an admin-managed promotional code. Redeeming it grants an
organization a plan tier (basic|power) for a fixed number of days.
`CouponRedemption` is the audit trail and enforces one-redemption-per-org.
"""
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.accounts.models import Organization


class Coupon(models.Model):
    """Admin-managed promotional code template."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text='Case-insensitive; stored uppercased. Shown to users as-is.',
    )
    description = models.CharField(max_length=255, blank=True)

    plan_granted = models.CharField(
        max_length=20,
        choices=Organization.Plan.choices,
        default=Organization.Plan.POWER,
        help_text='Plan tier granted on redemption.',
    )
    duration_days = models.PositiveIntegerField(
        default=30,
        help_text='How many days the granted plan stays active after redemption.',
    )

    max_redemptions = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Total redemption cap across all orgs. Blank = unlimited.',
    )
    redemption_count = models.PositiveIntegerField(default=0, editable=False)

    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='coupons_created',
    )

    class Meta:
        db_table = 'coupons'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.code} ({self.get_plan_granted_display()}, {self.duration_days}d)'

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def check_redeemable(self, organization=None):
        """Return (ok, reason). reason is a short user-safe string when not ok."""
        now = timezone.now()
        if not self.is_active:
            return False, 'This coupon is no longer active.'
        if self.valid_from and now < self.valid_from:
            return False, 'This coupon is not yet valid.'
        if self.valid_until and now > self.valid_until:
            return False, 'This coupon has expired.'
        if self.max_redemptions is not None and self.redemption_count >= self.max_redemptions:
            return False, 'This coupon has reached its redemption limit.'
        if organization is not None and CouponRedemption.objects.filter(
            coupon=self, organization=organization
        ).exists():
            return False, 'This coupon has already been redeemed for this organization.'
        return True, ''

    def apply_to(self, organization, user):
        """Grant the coupon's plan to the org. Caller must wrap in a transaction."""
        now = timezone.now()
        # Extend from later of (now, current expiry) so stacking promos doesn't shrink time.
        base = (
            organization.plan_expires_at
            if organization.plan_expires_at and organization.plan_expires_at > now
            and organization.plan == self.plan_granted
            else now
        )
        granted_until = base + timedelta(days=self.duration_days)

        organization.plan = self.plan_granted
        organization.plan_expires_at = granted_until
        organization.save(update_fields=['plan', 'plan_expires_at', 'updated_at'])

        redemption = CouponRedemption.objects.create(
            coupon=self,
            organization=organization,
            user=user,
            granted_until=granted_until,
        )
        Coupon.objects.filter(pk=self.pk).update(redemption_count=models.F('redemption_count') + 1)
        return redemption


class CouponRedemption(models.Model):
    """Per-organization redemption record. Enforces single-use per org."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    coupon = models.ForeignKey(Coupon, on_delete=models.PROTECT, related_name='redemptions')
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='coupon_redemptions'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='coupon_redemptions'
    )
    redeemed_at = models.DateTimeField(auto_now_add=True)
    granted_until = models.DateTimeField()

    class Meta:
        db_table = 'coupon_redemptions'
        ordering = ['-redeemed_at']
        unique_together = [('coupon', 'organization')]

    def __str__(self):
        return f'{self.coupon.code} → {self.organization.name}'
