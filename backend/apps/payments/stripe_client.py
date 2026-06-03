"""
Stripe client singleton.

Import the configured `stripe` module from here so the secret key is always set
before any API call, and so network retries / API version are consistent.
"""
import stripe
from django.conf import settings


def get_stripe():
    """Return the stripe module with the secret key + safe defaults configured."""
    stripe.api_key = settings.STRIPE_SECRET_KEY
    # Idempotent retries on transient network errors (Stripe-side dedup by
    # request; safe for our create calls which also pass idempotency keys).
    stripe.max_network_retries = 2
    return stripe
