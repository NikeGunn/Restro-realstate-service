"""
Django settings for AI Business Chat Platform.
"""
import os
from pathlib import Path
from datetime import timedelta

import dj_database_url
from decouple import config

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY', default='django-insecure-dev-key-change-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=True, cast=bool)

# Allow all hosts in development, or specific hosts from env in production
if DEBUG:
    ALLOWED_HOSTS = ['*']
else:
    ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1').split(',')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third party
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'django_filters',
    'drf_spectacular',
    'django_celery_beat',
    'django_celery_results',
    
    # Local apps
    'apps.common',  # Phase 0: shared mixins/permissions/throttles/idempotency/storage
    'apps.accounts',
    'apps.messaging',
    'apps.ai_engine',
    'apps.handoff',
    'apps.knowledge',
    'apps.analytics',
    'apps.widget',
    'apps.channels',  # Phase 4: WhatsApp & Instagram
    'apps.coupons',
    # Vertical apps
    'apps.restaurant',
    'apps.realestate',
    # Inventory (Plane B — admin-only, sealed from public chatbot)
    'apps.inventory',
    # CRM Lite (Phase 1) — consent-compliant customer database
    'apps.crm',
    # Lucky Draw (Phase 2) — QR lead capture + WhatsApp delivery + referral loop
    'apps.lucky_draw',
    # AI Content Studio (Phase 5) — structured AI image generation
    'apps.content_studio',
    # AI Credit & Usage Billing (Phase 6) — credit wallet + usage ledger + spend cap
    'apps.billing',
    # Payments — Stripe Checkout for AI credit-pack purchases (tops up Phase 6)
    'apps.payments',
    # Coffee Pass — paid 30-day customer membership (customer money, not org money)
    'apps.coffee_pass',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database
DATABASE_URL = config('DATABASE_URL', default='sqlite:///db.sqlite3')
DATABASES = {
    'default': dj_database_url.parse(DATABASE_URL)
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Custom User Model
AUTH_USER_MODEL = 'accounts.User'

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
# Project-level static dir (holds the embeddable widget.js). Without this in
# STATICFILES_DIRS, collectstatic's finders only look inside each app's
# static/ subdir and silently skip backend/static/widget.js — which made
# /api/v1/widget/widget.js serve the 85-byte "file not found" stub in prod.
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ──────────────────────────────────────────────────────────────────────
# Object storage (Phase 0) — OPT-IN, OFF by default.
#
# Default (dev + current prod): Django's FileSystemStorage writing to the
# media-pvc. Setting USE_OBJECT_STORAGE=true (env) flips every ImageField/
# FileField to an S3-compatible bucket (Tencent COS ap-hongkong / Cloudflare
# R2) via django-storages — with ZERO model changes. That is the prerequisite
# for raising backend `replicas` past 1 (the RWO media-pvc can't be multi-mounted).
#
# Non-secret S3 config (bucket, endpoint, region, CDN) belongs in
# k8s/configmap.yaml; the secret keys (S3_ACCESS_KEY_ID / S3_SECRET_ACCESS_KEY)
# are GitHub Secrets that must ALSO be wired into the deploy.yml deploy-secrets
# job before they reach the cluster (deferred until a bucket is provisioned).
# ──────────────────────────────────────────────────────────────────────
USE_OBJECT_STORAGE = config('USE_OBJECT_STORAGE', default=False, cast=bool)
if USE_OBJECT_STORAGE:
    STORAGES = {
        'default': {'BACKEND': 'storages.backends.s3.S3Storage'},
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'
        },
    }
    AWS_STORAGE_BUCKET_NAME = config('S3_BUCKET', default='')
    AWS_S3_ENDPOINT_URL = config('S3_ENDPOINT_URL', default=None)   # COS / R2 endpoint
    AWS_S3_REGION_NAME = config('S3_REGION', default='auto')        # 'ap-hongkong' (COS) | 'auto' (R2)
    AWS_S3_CUSTOM_DOMAIN = config('S3_CDN_DOMAIN', default=None)    # CDN domain for serving
    AWS_ACCESS_KEY_ID = config('S3_ACCESS_KEY_ID', default='')
    AWS_SECRET_ACCESS_KEY = config('S3_SECRET_ACCESS_KEY', default='')
    AWS_QUERYSTRING_AUTH = config('S3_SIGNED_URLS', default=True, cast=bool)
    AWS_S3_FILE_OVERWRITE = False
# else: FileSystemStorage (Django default) + media-pvc — unchanged.

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    # Phase 0: throttle scopes for unauthenticated public endpoints (lucky-draw etc.).
    # Authenticated views are unaffected (no default throttle class is set globally).
    'DEFAULT_THROTTLE_RATES': {
        'public_burst': '60/min',       # GET campaign config etc.
        'public_sustained': '600/hour',
        'public_form': '10/min',        # POST lucky-draw entry — anti-abuse
        'payments_checkout': '20/min',  # POST create-checkout-session — anti-abuse (authed)
    },
}

# JWT Settings
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# CORS Settings
# In production, use specific origins. In dev, allow all for easier testing.
CORS_ALLOW_ALL_ORIGINS = config('CORS_ALLOW_ALL_ORIGINS', default=DEBUG, cast=bool)

# If not allowing all origins, use specific origins list
if not CORS_ALLOW_ALL_ORIGINS:
    CORS_ALLOWED_ORIGINS = config(
        'CORS_ALLOWED_ORIGINS',
        default='http://localhost:3000,http://127.0.0.1:3000,http://localhost:8080,http://127.0.0.1:8080,https://kribaat.com,https://www.kribaat.com'
    ).split(',')
    # Clean up whitespace
    CORS_ALLOWED_ORIGINS = [origin.strip() for origin in CORS_ALLOWED_ORIGINS if origin.strip()]
else:
    CORS_ALLOWED_ORIGINS = []

# Allow credentials for authenticated requests
CORS_ALLOW_CREDENTIALS = True

# Allow specific headers
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

# CSRF Settings for HTTPS
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='https://kribaat.com,https://www.kribaat.com,http://localhost:3000,http://127.0.0.1:3000'
).split(',')
# Clean up whitespace
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in CSRF_TRUSTED_ORIGINS if origin.strip()]

# For API-only endpoints, we can use session auth exemption
# But we still want CSRF protection for authenticated endpoints using sessions
CSRF_COOKIE_HTTPONLY = False  # Allow JavaScript to read CSRF token
CSRF_COOKIE_SAMESITE = 'Lax'  # Changed from 'Strict' for cross-origin requests
CSRF_COOKIE_SECURE = not DEBUG  # Only send cookie over HTTPS in production

# Celery Configuration
CELERY_BROKER_URL = config('REDIS_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = 'django-db'
CELERY_CACHE_BACKEND = 'django-cache'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# Periodic tasks. crontab(hour=2, minute=15) runs nightly at 02:15 UTC.
from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    # ── Coffee Pass ──────────────────────────────────────────────────
    # Expiry is housekeeping: entitlement checks already refuse an
    # out-of-window pass at query time, so a late run cannot let anyone redeem.
    'coffee-pass-expire': {
        'task': 'apps.coffee_pass.tasks.expire_passes_task',
        'schedule': crontab(minute='*/15'),
    },
    # Notification delivery. Retries with backoff; never blocks a payment.
    'coffee-pass-outbox': {
        'task': 'apps.coffee_pass.tasks.process_outbox_task',
        'schedule': crontab(minute='*/10'),
    },
    # Recovers payments whose webhook never arrived (deploy window/network blip).
    'coffee-pass-reconcile': {
        'task': 'apps.coffee_pass.tasks.reconcile_purchases_task',
        'schedule': crontab(minute=5),
    },
    # Queues 3-day reminders; consent + quality are re-checked at SEND time.
    'coffee-pass-expiry-reminders': {
        'task': 'apps.coffee_pass.tasks.send_expiry_reminders_task',
        'schedule': crontab(hour=9, minute=30),
    },
    'coffee-pass-purge-tokens': {
        'task': 'apps.coffee_pass.tasks.purge_expired_tokens_task',
        'schedule': crontab(hour=3, minute=40),
    },
    'coffee-pass-anomalies': {
        'task': 'apps.coffee_pass.tasks.detect_anomalies_task',
        'schedule': crontab(hour=7, minute=30),
    },

    'downgrade-expired-plans-daily': {
        'task': 'coupons.downgrade_expired_plans',
        'schedule': crontab(hour=2, minute=15),
    },
    'inventory-daily-summary': {
        'task': 'apps.inventory.tasks.generate_daily_inventory_summary_task',
        'schedule': crontab(hour=8, minute=0),
    },
    'inventory-expiry-check': {
        'task': 'apps.inventory.tasks.check_expiry_task',
        'schedule': crontab(hour=7, minute=0),
    },
    'inventory-weekly-insights': {
        'task': 'apps.inventory.tasks.generate_weekly_insights_task',
        'schedule': crontab(hour=8, minute=0, day_of_week='monday'),
    },
    'inventory-ai-profile-refresh': {
        'task': 'apps.inventory.tasks.refresh_inventory_ai_profiles_task',
        'schedule': crontab(hour=3, minute=0),
    },
    # CRM Lite (Phase 1)
    'crm-refresh-segment-counts': {
        'task': 'apps.crm.tasks.refresh_segment_counts_task',
        'schedule': crontab(hour=2, minute=0),
    },
    'crm-refresh-birthday-tag': {
        'task': 'apps.crm.tasks.refresh_birthday_tag_task',
        'schedule': crontab(hour=0, minute=30),
    },
    'crm-refresh-inactive-tag': {
        'task': 'apps.crm.tasks.refresh_inactive_tag_task',
        'schedule': crontab(hour=1, minute=0),
    },
    # Lucky Draw (Phase 2)
    'lucky-draw-reset-prize-daily-counters': {
        'task': 'apps.lucky_draw.tasks.reset_prize_daily_counters_task',
        'schedule': crontab(hour=0, minute=1),
    },
    'lucky-draw-expiry-reminders': {
        'task': 'apps.lucky_draw.tasks.send_expiry_reminders_task',
        'schedule': crontab(minute=0),  # hourly
    },
    'lucky-draw-expire-entries': {
        'task': 'apps.lucky_draw.tasks.expire_entries_task',
        'schedule': crontab(hour=0, minute=15),
    },
    # Content Studio (Phase 5) — daily safety net for any output still pointing
    # at a provider temp URL (should be none once download-and-store is in place).
    'content-studio-cleanup-expired-urls': {
        'task': 'apps.content_studio.tasks.cleanup_expired_provider_urls_task',
        'schedule': crontab(hour=3, minute=30),
    },
    # Billing (Phase 6)
    'billing-reset-monthly-credits': {
        'task': 'apps.billing.tasks.reset_monthly_credits_task',
        'schedule': crontab(hour=0, minute=5, day_of_month=1),  # 1st of month 00:05 UTC
    },
    'billing-generate-monthly-summary': {
        'task': 'apps.billing.tasks.generate_monthly_summary_task',
        'schedule': crontab(hour=1, minute=0, day_of_month=2),  # 2nd of month
    },
    'billing-check-cap-alerts': {
        'task': 'apps.billing.tasks.check_cap_alerts_task',
        'schedule': crontab(minute=0, hour='*/6'),  # every 6h
    },
    'billing-reconcile-stale-reservations': {
        'task': 'apps.billing.tasks.reconcile_stale_reservations_task',
        'schedule': crontab(minute='*/15'),  # every 15 min
    },
}

# ──────────────────────────────────────────────────────────────────────
# CRM Lite (Phase 1) settings
# ──────────────────────────────────────────────────────────────────────
CRM_AUTO_SYNC_BOOKINGS = config('CRM_AUTO_SYNC_BOOKINGS', default=True, cast=bool)
CRM_AUTO_SYNC_CONVERSATIONS = config('CRM_AUTO_SYNC_CONVERSATIONS', default=True, cast=bool)
CRM_FREQUENT_THRESHOLD = config('CRM_FREQUENT_THRESHOLD', default=5, cast=int)
CRM_INACTIVE_DAYS = config('CRM_INACTIVE_DAYS', default=90, cast=int)

# ──────────────────────────────────────────────────────────────────────
# Lucky Draw (Phase 2) settings
# ──────────────────────────────────────────────────────────────────────
# Public origin that QR codes / referral links resolve against. Non-secret →
# belongs in k8s/configmap.yaml (chatplatform-config) in production.
PUBLIC_BASE_URL = config('PUBLIC_BASE_URL', default='https://kribaat.com')

# ──────────────────────────────────────────────────────────────────────
# AI Credit & Usage Billing (Phase 6) settings
# ──────────────────────────────────────────────────────────────────────
BILLING_SETTINGS = {
    # A `reserved` UsageEvent older than this (minutes) is presumed orphaned
    # (crash between provider-success and confirm) and refunded by the sweeper.
    'RESERVATION_TTL_MINUTES': config('BILLING_RESERVATION_TTL_MINUTES', default=15, cast=int),
    # USD→HKD conversion used to price provider cost in the org's billing currency.
    'USD_TO_HKD': config('BILLING_USD_TO_HKD', default=7.8, cast=float),
    # Notify the org owner (WhatsApp) when the spend cap crosses a threshold.
    'NOTIFY_OWNER_ON_CAP': config('BILLING_NOTIFY_OWNER_ON_CAP', default=True, cast=bool),
}

# ──────────────────────────────────────────────────────────────────────
# Payments (Stripe) settings
# ──────────────────────────────────────────────────────────────────────
# SECRET keys → GitHub Secrets → chatplatform-secrets (deploy-secrets job).
# PUBLISHABLE key is non-secret → k8s/configmap.yaml. Empty defaults keep the
# checkout endpoint returning 503 (not 500) until configured.
STRIPE_SECRET_KEY = config('STRIPE_SECRET_KEY', default='')
STRIPE_PUBLISHABLE_KEY = config('STRIPE_PUBLISHABLE_KEY', default='')
STRIPE_WEBHOOK_SECRET = config('STRIPE_WEBHOOK_SECRET', default='')

# Optional dedicated webhook secret for the Coffee Pass endpoint. When blank the
# shared STRIPE_WEBHOOK_SECRET is used — that is the normal single-endpoint setup.
COFFEE_PASS_WEBHOOK_SECRET = config('COFFEE_PASS_WEBHOOK_SECRET', default='')

# ──────────────────────────────────────────────────────────────────────
# Coffee Pass — paid 30-day repeat-visit membership
# ──────────────────────────────────────────────────────────────────────
# Every safety constant is configurable, but the OFFER GATES (quality, consent,
# tenancy) are code, not config — an owner can tune economics, never safety.
COFFEE_PASS_SETTINGS = {
    # Master feature flag. Off by default until a cafe is piloted.
    'ENABLED': config('COFFEE_PASS_ENABLED', default=False, cast=bool),

    # Which MenuItem.item_type values a Coffee Pass may discount.
    #
    # `coffee` is the intended type; `drink` is tolerated for menus built before
    # the coffee type existed. FOOD IS DELIBERATELY ABSENT — a pass that
    # discounts a rice platter is not the product.
    #
    # Widening this is a configmap edit, not a redeploy: set
    # COFFEE_PASS_ELIGIBLE_ITEM_TYPES=coffee,drink,addon in k8s/configmap.yaml
    # to let a future "pass covers a pastry too" promo work with no code change.
    'ELIGIBLE_ITEM_TYPES': tuple(
        t.strip() for t in config(
            'COFFEE_PASS_ELIGIBLE_ITEM_TYPES', default='coffee,drink',
        ).split(',') if t.strip()
    ),

    # Verification (the rotating QR shown in the customer wallet).
    'VERIFICATION_TOKEN_TTL_SECONDS': config(
        'COFFEE_PASS_TOKEN_TTL', default=90, cast=int),

    # OTP (public customer login).
    #
    # DELIVERY MODE — the single most important setting in this block.
    #
    # A free-form WhatsApp text only reaches a number that messaged the business
    # within the last 24 hours. Meta ACCEPTS a text to any other number (HTTP 200
    # + a wamid) and then drops it, so the send looks successful while no code
    # ever arrives. A brand-new customer is BY DEFINITION outside that window,
    # which makes text delivery useless for OTP.
    #
    # A pre-approved Authentication template is the only thing Meta delivers to a
    # cold number. Create one in Meta Business Manager -> WhatsApp Manager ->
    # Message templates (category: Authentication, with the copy-code button),
    # then set COFFEE_PASS_OTP_TEMPLATE to its name.
    #
    # Leave the template name empty ONLY for local dev against a phone whose 24h
    # window you have opened by hand.
    'OTP_TEMPLATE_NAME': config('COFFEE_PASS_OTP_TEMPLATE', default=''),
    'OTP_TEMPLATE_LANGUAGE': config('COFFEE_PASS_OTP_TEMPLATE_LANG', default='en'),

    # Whether the approved template carries the one-tap copy-code button. Set
    # false if the template was built with the body variable only — Meta rejects
    # a message carrying a component the template does not declare.
    'OTP_TEMPLATE_HAS_BUTTON': config(
        'COFFEE_PASS_OTP_TEMPLATE_HAS_BUTTON', default=True, cast=bool),

    'OTP_TTL_SECONDS': config('COFFEE_PASS_OTP_TTL', default=300, cast=int),
    'OTP_MAX_ATTEMPTS': config('COFFEE_PASS_OTP_MAX_ATTEMPTS', default=5, cast=int),
    'OTP_MAX_SENDS_PER_PHONE': config(
        'COFFEE_PASS_OTP_MAX_PER_PHONE', default=5, cast=int),
    'OTP_MAX_SENDS_PER_IP': config('COFFEE_PASS_OTP_MAX_PER_IP', default=20, cast=int),
    'OTP_RATE_WINDOW_SECONDS': 3600,

    # Public customer session lifetime.
    'SESSION_TTL_SECONDS': config('COFFEE_PASS_SESSION_TTL', default=3600, cast=int),

    # Redemption safety: caps a mistyped subtotal from poisoning every metric.
    'MAX_ELIGIBLE_SUBTOTAL_HKD': config(
        'COFFEE_PASS_MAX_SUBTOTAL', default=2000, cast=int),

    # A pending checkout blocks a new offer; release abandoned ones after this.
    'PENDING_CHECKOUT_TTL_MINUTES': config(
        'COFFEE_PASS_PENDING_TTL_MINUTES', default=60, cast=int),

    # Notifications.
    'REMINDER_MIN_INTERVAL_DAYS': config(
        'COFFEE_PASS_REMINDER_INTERVAL_DAYS', default=7, cast=int),
    'EXPIRY_REMINDER_DAYS': config('COFFEE_PASS_EXPIRY_REMINDER_DAYS', default=3, cast=int),
    'OUTBOX_MAX_ATTEMPTS': config('COFFEE_PASS_OUTBOX_MAX_ATTEMPTS', default=5, cast=int),

    # Owner anomaly thresholds (explainable alerts, never opaque scoring).
    'ALERT_MAX_REDEMPTIONS_PER_CUSTOMER_PER_DAY': 5,
    'ALERT_MAX_VOIDS_PER_STAFF_PER_WEEK': 20,
    'ALERT_NEGATIVE_FEEDBACK_PER_WEEK': 3,

    # Offer decision engine. Tunable economics; the hard gates are in code.
    'SCORING': {
        'ROUTINE_NEARBY': 60,
        'ROUTINE_OCCASIONAL': 20,
        'PRIOR_PASS_REDEEMED': 15,
        'PRIOR_POSITIVE_EXPERIENCE': 10,
        'PRIOR_PASS_UNUSED': -25,
        'NEGATIVE_EXPERIENCE': -40,
        'THRESHOLD_OFFER': 40,
        'THRESHOLD_SOFT': 20,
        'MAX_BREAK_EVEN_VISITS': config(
            'COFFEE_PASS_MAX_BREAK_EVEN_VISITS', default=20, cast=int),
    },
}

# Redis Cache
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': config('REDIS_URL', default='redis://localhost:6379/0'),
    }
}

# ──────────────────────────────────────────────────────────────────────
# Email (SMTP) — used by inventory PO send + future transactional mail.
#
# Defaults are dev-friendly: with no env vars set we use the console
# backend so emails just print to the container log. In production the
# CI pipeline injects EMAIL_HOST_USER + EMAIL_HOST_PASSWORD and we flip
# to the real SMTP backend automatically.
#
# Gmail SMTP is the easiest provider:
#   EMAIL_HOST = smtp.gmail.com
#   EMAIL_PORT = 587
#   EMAIL_USE_TLS = true
#   EMAIL_HOST_USER = your-gmail-address@gmail.com
#   EMAIL_HOST_PASSWORD = <16-char Gmail App Password>
# ──────────────────────────────────────────────────────────────────────
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=False, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_TIMEOUT = config('EMAIL_TIMEOUT', default=15, cast=int)
DEFAULT_FROM_EMAIL = config(
    'DEFAULT_FROM_EMAIL',
    default=EMAIL_HOST_USER or 'noreply@kribaat.com',
)
SERVER_EMAIL = DEFAULT_FROM_EMAIL
# Auto-pick the backend: real SMTP only if creds are present, else console.
EMAIL_BACKEND = config(
    'EMAIL_BACKEND',
    default=(
        'django.core.mail.backends.smtp.EmailBackend'
        if EMAIL_HOST_USER and EMAIL_HOST_PASSWORD
        else 'django.core.mail.backends.console.EmailBackend'
    ),
)

# OpenAI Configuration
OPENAI_API_KEY = config('OPENAI_API_KEY', default='')
OPENAI_MODEL = config('OPENAI_MODEL', default='gpt-4o-mini')
OPENAI_MAX_TOKENS = config('OPENAI_MAX_TOKENS', default=500, cast=int)
OPENAI_TEMPERATURE = config('OPENAI_TEMPERATURE', default=0.7, cast=float)

# Meta (WhatsApp & Instagram) Configuration
META_APP_SECRET = config('META_APP_SECRET', default='')
META_GRAPH_API_VERSION = config('META_GRAPH_API_VERSION', default='v18.0')
# Default verify tokens for webhook verification (override per organization in channel config)
WHATSAPP_DEFAULT_VERIFY_TOKEN = config('WHATSAPP_DEFAULT_VERIFY_TOKEN', default='whatsapp_verify_token_change_me')
INSTAGRAM_DEFAULT_VERIFY_TOKEN = config('INSTAGRAM_DEFAULT_VERIFY_TOKEN', default='instagram_verify_token_change_me')

# AI Engine Settings
AI_CONFIDENCE_THRESHOLD = 0.7  # Below this, escalate to human
AI_MAX_CONTEXT_MESSAGES = 10  # Max messages to include in context

# Inventory (Plane B) Settings
from decimal import Decimal as _Decimal  # noqa: E402

INVENTORY_SETTINGS = {
    'DEFAULT_TOLERANCE_PERCENT': _Decimal('0.5'),
    'MAX_TOLERANCE_PERCENT': _Decimal('5.0'),
    'EXCEL_MAX_FILE_SIZE_MB': 10,
    'EXCEL_PREVIEW_ROWS': 10,
    'IMPORT_ERROR_THRESHOLD_PERCENT': 30,
    'LOW_STOCK_ALERT_COOLDOWN_HOURS': 24,
    'AI_INVENTORY_ENABLED': True,
    'AI_INVENTORY_MODEL': config('INVENTORY_AI_MODEL', default='gpt-4o-mini'),
    'STOCK_ALERT_CHANNELS': ['whatsapp'],
    # Phase 6 — Plane A integration. When True, completing a Booking that
    # has RecipeBookingLink rows auto-consumes those recipes via StockEngine.
    # Default False so production is unchanged until explicitly enabled.
    'AUTO_CONSUME_ON_BOOKING_COMPLETE': config(
        'INVENTORY_AUTO_CONSUME_ON_BOOKING', default=False, cast=bool,
    ),
    # Phase 6 — per-org AI profile freshness. Profiles older than this are
    # regenerated on next AI query; a daily Celery task also refreshes.
    'AI_PROFILE_TTL_HOURS': 36,
    # Phase 4 — drink/cocktail formula pour variance (default tolerance for
    # drink_formula / cocktail_formula recipes when the recipe doesn't override).
    'DEFAULT_POUR_VARIANCE_PERCENT': _Decimal(
        config('INVENTORY_POUR_VARIANCE', default='5.0')
    ),
    'COCKTAIL_FORMULA_ENABLED': config(
        'INVENTORY_COCKTAIL_FORMULA', default=True, cast=bool,
    ),
}

# ──────────────────────────────────────────────────────────────────────
# AI Content Studio (Phase 5) settings
# ──────────────────────────────────────────────────────────────────────
# Model IDs are CONFIG-DRIVEN — never hardcode them in code or bump via redeploy.
# Bumping to a future model = change an env var (configmap) or a template DB row.
# Defaults reflect May 2026 (DALL·E removed from the API 2026-05-12 — not used).
CONTENT_STUDIO = {
    'IMAGE_MODEL_QUALITY': config('CONTENT_STUDIO_IMAGE_MODEL', default='gpt-image-2'),
    'IMAGE_MODEL_CHEAP': config('CONTENT_STUDIO_IMAGE_MODEL_CHEAP', default='gpt-image-1-mini'),
    'TEXT_ASSIST_MODEL': config('CONTENT_STUDIO_TEXT_MODEL', default='gpt-5.5'),
    'DEFAULT_PROVIDER': config('CONTENT_STUDIO_PROVIDER', default='openai_gpt_image'),
    'DEFAULT_RESOLUTION': config('CONTENT_STUDIO_DEFAULT_RESOLUTION', default='1024x1024'),
    'MAX_RETRIES': 3,
    'PROVIDER_URL_EXPIRY_MINUTES': 60,
    # Estimated USD per image by resolution tier — pre-flight credit estimate only;
    # actual cost is read from the provider usage object post-generation.
    'COST_ESTIMATE_USD': {'1k': _Decimal('0.05'), '2k': _Decimal('0.20'), '4k': _Decimal('0.80')},
    'USD_TO_HKD': _Decimal(config('USD_TO_HKD', default='7.8')),
}

# API Documentation
SPECTACULAR_SETTINGS = {
    'TITLE': 'AI Business Chat Platform API',
    'DESCRIPTION': 'Multi-tenant AI business chatbot platform API',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': config('DJANGO_LOG_LEVEL', default='INFO'),
            'propagate': False,
        },
        'apps': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}
