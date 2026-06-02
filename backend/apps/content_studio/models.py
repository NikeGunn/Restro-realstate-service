"""
AI Content Studio models (Phase 5).

A structured AI-image tool: each `ContentUseCase` is a form whose inputs feed a
`ContentPromptTemplate` to build a high-quality prompt (never a blank box). All
tables prefixed `studio_`, UUID PKs. Provider model IDs are NEVER hardcoded —
they default from settings and can be overridden per template (REQUIREMENTS § 0 #7).

Image binaries are stored in Django's default storage (S3 when
USE_OBJECT_STORAGE=true) — never a provider temp URL, which expires ~1h.
"""
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.accounts.models import Organization, User


class _StudioTimestamps(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ──────────────────────────────────────────────────────────────────────
# Use case (seeded, not user-created)
# ──────────────────────────────────────────────────────────────────────
class ContentUseCase(_StudioTimestamps):
    """A structured creative use case (e.g. "Offer Discount Poster").

    `required_fields` / `optional_fields` are JSON lists of field defs:
        {"key": "...", "label": "...", "type": "text|textarea|select|number|
                 image_upload|checkbox", "max_length": 100, "choices": [...]}
    """
    use_case_key = models.SlugField(max_length=64, unique=True)
    display_name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=64, default='image', help_text='lucide icon name')
    required_fields = models.JSONField(default=list, blank=True)
    optional_fields = models.JSONField(default=list, blank=True)
    supported_formats = models.JSONField(
        default=list, blank=True,
        help_text='Allowed aspects, e.g. ["square", "portrait", "landscape"].',
    )
    credit_cost = models.PositiveIntegerField(default=1)
    active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'studio_use_cases'
        ordering = ['sort_order', 'display_name']
        indexes = [models.Index(fields=['active', 'sort_order'])]

    def __str__(self):
        return self.display_name


# ──────────────────────────────────────────────────────────────────────
# Brand kit (one per org)
# ──────────────────────────────────────────────────────────────────────
class BrandKit(_StudioTimestamps):
    class Watermark(models.TextChoices):
        NONE = 'none', 'None'
        LOGO = 'logo', 'Logo'
        TEXT = 'text', 'Text'

    organization = models.OneToOneField(
        Organization, on_delete=models.CASCADE, related_name='brand_kit',
    )
    restaurant_name = models.CharField(max_length=200, blank=True)
    logo = models.ImageField(upload_to='brand_kits/', max_length=300, blank=True, null=True)
    brand_colors = models.JSONField(default=list, blank=True, help_text='List of hex colors.')
    preferred_language = models.CharField(max_length=10, default='zh-TW')
    default_cta = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    whatsapp = models.CharField(max_length=40, blank=True)
    address = models.CharField(max_length=255, blank=True)
    website_url = models.URLField(blank=True)
    social_handles = models.JSONField(default=dict, blank=True)
    watermark_preference = models.CharField(
        max_length=10, choices=Watermark.choices, default=Watermark.NONE,
    )
    style_preferences = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'studio_brand_kits'

    def __str__(self):
        return f'BrandKit({self.restaurant_name or self.organization.name})'

    def snapshot(self) -> dict:
        """Immutable copy frozen onto each job, so later brand-kit edits never
        retroactively change a past generation's provenance."""
        return {
            'restaurant_name': self.restaurant_name,
            'brand_colors': self.brand_colors,
            'preferred_language': self.preferred_language,
            'default_cta': self.default_cta,
            'phone': self.phone,
            'whatsapp': self.whatsapp,
            'address': self.address,
            'website_url': self.website_url,
            'social_handles': self.social_handles,
            'watermark_preference': self.watermark_preference,
            'style_preferences': self.style_preferences,
            'logo': self.logo.name if self.logo else '',
        }


# ──────────────────────────────────────────────────────────────────────
# Prompt template (admin-managed, one per use case) — prompts live HERE
# ──────────────────────────────────────────────────────────────────────
class ContentPromptTemplate(_StudioTimestamps):
    use_case = models.OneToOneField(
        ContentUseCase, on_delete=models.CASCADE, related_name='prompt_template',
    )
    prompt_template = models.TextField(help_text='Uses {{field_key}} placeholders.')
    negative_prompt = models.TextField(blank=True)
    system_instructions = models.TextField(blank=True)
    # Empty = fall back to CONTENT_STUDIO settings (config-driven, no hardcoded IDs).
    provider = models.CharField(max_length=64, blank=True)
    model = models.CharField(max_length=64, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = 'studio_prompt_templates'

    def __str__(self):
        return f'Template({self.use_case.use_case_key} v{self.version})'

    def resolved_provider(self) -> str:
        return self.provider or settings.CONTENT_STUDIO['DEFAULT_PROVIDER']

    def resolved_model(self) -> str:
        return self.model or settings.CONTENT_STUDIO['IMAGE_MODEL_QUALITY']


# ──────────────────────────────────────────────────────────────────────
# Generation job
# ──────────────────────────────────────────────────────────────────────
class ContentGenerationJob(_StudioTimestamps):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        QUEUED = 'queued', 'Queued'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        BLOCKED_BY_CAP = 'blocked_by_cap', 'Blocked by Spend Cap'
        CANCELLED = 'cancelled', 'Cancelled'
        REFUNDED = 'refunded', 'Refunded'

    class Aspect(models.TextChoices):
        SQUARE = 'square', 'Square'
        PORTRAIT = 'portrait', 'Portrait'
        LANDSCAPE = 'landscape', 'Landscape'

    # Terminal states never transition again — guards in save().
    TERMINAL_STATES = {'completed', 'failed', 'cancelled', 'refunded'}

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='content_jobs',
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='content_jobs',
    )
    use_case = models.ForeignKey(
        ContentUseCase, on_delete=models.PROTECT, related_name='jobs',
    )
    brand_kit_snapshot = models.JSONField(default=dict, blank=True)
    input_payload = models.JSONField(default=dict, blank=True)
    generated_prompt = models.TextField(blank=True)
    negative_prompt = models.TextField(blank=True)
    provider = models.CharField(max_length=64, blank=True)
    model = models.CharField(max_length=64, blank=True)
    output_resolution = models.CharField(max_length=12, default='1024x1024')
    aspect = models.CharField(max_length=12, choices=Aspect.choices, default=Aspect.SQUARE)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT,
    )
    credits_estimated = models.PositiveIntegerField(default=1)
    credits_used = models.PositiveIntegerField(null=True, blank=True)
    cost_estimated_usd = models.DecimalField(max_digits=10, decimal_places=6, default=Decimal('0'))
    cost_actual_usd = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    output_count = models.PositiveIntegerField(default=0)
    idempotency_key = models.CharField(max_length=64, unique=True)
    # FK to billing.UsageEvent kept as a nullable UUID (no hard dependency on the
    # billing app, which lands in Phase 6). Stored as the event id when reserved.
    usage_event_id = models.UUIDField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'studio_generation_jobs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', '-created_at']),
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f'Job({self.use_case_id} {self.status})'


# ──────────────────────────────────────────────────────────────────────
# Generation output (the stored image)
# ──────────────────────────────────────────────────────────────────────
class ContentGenerationOutput(_StudioTimestamps):
    job = models.ForeignKey(
        ContentGenerationJob, on_delete=models.CASCADE, related_name='outputs',
    )
    # Paths embed org + job UUIDs, so the default max_length=100 is too short.
    asset = models.ImageField(
        upload_to='content_studio/', max_length=300, blank=True, null=True,
    )
    thumbnail = models.ImageField(
        upload_to='content_studio/thumbs/', max_length=300, blank=True, null=True,
    )
    file_type = models.CharField(max_length=20, blank=True)
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    format = models.CharField(max_length=12, blank=True)
    provider_asset_id = models.CharField(max_length=200, blank=True)
    download_count = models.PositiveIntegerField(default=0)
    is_favorite = models.BooleanField(default=False)

    class Meta:
        db_table = 'studio_generation_outputs'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['job', 'created_at']),
        ]

    def __str__(self):
        return f'Output({self.job_id} {self.width}x{self.height})'
