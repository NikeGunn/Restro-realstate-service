"""
Register / list / delete the Kribaat Stripe webhook endpoint.

    python manage.py setup_stripe_webhook            # create (uses PUBLIC_BASE_URL)
    python manage.py setup_stripe_webhook --list
    python manage.py setup_stripe_webhook --url https://kribaat.com/api/v1/payments/webhook/
    python manage.py setup_stripe_webhook --delete we_123

Prints the `whsec_...` signing secret on create — copy it into the
STRIPE_WEBHOOK_SECRET GitHub Secret + deploy.yml.
"""
from django.conf import settings
from django.core.management.base import BaseCommand

import stripe

WEBHOOK_PATH = '/api/v1/payments/webhook/'
ENABLED_EVENTS = [
    'checkout.session.completed',
    'checkout.session.expired',
    'charge.refunded',
    'payment_intent.payment_failed',
]


class Command(BaseCommand):
    help = 'Register the Stripe webhook endpoint and print the signing secret.'

    def add_arguments(self, parser):
        parser.add_argument('--url', type=str, default='')
        parser.add_argument('--list', action='store_true')
        parser.add_argument('--delete', type=str, default='')

    def handle(self, *args, **options):
        stripe.api_key = settings.STRIPE_SECRET_KEY
        if not stripe.api_key:
            self.stderr.write(self.style.ERROR('STRIPE_SECRET_KEY is not set.'))
            return

        try:
            account = stripe.Account.retrieve()
            self.stdout.write(self.style.SUCCESS(
                f'Stripe account verified: {account.get("id", "unknown")} '
                f'(livemode={account.get("charges_enabled")})'))
        except stripe.error.AuthenticationError:
            self.stderr.write(self.style.ERROR('Invalid STRIPE_SECRET_KEY.'))
            return

        if options['list']:
            for ep in stripe.WebhookEndpoint.list(limit=20).data:
                self.stdout.write(
                    f'  ID: {ep.id}\n  URL: {ep.url}\n  Status: {ep.status}\n'
                    f'  Events: {", ".join(ep.enabled_events)}\n  ---')
            return

        if options['delete']:
            stripe.WebhookEndpoint.delete(options['delete'])
            self.stdout.write(self.style.SUCCESS(f'Deleted {options["delete"]}'))
            return

        url = options['url'] or f'{settings.PUBLIC_BASE_URL.rstrip("/")}{WEBHOOK_PATH}'
        self.stdout.write(f'Creating webhook endpoint: {url}')
        endpoint = stripe.WebhookEndpoint.create(
            url=url, enabled_events=ENABLED_EVENTS,
            description='Kribaat credit-pack payments webhook',
        )
        self.stdout.write(self.style.SUCCESS(
            f'\nWebhook created!\n  ID: {endpoint.id}\n  URL: {endpoint.url}\n'
            f'  Secret: {endpoint.secret}\n\n'
            f'Add to GitHub Secrets + deploy.yml:\n'
            f'  STRIPE_WEBHOOK_SECRET={endpoint.secret}\n'))
