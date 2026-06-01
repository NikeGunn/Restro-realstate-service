"""
CRM Lite models (Phase 1).

A consent-compliant customer database that auto-populates from every touchpoint
(bookings, chatbot, WhatsApp, Instagram, manual, lucky draw, wifi, walk-in).

Conventions (REQUIREMENTS.md § Phase 1 / Database):
- All PKs are UUID. All `organization` FKs CASCADE and use string refs.
- Tables prefixed `crm_`.
- Append-only models (CRMInteraction, CRMConsent) block updates in save().
- DB-level constraints (partial unique, indexes) over app-only validation.
- Denormalized `birthday_month` / `visit_count` for index-friendly segments.
"""
import uuid

from django.db import models

from apps.messaging.models import LanguageChoice


# ──────────────────────────────────────────────────────────────────────
# Choice enums
# ──────────────────────────────────────────────────────────────────────
class CustomerSource(models.TextChoices):
    BOOKING = 'booking', 'Booking'
    CHATBOT = 'chatbot', 'Chatbot'
    WHATSAPP = 'whatsapp', 'WhatsApp'
    INSTAGRAM = 'instagram', 'Instagram'
    MESSENGER = 'messenger', 'Messenger (not yet wired)'  # forward-compat enum value only
    MANUAL = 'manual', 'Manual'
    LUCKY_DRAW = 'lucky_draw', 'Lucky Draw'
    WIFI = 'wifi', 'WiFi'
    WALK_IN = 'walk_in', 'Walk-in'
    IMPORT = 'import', 'Import'


class ConsentStatus(models.TextChoices):
    NOT_ASKED = 'not_asked', 'Not Asked'
    GIVEN = 'given', 'Given'
    REFUSED = 'refused', 'Refused'
    WITHDRAWN = 'withdrawn', 'Withdrawn'


class Gender(models.TextChoices):
    MALE = 'male', 'Male'
    FEMALE = 'female', 'Female'
    OTHER = 'other', 'Other'
    PREFER_NOT_TO_SAY = 'prefer_not_to_say', 'Prefer not to say'


class InteractionType(models.TextChoices):
    BOOKING = 'booking', 'Booking'
    CHATBOT_MESSAGE = 'chatbot_message', 'Chatbot Message'
    WHATSAPP_MESSAGE = 'whatsapp_message', 'WhatsApp Message'
    INSTAGRAM_MESSAGE = 'instagram_message', 'Instagram Message'
    MESSENGER_MESSAGE = 'messenger_message', 'Messenger Message (not yet wired)'
    PHONE_CALL = 'phone_call', 'Phone Call'
    WALK_IN = 'walk_in', 'Walk-in'
    LUCKY_DRAW_ENTRY = 'lucky_draw_entry', 'Lucky Draw Entry'
    WIFI_SIGNIN = 'wifi_signin', 'WiFi Sign-in'
    MANUAL_NOTE = 'manual_note', 'Manual Note'
    COUPON_REDEEMED = 'coupon_redeemed', 'Coupon Redeemed'
    WHATSAPP_COUPON_SENT = 'whatsapp_coupon_sent', 'WhatsApp Coupon Sent'


class ConsentSource(models.TextChoices):
    BOOKING_FORM = 'booking_form', 'Booking Form'
    LUCKY_DRAW_FORM = 'lucky_draw_form', 'Lucky Draw Form'
    WIFI_FORM = 'wifi_form', 'WiFi Form'
    CHATBOT = 'chatbot', 'Chatbot'
    MANUAL = 'manual', 'Manual'
    IMPORT = 'import', 'Import'


# ──────────────────────────────────────────────────────────────────────
# Customer
# ──────────────────────────────────────────────────────────────────────
class CRMCustomer(models.Model):
    """A unified customer profile, deduplicated per org by phone then email."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='crm_customers'
    )
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=30, blank=True, null=True)
    phone_raw = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True, null=True)
    whatsapp_number = models.CharField(max_length=30, blank=True, null=True)
    birthday = models.DateField(blank=True, null=True)
    birthday_month = models.PositiveSmallIntegerField(blank=True, null=True, db_index=True)
    gender = models.CharField(max_length=20, choices=Gender.choices, blank=True)
    preferred_language = models.CharField(
        max_length=10, choices=LanguageChoice.choices, blank=True
    )
    source = models.CharField(max_length=20, choices=CustomerSource.choices)
    notes = models.TextField(blank=True)
    last_visit_date = models.DateField(blank=True, null=True)
    last_interaction_at = models.DateTimeField(null=True, blank=True)
    visit_count = models.PositiveIntegerField(default=0)
    marketing_consent_status = models.CharField(
        max_length=20, choices=ConsentStatus.choices, default=ConsentStatus.NOT_ASKED
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'crm_customers'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'phone'],
                condition=models.Q(phone__isnull=False) & ~models.Q(phone=''),
                name='uniq_crm_org_phone',
            ),
            models.UniqueConstraint(
                fields=['organization', 'email'],
                condition=models.Q(email__isnull=False) & ~models.Q(email=''),
                name='uniq_crm_org_email',
            ),
        ]
        indexes = [
            models.Index(fields=['organization', 'marketing_consent_status']),
            models.Index(fields=['organization', 'source']),
            models.Index(fields=['organization', 'birthday_month']),
            models.Index(fields=['organization', 'last_visit_date']),
        ]

    def __str__(self):
        return f"{self.name} ({self.phone or self.email or 'no-contact'})"

    def save(self, *args, **kwargs):
        # Normalize on save: E.164 phone, lowercase email, derive birthday_month,
        # default whatsapp. Phone normalization here means direct API creates get
        # the same E.164 treatment as the service path.
        if self.phone:
            from .services.customer_service import normalize_phone
            if not self.phone_raw:
                self.phone_raw = self.phone
            self.phone = normalize_phone(self.phone)
        if self.email:
            self.email = self.email.strip().lower() or None
        self.birthday_month = self.birthday.month if self.birthday else None
        if not self.whatsapp_number and self.phone:
            self.whatsapp_number = self.phone
        super().save(*args, **kwargs)


# ──────────────────────────────────────────────────────────────────────
# Tags
# ──────────────────────────────────────────────────────────────────────
class CRMTag(models.Model):
    """A label applied to customers. System tags are auto-seeded and protected."""
    SYSTEM_TAGS = (
        'lucky_draw_lead', 'wifi_lead', 'buffet_customer', 'frequent_customer',
        'vip', 'inactive_customer', 'birthday_this_month',
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='crm_tags'
    )
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=7, default='#6366F1')
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'crm_tags'
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'name'], name='uniq_crm_org_tag_name'
            ),
        ]

    def __str__(self):
        return self.name


class CRMCustomerTag(models.Model):
    """Through model linking customers to tags."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        CRMCustomer, on_delete=models.CASCADE, related_name='customer_tags'
    )
    tag = models.ForeignKey(
        CRMTag, on_delete=models.CASCADE, related_name='customer_tags'
    )
    added_at = models.DateTimeField(auto_now_add=True)
    added_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        db_table = 'crm_customer_tags'
        constraints = [
            models.UniqueConstraint(
                fields=['customer', 'tag'], name='uniq_crm_customer_tag'
            ),
        ]
        indexes = [models.Index(fields=['tag', 'customer'])]

    def __str__(self):
        return f"{self.customer_id} · {self.tag_id}"


# ──────────────────────────────────────────────────────────────────────
# Interactions (APPEND-ONLY)
# ──────────────────────────────────────────────────────────────────────
class CRMInteraction(models.Model):
    """An append-only log of touchpoints with a customer."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='crm_interactions'
    )
    customer = models.ForeignKey(
        CRMCustomer, on_delete=models.CASCADE, related_name='interactions'
    )
    interaction_type = models.CharField(max_length=30, choices=InteractionType.choices)
    source_channel = models.CharField(max_length=20, blank=True)
    summary = models.TextField(max_length=500, blank=True)
    related_entity_type = models.CharField(max_length=50, blank=True)
    related_entity_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        db_table = 'crm_interactions'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['customer', '-created_at'])]

    def __str__(self):
        return f"{self.interaction_type} · {self.customer_id}"

    def save(self, *args, **kwargs):
        if self.pk is not None and CRMInteraction.objects.filter(pk=self.pk).exists():
            raise ValueError("CRMInteraction is append-only; updates are not allowed.")
        super().save(*args, **kwargs)


# ──────────────────────────────────────────────────────────────────────
# Consent (APPEND-ONLY & IMMUTABLE)
# ──────────────────────────────────────────────────────────────────────
class CRMConsent(models.Model):
    """
    An append-only, immutable consent record. A withdrawal is a NEW row with
    consent_given=False — never an edit. The customer's marketing_consent_status
    is recomputed from the latest row by a signal.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='crm_consent_records'
    )
    customer = models.ForeignKey(
        CRMCustomer, on_delete=models.CASCADE, related_name='consent_records'
    )
    consent_given = models.BooleanField()
    consent_source = models.CharField(max_length=20, choices=ConsentSource.choices)
    consent_text_snapshot = models.TextField()
    consent_text_version = models.CharField(max_length=20)
    marketing_channels_allowed = models.JSONField(default=list, blank=True)
    opt_out_timestamp = models.DateTimeField(null=True, blank=True)
    privacy_notice_version = models.CharField(max_length=20, blank=True)
    ip_address_hashed = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'crm_consent_records'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['customer', '-created_at'])]

    def __str__(self):
        return f"consent={self.consent_given} · {self.customer_id}"

    def save(self, *args, **kwargs):
        if self.pk is not None and CRMConsent.objects.filter(pk=self.pk).exists():
            raise ValueError("CRMConsent is append-only & immutable; updates are not allowed.")
        super().save(*args, **kwargs)


# ──────────────────────────────────────────────────────────────────────
# Segments
# ──────────────────────────────────────────────────────────────────────
class CRMSegment(models.Model):
    """A saved, rule-based customer filter (DSL compiled to a Django Q)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='crm_segments'
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    filter_rules = models.JSONField(default=dict)
    customer_count = models.IntegerField(default=0)
    is_dynamic = models.BooleanField(default=True)
    last_evaluated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'crm_segments'
        ordering = ['name']
        indexes = [models.Index(fields=['organization'])]

    def __str__(self):
        return self.name
