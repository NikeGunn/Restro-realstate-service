"""
Coffee Pass models — a paid 30-day repeat-visit membership.

A customer who confirms they enjoyed a coffee may buy a Coffee Pass that grants
a transparent 30% discount on eligible coffee at ONE cafe location for 30 days.
Staff verify a rotating QR/fallback code and record the redemption; the external
POS stays the payment source of truth, this ledger is the discount/retention
source of truth.

Conventions (mirrors Phase 0-6 + payments):
- UUID PKs, Decimal money, UTC timestamps, tables prefixed `coffee_pass_`.
- Cross-app FKs use string refs so no import cycles (crm/restaurant/accounts).
- Plan terms are SNAPSHOTTED at purchase; editing a plan can never alter an
  already-sold entitlement.
- Stripe identifiers are partial-unique when non-empty, and `activated` is a
  one-way latch, so a replayed webhook can never activate a second pass.
- Verification tokens store only a hash — the raw QR secret is never persisted.
- CoffeePassAuditEvent and CoffeePassOutboxEvent are append-only.

⚠️ This is NOT `apps.coupons` (which grants ORG SOFTWARE PLAN tiers) and NOT
`apps.payments.CreditPurchase` (which buys ORG AI CREDITS). Coffee Pass money is
CUSTOMER money buying a CUSTOMER entitlement — a separate bounded context.
"""
import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


# ──────────────────────────────────────────────────────────────────────
# Choice enums
# ──────────────────────────────────────────────────────────────────────
class PlanStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    ACTIVE = 'active', 'Active'
    PAUSED = 'paused', 'Paused'
    ARCHIVED = 'archived', 'Archived'


class Sentiment(models.TextChoices):
    """The quality gate. Only GOOD (and optionally OKAY) may see an offer."""
    GOOD = 'good', 'Good'
    OKAY = 'okay', 'Okay'
    NOT_GOOD = 'not_good', 'Not good'


class RoutineContext(models.TextChoices):
    """Voluntarily supplied habit context. NEVER inferred from location/employment."""
    WORK_NEARBY = 'work_nearby', 'Work nearby'
    STUDY_NEARBY = 'study_nearby', 'Study nearby'
    LIVE_NEARBY = 'live_nearby', 'Live nearby'
    OCCASIONAL = 'occasional', 'Occasionally'
    PREFER_NOT_TO_SAY = 'prefer_not_to_say', 'Prefer not to say'


class ExperienceSource(models.TextChoices):
    QR = 'qr', 'QR'
    WHATSAPP = 'whatsapp', 'WhatsApp'
    STAFF = 'staff', 'Staff'


class PurchaseStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    PAID = 'paid', 'Paid'
    FAILED = 'failed', 'Failed'
    EXPIRED = 'expired', 'Expired'
    REFUNDED = 'refunded', 'Refunded'


class PassStatus(models.TextChoices):
    PENDING_PAYMENT = 'pending_payment', 'Pending payment'
    ACTIVE = 'active', 'Active'
    EXPIRED = 'expired', 'Expired'
    SUSPENDED = 'suspended', 'Suspended'
    CANCELLED = 'cancelled', 'Cancelled'


class RedemptionStatus(models.TextChoices):
    REDEEMED = 'redeemed', 'Redeemed'
    VOIDED = 'voided', 'Voided'


class OutboxStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    SENT = 'sent', 'Sent'
    FAILED = 'failed', 'Failed'
    SKIPPED = 'skipped', 'Skipped'


#: Pass states that are terminal — a pass here can never redeem again.
TERMINAL_PASS_STATUSES = frozenset({
    PassStatus.EXPIRED, PassStatus.CANCELLED,
})


# ──────────────────────────────────────────────────────────────────────
# Plan
# ──────────────────────────────────────────────────────────────────────
class CoffeePassPlan(models.Model):
    """
    An owner-configured, location-specific membership product.

    Terms here are the CURRENT sale terms. Once sold, the buyer's entitlement is
    driven by the snapshot on their purchase/pass — editing this row never
    changes what an existing member is owed.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE,
        related_name='coffee_pass_plans',
    )
    location = models.ForeignKey(
        'accounts.Location', on_delete=models.CASCADE,
        related_name='coffee_pass_plans',
    )

    name = models.CharField(max_length=200, default='Coffee Pass — 30 days')
    description = models.TextField(blank=True)

    price_hkd = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    currency = models.CharField(max_length=3, default='hkd')
    discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('30.00'),
        help_text='0 < value <= 50. The customer-facing discount on eligible items.',
    )
    duration_days = models.PositiveIntegerField(default=30)

    eligible_items = models.ManyToManyField(
        'restaurant.MenuItem', blank=True, related_name='coffee_pass_plans',
        help_text='Required before activation. Must belong to this organization.',
    )

    #: Whether a neutral ("okay") experience may also see an offer. Default off:
    #: the product is a reward for a good experience, not a rescue discount.
    allow_neutral_feedback = models.BooleanField(default=False)

    status = models.CharField(
        max_length=10, choices=PlanStatus.choices, default=PlanStatus.DRAFT, db_index=True,
    )

    #: Owner acknowledged that break-even exceeds the safe threshold (A.6 guard).
    break_even_acknowledged = models.BooleanField(default=False)

    #: Public entry token for this plan's QR code. Opaque — carries no PII.
    public_token = models.CharField(max_length=64, unique=True, db_index=True)

    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='coffee_pass_plans_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'coffee_pass_plans'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', 'location', 'status']),
            models.Index(fields=['organization', '-created_at']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(discount_percent__gt=0) & models.Q(discount_percent__lte=50),
                name='coffee_pass_plan_discount_range',
            ),
            models.CheckConstraint(
                check=models.Q(duration_days__gt=0),
                name='coffee_pass_plan_duration_positive',
            ),
        ]

    def __str__(self):
        return f'{self.name} @ {self.location_id} ({self.status})'

    def save(self, *args, **kwargs):
        if not self.public_token:
            self.public_token = uuid.uuid4().hex
        super().save(*args, **kwargs)

    @property
    def is_sellable(self) -> bool:
        """Only an ACTIVE plan may start a new checkout. Paused honors existing passes."""
        return self.status == PlanStatus.ACTIVE

    @property
    def amount_cents(self) -> int:
        """Stripe expects the smallest currency unit (HKD has 2 decimals)."""
        return int(self.price_hkd * 100)

    def build_snapshot(self) -> dict:
        """
        Freeze the terms a buyer is agreeing to. Stored on the purchase AND the
        pass so later plan edits can never alter an existing entitlement.
        """
        items = list(
            self.eligible_items.all().values('id', 'name', 'price')
        )
        return {
            'plan_id': str(self.id),
            'name': self.name,
            'description': self.description,
            'price_hkd': str(self.price_hkd),
            'currency': self.currency,
            'discount_percent': str(self.discount_percent),
            'duration_days': self.duration_days,
            'location_id': str(self.location_id),
            'eligible_items': [
                {'id': str(i['id']), 'name': i['name'], 'price': str(i['price'])}
                for i in items
            ],
            'snapshot_at': timezone.now().isoformat(),
        }


# ──────────────────────────────────────────────────────────────────────
# Experience (the quality gate)
# ──────────────────────────────────────────────────────────────────────
class CoffeeExperience(models.Model):
    """
    One verified post-visit response. The hard quality gate for offers:
    a `not_good` experience can never produce an eligible offer decision.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE,
        related_name='coffee_experiences',
    )
    location = models.ForeignKey(
        'accounts.Location', on_delete=models.CASCADE,
        related_name='coffee_experiences',
    )
    customer = models.ForeignKey(
        'crm.CRMCustomer', on_delete=models.CASCADE,
        related_name='coffee_experiences',
    )
    plan = models.ForeignKey(
        CoffeePassPlan, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='experiences',
    )

    sentiment = models.CharField(max_length=10, choices=Sentiment.choices)
    #: Private to the owner's service-recovery workflow — NEVER exposed to the
    #: staff redemption endpoint (A.9) or any public response.
    comment = models.TextField(max_length=1000, blank=True)
    routine_context = models.CharField(
        max_length=20, choices=RoutineContext.choices, blank=True,
    )
    source = models.CharField(
        max_length=10, choices=ExperienceSource.choices, default=ExperienceSource.QR,
    )

    offer_shown_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'coffee_pass_experiences'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['customer', 'location', '-created_at']),
            models.Index(fields=['organization', 'location', 'sentiment']),
            models.Index(fields=['organization', '-created_at']),
        ]

    def __str__(self):
        return f'{self.sentiment} · {self.customer_id} @ {self.location_id}'

    @property
    def is_positive(self) -> bool:
        return self.sentiment in (Sentiment.GOOD, Sentiment.OKAY)


# ──────────────────────────────────────────────────────────────────────
# Purchase (the Stripe checkout saga record)
# ──────────────────────────────────────────────────────────────────────
class CoffeePassPurchase(models.Model):
    """
    A customer's Coffee Pass order. Separate from payments.CreditPurchase: that
    is ORG money for AI credits, this is CUSTOMER money for an entitlement.

    Idempotency is layered exactly like the payments saga:
      1. webhook event-id cache claim (dedupes deliveries)
      2. partial-unique stripe session/intent ids (dedupes across restarts)
      3. `activated` one-way latch inside the locked txn (blocks double-grant)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE,
        related_name='coffee_pass_purchases',
    )
    location = models.ForeignKey(
        'accounts.Location', on_delete=models.CASCADE,
        related_name='coffee_pass_purchases',
    )
    customer = models.ForeignKey(
        'crm.CRMCustomer', on_delete=models.CASCADE,
        related_name='coffee_pass_purchases',
    )
    plan = models.ForeignKey(
        CoffeePassPlan, on_delete=models.PROTECT, related_name='purchases',
    )
    experience = models.ForeignKey(
        CoffeeExperience, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='purchases',
        help_text='The experience that made this customer eligible (audit trail).',
    )

    status = models.CharField(
        max_length=10, choices=PurchaseStatus.choices,
        default=PurchaseStatus.PENDING, db_index=True,
    )
    #: Immutable copy of the plan terms at checkout time.
    plan_snapshot = models.JSONField(default=dict)
    amount_hkd = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='hkd')

    stripe_session_id = models.CharField(max_length=255, blank=True, db_index=True)
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True)
    stripe_charge_id = models.CharField(max_length=255, blank=True)
    stripe_receipt_url = models.URLField(blank=True)

    #: One-way latch: True once a pass has been created for this order.
    activated = models.BooleanField(default=False)

    refunded_amount_hkd = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0'),
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'coffee_pass_purchases'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', '-created_at']),
            models.Index(fields=['customer', '-created_at']),
            models.Index(fields=['status']),
        ]
        constraints = [
            # Partial-unique: a non-empty Stripe id maps to exactly one purchase.
            models.UniqueConstraint(
                fields=['stripe_payment_intent_id'],
                condition=~models.Q(stripe_payment_intent_id=''),
                name='uniq_coffee_pass_intent',
            ),
            models.UniqueConstraint(
                fields=['stripe_session_id'],
                condition=~models.Q(stripe_session_id=''),
                name='uniq_coffee_pass_session',
            ),
        ]

    def __str__(self):
        return f'{self.customer_id} · {self.plan_id} · {self.status}'

    @property
    def is_fully_refunded(self) -> bool:
        return self.refunded_amount_hkd >= self.amount_hkd > Decimal('0')


# ──────────────────────────────────────────────────────────────────────
# Pass (the entitlement)
# ──────────────────────────────────────────────────────────────────────
class CoffeePass(models.Model):
    """
    The entitlement itself. `EntitlementService` is the ONLY authority on whether
    this pass may redeem — manual staff redemption today, a POS adapter later,
    both asking the same question.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='coffee_passes',
    )
    location = models.ForeignKey(
        'accounts.Location', on_delete=models.CASCADE, related_name='coffee_passes',
    )
    customer = models.ForeignKey(
        'crm.CRMCustomer', on_delete=models.CASCADE, related_name='coffee_passes',
    )
    plan = models.ForeignKey(
        CoffeePassPlan, on_delete=models.PROTECT, related_name='passes',
    )
    purchase = models.OneToOneField(
        CoffeePassPurchase, on_delete=models.CASCADE, related_name='coffee_pass',
    )

    status = models.CharField(
        max_length=20, choices=PassStatus.choices,
        default=PassStatus.PENDING_PAYMENT, db_index=True,
    )
    #: Immutable copy from the purchase — the terms this member actually bought.
    plan_snapshot = models.JSONField(default=dict)

    starts_at = models.DateTimeField()
    expires_at = models.DateTimeField(db_index=True)

    suspension_reason = models.CharField(max_length=255, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'coffee_pass_passes'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['customer', 'location', 'status', 'expires_at']),
            models.Index(fields=['organization', 'location', 'status']),
            models.Index(fields=['status', 'expires_at']),
        ]
        constraints = [
            # One ACTIVE pass per (customer, location, plan). Partial so expired /
            # cancelled history is unconstrained. This is the authoritative
            # backstop behind the service-level duplicate check.
            models.UniqueConstraint(
                fields=['customer', 'location', 'plan'],
                condition=models.Q(status='active'),
                name='uniq_coffee_pass_active_per_customer_location_plan',
            ),
        ]

    def __str__(self):
        return f'{self.customer_id} @ {self.location_id} ({self.status})'

    # ── entitlement helpers (single source of truth for "can this redeem?") ──
    @property
    def discount_percent(self) -> Decimal:
        """Read the SNAPSHOT, never the live plan — terms are frozen at purchase."""
        raw = (self.plan_snapshot or {}).get('discount_percent')
        return Decimal(str(raw)) if raw is not None else self.plan.discount_percent

    @property
    def eligible_item_names(self) -> list:
        return [i['name'] for i in (self.plan_snapshot or {}).get('eligible_items', [])]

    def is_redeemable(self, at=None) -> bool:
        """Active AND inside its window. Query-time expiry is the final guard."""
        at = at or timezone.now()
        return self.status == PassStatus.ACTIVE and self.starts_at <= at < self.expires_at


# ──────────────────────────────────────────────────────────────────────
# Redemption (the discount ledger)
# ──────────────────────────────────────────────────────────────────────
class CoffeePassRedemption(models.Model):
    """
    One recorded discount. Org/location/customer are denormalized so tenant-safe
    reporting never needs to join through the pass.

    Never deleted — a correction is a `void` that flips status and audits.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE,
        related_name='coffee_pass_redemptions',
    )
    location = models.ForeignKey(
        'accounts.Location', on_delete=models.CASCADE,
        related_name='coffee_pass_redemptions',
    )
    coffee_pass = models.ForeignKey(
        CoffeePass, on_delete=models.CASCADE, related_name='redemptions',
    )
    customer = models.ForeignKey(
        'crm.CRMCustomer', on_delete=models.CASCADE,
        related_name='coffee_pass_redemptions',
    )
    redeemed_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='coffee_pass_redemptions',
    )

    #: Staff-entered pre-discount subtotal for ELIGIBLE items only.
    eligible_subtotal_hkd = models.DecimalField(max_digits=10, decimal_places=2)
    #: ALWAYS server-calculated from the snapshot percent. Never trusted from the client.
    discount_amount_hkd = models.DecimalField(max_digits=10, decimal_places=2)
    discount_percent_applied = models.DecimalField(max_digits=5, decimal_places=2)

    pos_receipt_reference = models.CharField(max_length=100, blank=True)

    status = models.CharField(
        max_length=10, choices=RedemptionStatus.choices,
        default=RedemptionStatus.REDEEMED, db_index=True,
    )
    redeemed_at = models.DateTimeField(default=timezone.now, db_index=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='coffee_pass_voids',
    )
    void_reason = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'coffee_pass_redemptions'
        ordering = ['-redeemed_at']
        indexes = [
            models.Index(fields=['organization', 'location', '-redeemed_at']),
            models.Index(fields=['coffee_pass', '-redeemed_at']),
            models.Index(fields=['customer', '-redeemed_at']),
            models.Index(fields=['organization', 'status']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(eligible_subtotal_hkd__gte=Decimal('0')),
                name='coffee_pass_redemption_subtotal_non_negative',
            ),
        ]

    def __str__(self):
        return f'{self.coffee_pass_id} · HK${self.discount_amount_hkd} ({self.status})'

    @property
    def counts_toward_savings(self) -> bool:
        return self.status == RedemptionStatus.REDEEMED


# ──────────────────────────────────────────────────────────────────────
# Verification token (the rotating QR secret)
# ──────────────────────────────────────────────────────────────────────
class CoffeePassVerificationToken(models.Model):
    """
    A short-lived one-time code minted by the customer's wallet and consumed by
    staff at redemption.

    SECURITY: only the HASH is stored. The raw value exists in the HTTP response
    to the wallet and in the staff's scan — never at rest, so a database leak
    cannot mint redemptions.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    coffee_pass = models.ForeignKey(
        CoffeePass, on_delete=models.CASCADE, related_name='verification_tokens',
    )
    #: SHA-256 of the raw token. Unique so a hash collision/replay can't co-exist.
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    #: Short human-typable fallback, also hashed. Scoped per pass, not global.
    fallback_hash = models.CharField(max_length=64, blank=True, db_index=True)

    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    consumed_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='coffee_pass_tokens_consumed',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'coffee_pass_verification_tokens'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['coffee_pass', '-created_at']),
            models.Index(fields=['expires_at', 'consumed_at']),
        ]

    def __str__(self):
        return f'token · {self.coffee_pass_id} · {"used" if self.consumed_at else "live"}'

    def is_live(self, at=None) -> bool:
        at = at or timezone.now()
        return self.consumed_at is None and self.expires_at > at


# ──────────────────────────────────────────────────────────────────────
# OTP (public customer session bootstrap)
# ──────────────────────────────────────────────────────────────────────
class CoffeePassOTP(models.Model):
    """
    A hashed one-time login code for the public customer flow.

    SECURITY: the code is hashed at rest, expires quickly, is attempt-limited,
    and endpoints return a GENERIC response whether or not the phone exists, so
    the flow can't be used to enumerate customers.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE,
        related_name='coffee_pass_otps',
    )
    #: E.164 phone the code was sent to. Not a FK — the customer may not exist yet.
    phone = models.CharField(max_length=30, db_index=True)
    code_hash = models.CharField(max_length=64)

    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)

    ip_hash = models.CharField(max_length=64, blank=True)

    #: Whether the code actually REACHED the customer.
    #:
    #: The endpoint must answer identically for a known and unknown phone, so a
    #: delivery failure cannot be surfaced in the HTTP response. Recording it
    #: here is what stops "no WhatsApp config" from being an invisible outage:
    #: the owner's dashboard reads these rows. Without this the flow looks
    #: healthy from the outside while no customer can ever log in.
    delivery_status = models.CharField(
        max_length=20, default='pending', db_index=True,
        choices=[
            ('pending', 'Pending'),
            ('sent', 'Sent'),
            ('no_channel', 'No WhatsApp channel configured'),
            ('failed', 'Delivery failed'),
        ],
    )
    #: Operator-facing reason for a non-'sent' status. Never shown to customers.
    delivery_detail = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'coffee_pass_otps'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', 'phone', '-created_at']),
            models.Index(fields=['expires_at']),
            models.Index(fields=['organization', 'delivery_status', '-created_at']),
        ]

    def __str__(self):
        return f'otp · {self.phone[-4:] if self.phone else "?"} · {self.created_at:%H:%M}'


# ──────────────────────────────────────────────────────────────────────
# Audit (APPEND-ONLY)
# ──────────────────────────────────────────────────────────────────────
class CoffeePassAuditEvent(models.Model):
    """Append-only log of every state change: plan, payment, redemption, void."""

    class Action(models.TextChoices):
        PLAN_CREATED = 'plan_created', 'Plan created'
        PLAN_UPDATED = 'plan_updated', 'Plan updated'
        PLAN_ACTIVATED = 'plan_activated', 'Plan activated'
        PLAN_PAUSED = 'plan_paused', 'Plan paused'
        EXPERIENCE_SUBMITTED = 'experience_submitted', 'Experience submitted'
        CHECKOUT_STARTED = 'checkout_started', 'Checkout started'
        PASS_ACTIVATED = 'pass_activated', 'Pass activated'
        PASS_EXPIRED = 'pass_expired', 'Pass expired'
        PASS_SUSPENDED = 'pass_suspended', 'Pass suspended'
        PASS_RESTORED = 'pass_restored', 'Pass restored'
        PASS_CANCELLED = 'pass_cancelled', 'Pass cancelled'
        REFUND_PROCESSED = 'refund_processed', 'Refund processed'
        TOKEN_MINTED = 'token_minted', 'Verification token minted'
        REDEMPTION_CREATED = 'redemption_created', 'Redemption created'
        REDEMPTION_VOIDED = 'redemption_voided', 'Redemption voided'
        NOTIFICATION_SENT = 'notification_sent', 'Notification sent'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE,
        related_name='coffee_pass_audit_events',
    )
    location = models.ForeignKey(
        'accounts.Location', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='coffee_pass_audit_events',
    )
    action = models.CharField(max_length=30, choices=Action.choices, db_index=True)
    entity_type = models.CharField(max_length=50)
    entity_id = models.UUIDField(null=True, blank=True, db_index=True)

    actor = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='coffee_pass_audit_events',
    )
    #: Set for customer-driven public actions (no dashboard user involved).
    actor_customer = models.ForeignKey(
        'crm.CRMCustomer', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='coffee_pass_audit_events',
    )
    #: Correlates one request across audit rows. Never contains PII.
    correlation_id = models.CharField(max_length=64, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_hash = models.CharField(max_length=64, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'coffee_pass_audit_events'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', '-created_at']),
            models.Index(fields=['organization', 'action', '-created_at']),
            models.Index(fields=['entity_type', 'entity_id']),
        ]

    def __str__(self):
        return f'{self.action} · {self.entity_type}:{self.entity_id}'

    def save(self, *args, **kwargs):
        if self.pk is not None and CoffeePassAuditEvent.objects.filter(pk=self.pk).exists():
            raise ValueError('CoffeePassAuditEvent is append-only; updates are not allowed.')
        super().save(*args, **kwargs)


# ──────────────────────────────────────────────────────────────────────
# Transactional outbox
# ──────────────────────────────────────────────────────────────────────
class CoffeePassOutboxEvent(models.Model):
    """
    Notification/analytics intent written in the SAME transaction as the domain
    mutation, delivered later by Celery.

    Why: a WhatsApp send must never roll back a payment or a redemption, and a
    broker outage must never silently lose the intent to notify.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE,
        related_name='coffee_pass_outbox_events',
    )
    event_type = models.CharField(max_length=40, db_index=True)
    aggregate_type = models.CharField(max_length=40)
    aggregate_id = models.UUIDField(null=True, blank=True, db_index=True)
    #: Minimal, privacy-safe payload — ids and amounts, never comments or PII.
    payload = models.JSONField(default=dict, blank=True)

    #: Unique delivery intent — a retry can never send twice.
    idempotency_key = models.CharField(max_length=120, unique=True)

    status = models.CharField(
        max_length=10, choices=OutboxStatus.choices,
        default=OutboxStatus.PENDING, db_index=True,
    )
    attempt_count = models.PositiveSmallIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'coffee_pass_outbox_events'
        ordering = ['available_at']
        indexes = [
            models.Index(fields=['status', 'available_at']),
            models.Index(fields=['organization', 'event_type']),
        ]

    def __str__(self):
        return f'{self.event_type} · {self.status} (try {self.attempt_count})'
