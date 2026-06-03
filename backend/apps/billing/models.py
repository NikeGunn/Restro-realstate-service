"""
Billing models — AI Credit & Usage Billing System (Phase 6).

This is a **usage-tracking + credit-wallet** layer, NOT a payment processor:
no card charges, no Stripe. Plans are granted via admin / the `coupons` app;
this app meters AI usage, holds the credit wallet, and enforces a monthly
spend cap.

Correctness-critical tables:
- `UsageCreditBalance` is the **single row we lock** (`select_for_update`) for
  every reserve/confirm/refund. One per org (OneToOne).
- `UsageEvent` is an **APPEND-ONLY** ledger. A refund is a NEW row, never an
  edit of the original. A unique `idempotency_key` makes Celery retries safe.
"""
import uuid

from django.conf import settings
from django.db import models

from apps.accounts.models import Organization


# ── enums ──────────────────────────────────────────────────────────────────

class CapStatus(models.TextChoices):
    ACTIVE = 'active', 'Active'
    WARNING_50 = 'warning_50', 'Warning 50%'
    WARNING_80 = 'warning_80', 'Warning 80%'
    BLOCKED = 'blocked', 'Blocked'


class SubscriptionStatus(models.TextChoices):
    ACTIVE = 'active', 'Active'
    PAUSED = 'paused', 'Paused'
    CANCELLED = 'cancelled', 'Cancelled'
    TRIAL = 'trial', 'Trial'


class UsageModule(models.TextChoices):
    CONTENT_STUDIO = 'content_studio', 'Content Studio'
    INVENTORY_AI = 'inventory_ai', 'Inventory AI'
    CHATBOT_AI = 'chatbot_ai', 'Chatbot AI'
    MESSAGING = 'messaging', 'Messaging'


class EventStatus(models.TextChoices):
    RESERVED = 'reserved', 'Reserved'
    SUCCESS = 'success', 'Success'
    FAILED = 'failed', 'Failed'
    REFUNDED = 'refunded', 'Refunded'


# ── models ─────────────────────────────────────────────────────────────────

class SubscriptionPlan(models.Model):
    """Admin-seeded catalog of plans. `plan_code` maps to Organization.plan."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=60, unique=True)
    price_hkd = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    monthly_image_credits = models.PositiveIntegerField(default=0)
    plan_code = models.CharField(
        max_length=20, choices=Organization.Plan.choices,
        default=Organization.Plan.BASIC,
        help_text='Maps to Organization.plan (basic/power).',
    )
    enabled_modules = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'billing_subscription_plans'
        ordering = ['price_hkd']

    def __str__(self):
        return f'{self.name} ({self.plan_code}, {self.monthly_image_credits} cr)'


class AccountSubscription(models.Model):
    """One active subscription per org. Tracks the billing period + spend cap."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='subscriptions',
    )
    plan = models.ForeignKey(
        SubscriptionPlan, on_delete=models.PROTECT, related_name='subscriptions',
    )
    status = models.CharField(
        max_length=20, choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.ACTIVE,
    )
    current_period_start = models.DateField()
    current_period_end = models.DateField()
    monthly_ai_spend_cap_hkd = models.DecimalField(
        max_digits=10, decimal_places=2, default=200,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'billing_account_subscriptions'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['organization', 'status'])]

    def __str__(self):
        return f'{self.organization_id} · {self.plan.slug} · {self.status}'


class UsageCreditBalance(models.Model):
    """OneToOne org — THE row locked for every credit mutation.

    Deduction order is ALWAYS free → paid (never touch paid until free is
    exhausted). `reserved_credits` is the in-flight reservation count.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField(
        Organization, on_delete=models.CASCADE, related_name='credit_balance',
    )
    free_credits_remaining = models.PositiveIntegerField(default=0)
    paid_credits_remaining = models.PositiveIntegerField(default=0)
    free_credits_used_this_month = models.PositiveIntegerField(default=0)
    paid_credits_used_this_month = models.PositiveIntegerField(default=0)
    reserved_credits = models.PositiveIntegerField(default=0)
    current_estimated_spend_hkd = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
    )
    cap_status = models.CharField(
        max_length=20, choices=CapStatus.choices, default=CapStatus.ACTIVE,
    )
    period_start = models.DateField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'billing_credit_balances'

    def __str__(self):
        return (f'{self.organization_id} · free={self.free_credits_remaining} '
                f'paid={self.paid_credits_remaining} reserved={self.reserved_credits}')

    @property
    def total_available(self) -> int:
        """Credits that can still be reserved (free + paid − already reserved)."""
        return max(
            0,
            self.free_credits_remaining + self.paid_credits_remaining - self.reserved_credits,
        )


class UsageEvent(models.Model):
    """APPEND-ONLY usage ledger row. A refund is a NEW row, never an edit.

    `idempotency_key` is unique → calling reserve twice with the same key
    returns the existing event instead of double-charging (Celery-retry safe).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='usage_events',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='usage_events',
        help_text='Null = system-initiated.',
    )
    module = models.CharField(max_length=30, choices=UsageModule.choices)
    event_type = models.CharField(max_length=60)
    provider = models.CharField(max_length=60, blank=True)
    model = models.CharField(max_length=80, blank=True)
    credits_used = models.PositiveIntegerField(default=0)
    is_free_credit = models.BooleanField(default=False)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    cost_hkd = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    billable_amount_hkd = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    status = models.CharField(
        max_length=20, choices=EventStatus.choices, default=EventStatus.RESERVED,
    )
    reference_id = models.UUIDField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=64, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    # Internal bookkeeping: how the originally-reserved credits split free/paid,
    # so a refund can restore them to the right bucket without guessing.
    reserved_free = models.PositiveIntegerField(default=0)
    reserved_paid = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'billing_usage_events'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', '-created_at']),
            models.Index(fields=['organization', 'module']),
            models.Index(fields=['status']),
            models.Index(fields=['reference_id']),
        ]

    def __str__(self):
        return f'{self.module}/{self.event_type} · {self.status} · {self.credits_used}cr'


class UsageLimit(models.Model):
    """OneToOne org — owner-configurable spend cap + alert threshold."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField(
        Organization, on_delete=models.CASCADE, related_name='usage_limit',
    )
    monthly_ai_spend_cap_hkd = models.DecimalField(
        max_digits=10, decimal_places=2, default=200,
    )
    monthly_image_credits_extra_allowed = models.PositiveIntegerField(default=0)
    alert_at_percent = models.PositiveIntegerField(default=80)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'billing_usage_limits'

    def __str__(self):
        return f'{self.organization_id} cap=HKD{self.monthly_ai_spend_cap_hkd}'


class MonthlyUsageSummary(models.Model):
    """Celery-generated per-org per-month rollup. Unique (org, year, month)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='monthly_summaries',
    )
    year = models.PositiveIntegerField()
    month = models.PositiveIntegerField()
    free_credits_used = models.PositiveIntegerField(default=0)
    paid_credits_used = models.PositiveIntegerField(default=0)
    total_cost_usd = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    total_cost_hkd = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    total_billable_hkd = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    image_generations = models.PositiveIntegerField(default=0)
    ai_queries = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'billing_monthly_summaries'
        ordering = ['-year', '-month']
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'year', 'month'],
                name='uniq_billing_monthly_summary',
            ),
        ]

    def __str__(self):
        return f'{self.organization_id} {self.year}-{self.month:02d}'
