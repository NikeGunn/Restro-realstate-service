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
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

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
