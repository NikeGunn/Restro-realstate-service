"""
Concurrency proof: two simultaneous reservations that together exceed the
balance — exactly one succeeds, the other is blocked. This validates the
`select_for_update` row lock in reserve_credits.

Uses transaction=True so each thread gets a real, committable connection.
"""
import threading
from decimal import Decimal
from datetime import date

import pytest

from apps.accounts.models import Organization
from apps.billing.models import UsageCreditBalance, UsageEvent
from apps.billing.services import credit_service as cs
from apps.billing.services.provisioning import ensure_billing_for_org
from .conftest import new_key


@pytest.mark.django_db(transaction=True)
def test_two_concurrent_reservations_exceeding_balance_one_wins(django_db_setup):
    from apps.billing.models import SubscriptionPlan
    SubscriptionPlan.objects.update_or_create(
        slug='power', defaults={'name': 'Growth', 'plan_code': 'power',
                                'price_hkd': Decimal('200'), 'monthly_image_credits': 0,
                                'enabled_modules': []})
    org = Organization.objects.create(
        name='Concurrency Org', business_type=Organization.BusinessType.RESTAURANT,
        plan=Organization.Plan.POWER,
    )
    ensure_billing_for_org(org)
    bal = UsageCreditBalance.objects.get(organization=org)
    bal.free_credits_remaining = 0
    bal.paid_credits_remaining = 10  # only enough for ONE of two 8-credit reserves
    bal.period_start = date.today().replace(day=1)
    bal.save()

    results = {}
    barrier = threading.Barrier(2)

    def attempt(name):
        from django.db import connection
        barrier.wait()
        try:
            cs.reserve_credits(
                org, 8, event_type='content_studio_image', provider='openai',
                model='m', cost_usd_estimate=Decimal('0.1'),
                reference_id=None, idempotency_key=new_key(),
            )
            results[name] = 'ok'
        except cs.InsufficientCreditsError:
            results[name] = 'blocked'
        except Exception as e:  # pragma: no cover
            results[name] = f'error:{e}'
        finally:
            connection.close()

    t1 = threading.Thread(target=attempt, args=('a',))
    t2 = threading.Thread(target=attempt, args=('b',))
    t1.start(); t2.start(); t1.join(); t2.join()

    outcomes = sorted(results.values())
    assert outcomes == ['blocked', 'ok'], f'expected exactly one winner, got {results}'

    bal.refresh_from_db()
    assert bal.reserved_credits == 8  # only the winner reserved
    assert UsageEvent.objects.filter(organization=org).count() == 1

    # cleanup (transaction=True doesn't auto-rollback)
    UsageEvent.objects.filter(organization=org).delete()
    UsageCreditBalance.objects.filter(organization=org).delete()
    org.delete()
