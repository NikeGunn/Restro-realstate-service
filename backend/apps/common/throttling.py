"""
Throttle classes for unauthenticated public endpoints (Phase 0).

Rates are configured in settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'].
These are AnonRateThrottle subclasses (keyed by client IP) for the public
lucky-draw flows (Phase 2) and any future public surface.

There was NO throttle config before Phase 0 — this is net-new and required
before any public endpoint ships.
"""
from rest_framework.throttling import AnonRateThrottle


class PublicBurstThrottle(AnonRateThrottle):
    """GET-side burst protection for public config endpoints (e.g. campaign config)."""
    scope = 'public_burst'


class PublicSustainedThrottle(AnonRateThrottle):
    """Sustained-rate ceiling for public reads over a longer window."""
    scope = 'public_sustained'


class PublicFormThrottle(AnonRateThrottle):
    """Stricter limit for public POST submissions (e.g. lucky-draw entry)."""
    scope = 'public_form'
