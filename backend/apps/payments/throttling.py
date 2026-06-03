"""Payments throttles."""
from rest_framework.throttling import UserRateThrottle


class CheckoutThrottle(UserRateThrottle):
    """Rate-limit authenticated checkout-session creation per user (anti-abuse).

    Rate is `payments_checkout` in settings.DEFAULT_THROTTLE_RATES.
    """
    scope = 'payments_checkout'
