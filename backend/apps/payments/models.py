"""
Payments models — Stripe Checkout for AI credit-pack purchases.

An org owner buys a `CreditPack` (e.g. HK$50 → 50 paid credits). Stripe Checkout
collects the card (we never touch card data → PCI-compliant). On the
`checkout.session.completed` webhook we atomically top up the Phase 6
`UsageCreditBalance.paid_credits_remaining`.

`CreditPurchase` is the order record + the idempotency anchor:
- `stripe_session_id` and `stripe_payment_intent_id` are unique (when set) so a
  replayed webhook can never create a second credit grant.
- `credited` is a one-way latch flipped inside the same locked transaction that
  grants the credits, so even a logic bug can't double-credit a paid purchase.
"""
import uuid

from django.conf import settings
from django.db import models

from apps.accounts.models import Organization


class CreditPack(models.Model):
    """Admin-seeded sellable SKU: a fixed HKD price → N paid AI credits."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True)
    credits = models.PositiveIntegerField(help_text='Paid credits granted on purchase.')
    price_hkd = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='hkd')
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'payments_credit_packs'
        ordering = ['sort_order', 'price_hkd']

    def __str__(self):
        return f'{self.name} ({self.credits} credits / HK${self.price_hkd})'

    @property
    def amount_cents(self) -> int:
        """Stripe expects the smallest currency unit (HKD has 2 decimals)."""
        return int(self.price_hkd * 100)


class CreditPurchase(models.Model):
    """One credit-pack purchase order. Drives the Stripe checkout → top-up saga."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PAID = 'paid', 'Paid'
        FAILED = 'failed', 'Failed'
        EXPIRED = 'expired', 'Expired'
        REFUNDED = 'refunded', 'Refunded'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='credit_purchases',
    )
    pack = models.ForeignKey(
        CreditPack, on_delete=models.PROTECT, related_name='purchases',
    )
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='credit_purchases',
    )

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True,
    )
    # Snapshot the pack's terms at purchase time (price/credits can change later).
    credits = models.PositiveIntegerField()
    amount_hkd = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='hkd')

    # Stripe identifiers — unique (when present) to block replayed grants.
    stripe_session_id = models.CharField(max_length=255, blank=True, db_index=True)
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True)
    stripe_charge_id = models.CharField(max_length=255, blank=True)
    stripe_receipt_url = models.URLField(blank=True)

    # One-way latch: True once the credits have been granted. Never re-credit.
    credited = models.BooleanField(default=False)
    # Link to the Phase 6 ledger row written when credits were granted.
    usage_event_id = models.UUIDField(null=True, blank=True)

    refunded_amount_hkd = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'payments_credit_purchases'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', '-created_at']),
            models.Index(fields=['status']),
        ]
        constraints = [
            # Partial-unique: a non-empty payment_intent / session id can map to
            # exactly one purchase. Blank values (pending orders) are unconstrained.
            models.UniqueConstraint(
                fields=['stripe_payment_intent_id'],
                condition=~models.Q(stripe_payment_intent_id=''),
                name='uniq_payments_intent',
            ),
            models.UniqueConstraint(
                fields=['stripe_session_id'],
                condition=~models.Q(stripe_session_id=''),
                name='uniq_payments_session',
            ),
        ]

    def __str__(self):
        return f'{self.organization_id} · {self.pack_id} · {self.status}'
