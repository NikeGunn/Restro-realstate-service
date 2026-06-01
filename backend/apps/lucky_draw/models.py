"""
Lucky Draw models (Phase 2).

QR-code lucky-draw campaigns that reward customers with a random discount while
capturing CRM-ready, consent-recorded leads — then deliver the prize over
WhatsApp and let sharing earn bonus odds.

Conventions (REQUIREMENTS.md § Phase 2 / Cross-Cutting):
- All PKs are UUID. `organization` FK CASCADEs. Cross-app FKs use string refs.
- Tables prefixed `lucky_draw_`.
- LuckyDrawEntry core facts are APPEND-ONLY (save() blocks edits except a
  whitelist of status-transition columns via update_fields).
- Denormalized prize counters (wins_today_count / wins_total_count) so daily/
  total limit checks never COUNT the entry table on every spin; they're bumped
  with F() inside the same transaction as the draw.
- DB-level constraints (unique coupon_code / referral_token / url_token) and
  covering indexes for every hot lookup.

⚠️ This is NOT the `coupons` app. `coupons` grants PLAN TIERS to organizations.
Lucky Draw's coupon_code is a CUSTOMER DISCOUNT CODE and lives entirely here.
"""
import uuid

from django.db import models

from apps.messaging.models import LanguageChoice


# ──────────────────────────────────────────────────────────────────────
# Choice enums
# ──────────────────────────────────────────────────────────────────────
class CampaignStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    ACTIVE = 'active', 'Active'
    PAUSED = 'paused', 'Paused'
    ENDED = 'ended', 'Ended'


class EntryStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    DRAWN = 'drawn', 'Drawn'
    REDEEMED = 'redeemed', 'Redeemed'
    EXPIRED = 'expired', 'Expired'
    INVALID = 'invalid', 'Invalid'


class ReferralBonusType(models.TextChoices):
    EXTRA_ENTRY = 'extra_entry', 'Extra Entry'
    BETTER_ODDS = 'better_odds', 'Better Odds'


# ──────────────────────────────────────────────────────────────────────
# Campaign
# ──────────────────────────────────────────────────────────────────────
class LuckyDrawCampaign(models.Model):
    """A configurable lucky-draw campaign owned by one organization."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE,
        related_name='lucky_draw_campaigns',
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=10, choices=CampaignStatus.choices, default=CampaignStatus.DRAFT,
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)  # null = no end

    # Per-customer entry limits (HARD per phone).
    daily_entry_limit_per_customer = models.PositiveIntegerField(default=1)
    total_entry_limit_per_customer = models.PositiveIntegerField(null=True, blank=True)  # null = ∞

    # Which form fields the public entry page requires.
    requires_name = models.BooleanField(default=True)
    requires_phone = models.BooleanField(default=True)
    requires_email = models.BooleanField(default=False)

    consent_text = models.TextField()
    privacy_notice_text = models.TextField(blank=True)
    default_language = models.CharField(
        max_length=10, choices=LanguageChoice.choices, default=LanguageChoice.TRADITIONAL_CHINESE,
    )

    # 🇭🇰 loops
    deliver_coupon_via_whatsapp = models.BooleanField(default=True)
    referral_enabled = models.BooleanField(default=True)
    referral_bonus_type = models.CharField(
        max_length=12, choices=ReferralBonusType.choices, default=ReferralBonusType.EXTRA_ENTRY,
    )
    coupon_validity_days = models.PositiveIntegerField(default=14)

    # Optional: tag redeemers as buffet_customer when the coupon is redeemed.
    tag_redeemers_as_buffet = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'lucky_draw_campaigns'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['organization', '-created_at']),
        ]

    def __str__(self):
        return f"{self.name} ({self.status})"


# ──────────────────────────────────────────────────────────────────────
# Prize
# ──────────────────────────────────────────────────────────────────────
class LuckyDrawPrize(models.Model):
    """
    A discount tier in a campaign. Probability ∝ weight / Σweights.

    wins_today_count / wins_total_count are denormalized counters updated
    atomically (F()) in the same transaction as the draw, so limit checks don't
    COUNT the entries table on every spin. wins_today_count is zeroed daily.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(
        LuckyDrawCampaign, on_delete=models.CASCADE, related_name='prizes',
    )
    label = models.CharField(max_length=100, blank=True)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2)  # 0.01–100
    weight = models.PositiveIntegerField()
    max_wins_per_day = models.PositiveIntegerField(null=True, blank=True)  # null = ∞
    max_total_wins = models.PositiveIntegerField(null=True, blank=True)    # null = ∞
    wins_today_count = models.PositiveIntegerField(default=0)
    wins_total_count = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'lucky_draw_prizes'
        ordering = ['-weight', '-discount_percent']
        indexes = [models.Index(fields=['campaign', 'active'])]
        constraints = [
            models.CheckConstraint(
                check=models.Q(discount_percent__gt=0) & models.Q(discount_percent__lte=100),
                name='lucky_draw_prize_discount_range',
            ),
        ]

    def __str__(self):
        return self.label or f"{self.discount_percent}% off"

    def has_daily_headroom(self):
        return self.max_wins_per_day is None or self.wins_today_count < self.max_wins_per_day

    def has_total_headroom(self):
        return self.max_total_wins is None or self.wins_total_count < self.max_total_wins


# ──────────────────────────────────────────────────────────────────────
# Entry (APPEND-ONLY core facts)
# ──────────────────────────────────────────────────────────────────────
#: Columns a status transition is allowed to touch via update_fields after the
#: entry's immutable core facts are written.
ENTRY_MUTABLE_FIELDS = {
    'status', 'prize', 'coupon_code', 'whatsapp_sent_at', 'reminder_sent_at',
    'referral_count', 'referred_by_entry', 'drawn_at', 'expires_at',
    'redeemed_at', 'redeemed_by', 'crm_customer',
}


class LuckyDrawEntry(models.Model):
    """
    A single lucky-draw entry. Core facts (who/when/consent/referral lineage)
    are append-only; only whitelisted status-transition columns may be updated,
    and only via save(update_fields=...).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(
        LuckyDrawCampaign, on_delete=models.CASCADE, related_name='entries',
    )
    crm_customer = models.ForeignKey(
        'crm.CRMCustomer', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='lucky_draw_entries',
    )
    customer_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    table_number = models.CharField(max_length=20, blank=True)
    consent_given = models.BooleanField(default=False)
    ip_address_hashed = models.CharField(max_length=64, blank=True)
    user_agent_hash = models.CharField(max_length=64, blank=True)

    prize = models.ForeignKey(
        LuckyDrawPrize, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='entries',
    )
    coupon_code = models.CharField(max_length=20, unique=True, null=True, blank=True)
    status = models.CharField(
        max_length=10, choices=EntryStatus.choices, default=EntryStatus.PENDING,
    )

    # 🇭🇰 referral loop
    referred_by_entry = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='referrals',
    )
    referral_token = models.CharField(max_length=32, unique=True, null=True, blank=True)
    referral_count = models.PositiveIntegerField(default=0)

    whatsapp_sent_at = models.DateTimeField(null=True, blank=True)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    entered_at = models.DateTimeField(auto_now_add=True)
    drawn_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    redeemed_at = models.DateTimeField(null=True, blank=True)
    redeemed_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='lucky_draw_redemptions',
    )

    class Meta:
        db_table = 'lucky_draw_entries'
        ordering = ['-entered_at']
        indexes = [
            models.Index(fields=['campaign', 'phone', 'entered_at']),
            models.Index(fields=['campaign', 'ip_address_hashed', 'entered_at']),
            models.Index(fields=['coupon_code']),
            models.Index(fields=['referral_token']),
            models.Index(fields=['campaign', 'status']),
            models.Index(fields=['status', 'expires_at']),
        ]

    def __str__(self):
        return f"{self.customer_name} · {self.coupon_code or self.status}"

    def save(self, *args, **kwargs):
        """
        Append-only for core facts. On the first write (no pk yet) anything goes.
        On subsequent writes the caller MUST pass update_fields, and every field
        named must be in the mutable whitelist — protecting the immutable lineage
        (who entered, when, consent, referral source) from tampering.
        """
        if self._state.adding:
            return super().save(*args, **kwargs)

        update_fields = kwargs.get('update_fields')
        if update_fields is None:
            raise ValueError(
                "LuckyDrawEntry core facts are append-only; updates must pass "
                "update_fields restricted to status-transition columns."
            )
        illegal = set(update_fields) - ENTRY_MUTABLE_FIELDS
        if illegal:
            raise ValueError(
                f"LuckyDrawEntry fields {sorted(illegal)} are immutable."
            )
        return super().save(*args, **kwargs)


# ──────────────────────────────────────────────────────────────────────
# QR Code
# ──────────────────────────────────────────────────────────────────────
class LuckyDrawQRCode(models.Model):
    """A scannable QR code that routes to the public entry page for a campaign."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(
        LuckyDrawCampaign, on_delete=models.CASCADE, related_name='qr_codes',
    )
    label = models.CharField(max_length=100, blank=True)
    qr_image = models.ImageField(upload_to='lucky_draw/qr/', null=True, blank=True)
    poster_image = models.ImageField(upload_to='lucky_draw/posters/', null=True, blank=True)
    url_token = models.CharField(max_length=64, unique=True)
    scan_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'lucky_draw_qr_codes'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['url_token'])]

    def __str__(self):
        return self.label or str(self.url_token)
