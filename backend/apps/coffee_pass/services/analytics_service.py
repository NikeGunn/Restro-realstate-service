"""
Owner analytics — computed from PERSISTED records, never from event streams.

Design choice (PRD §12): every number reconciles to a row an owner could count
by hand. Analytics events are for funnel debugging; the dashboard reads the
ledger. That is why the tests can assert exact values against fixtures.

All queries are date-bounded SQL aggregates against the indexes declared on the
models. No daily rollup tables until real p95 data proves the budget is missed —
premature aggregation would be a second source of truth to keep in sync.
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from ..models import (
    CoffeeExperience, CoffeePass, CoffeePassPurchase, CoffeePassRedemption,
    PassStatus, PurchaseStatus, RedemptionStatus, Sentiment,
)

ZERO = Decimal('0.00')


def _window(date_from=None, date_to=None):
    """Default to the trailing 30 days when the caller gives no range."""
    now = timezone.now()
    start = date_from or (now - timezone.timedelta(days=30))
    end = date_to or now
    return start, end


def _scoped(qs, organization, location=None):
    qs = qs.filter(organization=organization)
    return qs.filter(location=location) if location is not None else qs


def summary(*, organization, location=None, date_from=None, date_to=None) -> dict:
    """
    The owner dashboard payload: sales, passes, redemptions, retention, feedback.

    Retention is the number the whole product exists to move, so it is measured
    two independent ways — first-week activation and repeat usage — rather than a
    single flattering metric.
    """
    start, end = _window(date_from, date_to)

    purchases = _scoped(
        CoffeePassPurchase.objects.filter(created_at__gte=start, created_at__lte=end),
        organization, location,
    )
    paid = purchases.filter(status__in=[PurchaseStatus.PAID, PurchaseStatus.REFUNDED])

    revenue = paid.aggregate(
        gross=Sum('amount_hkd'), refunded=Sum('refunded_amount_hkd'),
    )
    gross = revenue['gross'] or ZERO
    refunded = revenue['refunded'] or ZERO

    # Pass counts are CURRENT state, not window-bounded: "how many active passes
    # do I have right now" is the question owners actually ask.
    passes = _scoped(CoffeePass.objects.all(), organization, location)
    pass_counts = passes.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(status=PassStatus.ACTIVE)),
        expired=Count('id', filter=Q(status=PassStatus.EXPIRED)),
        cancelled=Count('id', filter=Q(status=PassStatus.CANCELLED)),
        suspended=Count('id', filter=Q(status=PassStatus.SUSPENDED)),
    )

    redemptions = _scoped(
        CoffeePassRedemption.objects.filter(redeemed_at__gte=start, redeemed_at__lte=end),
        organization, location,
    )
    live = redemptions.filter(status=RedemptionStatus.REDEEMED)
    redemption_stats = live.aggregate(
        count=Count('id'),
        eligible_total=Sum('eligible_subtotal_hkd'),
        discount_total=Sum('discount_amount_hkd'),
        average_saving=Avg('discount_amount_hkd'),
    )
    missing_receipt = live.filter(pos_receipt_reference='').count()

    experiences = _scoped(
        CoffeeExperience.objects.filter(created_at__gte=start, created_at__lte=end),
        organization, location,
    )
    feedback = experiences.aggregate(
        good=Count('id', filter=Q(sentiment=Sentiment.GOOD)),
        okay=Count('id', filter=Q(sentiment=Sentiment.OKAY)),
        not_good=Count('id', filter=Q(sentiment=Sentiment.NOT_GOOD)),
        offers_shown=Count('id', filter=Q(offer_shown_at__isnull=False)),
    )

    return {
        'window': {'from': start.isoformat(), 'to': end.isoformat()},
        'sales': {
            'checkout_started': purchases.count(),
            'purchases_paid': paid.count(),
            'conversion_rate': _rate(paid.count(), purchases.count()),
            'gross_revenue_hkd': str(gross),
            'refunded_hkd': str(refunded),
            'net_revenue_hkd': str(gross - refunded),
        },
        'passes': pass_counts,
        'redemptions': {
            'count': redemption_stats['count'] or 0,
            'voided_count': redemptions.filter(status=RedemptionStatus.VOIDED).count(),
            'eligible_subtotal_hkd': str(redemption_stats['eligible_total'] or ZERO),
            'total_discount_hkd': str(redemption_stats['discount_total'] or ZERO),
            'average_saving_hkd': str(
                (redemption_stats['average_saving'] or ZERO).quantize(Decimal('0.01'))
            ),
            'missing_receipt_reference': missing_receipt,
        },
        'retention': retention(organization=organization, location=location,
                               date_from=start, date_to=end),
        'feedback': feedback,
    }


def retention(*, organization, location=None, date_from=None, date_to=None) -> dict:
    """
    Does membership actually bring people back?

    - first_redemption_within_7_days: did the pass get used at all, quickly?
    - repeat_rate: share of members with 2+ redemptions (the real repeat signal)
    - never_redeemed: passes sold that produced nothing — the margin leak, and a
      retention opportunity, NOT a fraud signal.
    """
    start, end = _window(date_from, date_to)
    passes = _scoped(
        CoffeePass.objects.filter(starts_at__gte=start, starts_at__lte=end)
        .exclude(status=PassStatus.PENDING_PAYMENT),
        organization, location,
    )
    total = passes.count()
    if not total:
        return {
            'passes_measured': 0, 'first_redemption_within_7_days': 0,
            'first_redemption_rate': 0.0, 'repeat_customers': 0,
            'repeat_rate': 0.0, 'never_redeemed': 0,
        }

    annotated = passes.annotate(
        live_redemptions=Count(
            'redemptions', filter=Q(redemptions__status=RedemptionStatus.REDEEMED),
        ),
    )
    never = sum(1 for p in annotated if p.live_redemptions == 0)
    repeat = sum(1 for p in annotated if p.live_redemptions >= 2)

    quick = 0
    for coffee_pass in passes.only('id', 'starts_at'):
        cutoff = coffee_pass.starts_at + timezone.timedelta(days=7)
        if CoffeePassRedemption.objects.filter(
            coffee_pass=coffee_pass, status=RedemptionStatus.REDEEMED,
            redeemed_at__lte=cutoff,
        ).exists():
            quick += 1

    return {
        'passes_measured': total,
        'first_redemption_within_7_days': quick,
        'first_redemption_rate': _rate(quick, total),
        'repeat_customers': repeat,
        'repeat_rate': _rate(repeat, total),
        'never_redeemed': never,
    }


def anomalies(*, organization, location=None) -> list:
    """
    Explainable alerts, not opaque fraud scoring (A.6).

    Each entry carries a `code`, a human `detail`, and the offending count, so an
    owner can act on it. Nothing here accuses anyone — 'pass unused' is a
    retention prompt, and 'many voids' is a question, not a verdict.
    """
    from django.conf import settings

    cfg = getattr(settings, 'COFFEE_PASS_SETTINGS', {})
    now = timezone.now()
    day_ago = now - timezone.timedelta(days=1)
    week_ago = now - timezone.timedelta(days=7)
    found = []

    live = _scoped(
        CoffeePassRedemption.objects.filter(status=RedemptionStatus.REDEEMED),
        organization, location,
    )

    # >N redemptions by one customer in a day.
    heavy = (
        live.filter(redeemed_at__gte=day_ago)
        .values('customer_id')
        .annotate(n=Count('id'))
        .filter(n__gt=cfg.get('ALERT_MAX_REDEMPTIONS_PER_CUSTOMER_PER_DAY', 5))
    )
    for row in heavy:
        found.append({
            'code': 'high_redemption_count',
            'detail': 'One customer redeemed unusually often today.',
            'customer_id': str(row['customer_id']), 'count': row['n'],
        })

    # Same POS receipt reference reused at a location.
    dupes = (
        live.filter(redeemed_at__gte=week_ago).exclude(pos_receipt_reference='')
        .values('location_id', 'pos_receipt_reference')
        .annotate(n=Count('id')).filter(n__gt=1)
    )
    for row in dupes:
        found.append({
            'code': 'duplicate_receipt_reference',
            'detail': 'The same POS receipt reference was recorded more than once.',
            'reference': row['pos_receipt_reference'], 'count': row['n'],
        })

    # >N voids by one staff member in 7 days.
    voids = (
        _scoped(
            CoffeePassRedemption.objects.filter(
                status=RedemptionStatus.VOIDED, voided_at__gte=week_ago,
            ), organization, location,
        )
        .values('voided_by_id').annotate(n=Count('id'))
        .filter(n__gt=cfg.get('ALERT_MAX_VOIDS_PER_STAFF_PER_WEEK', 20))
    )
    for row in voids:
        found.append({
            'code': 'high_void_count',
            'detail': 'One staff member voided an unusual number of redemptions.',
            'user_id': str(row['voided_by_id']) if row['voided_by_id'] else None,
            'count': row['n'],
        })

    # Paid but never used after 21 days — retention opportunity.
    stale_cutoff = now - timezone.timedelta(days=21)
    unused = _scoped(
        CoffeePass.objects.filter(status=PassStatus.ACTIVE, starts_at__lt=stale_cutoff),
        organization, location,
    ).annotate(
        live_redemptions=Count(
            'redemptions', filter=Q(redemptions__status=RedemptionStatus.REDEEMED),
        ),
    ).filter(live_redemptions=0).count()
    if unused:
        found.append({
            'code': 'passes_unused',
            'detail': 'Active passes with no redemption after 21 days.',
            'count': unused,
        })

    # Quality alert: repeated negative feedback at one location.
    negatives = _scoped(
        CoffeeExperience.objects.filter(
            sentiment=Sentiment.NOT_GOOD, created_at__gte=week_ago,
        ), organization, location,
    ).count()
    if negatives >= cfg.get('ALERT_NEGATIVE_FEEDBACK_PER_WEEK', 3):
        found.append({
            'code': 'negative_feedback_cluster',
            'detail': 'Several customers reported a poor coffee experience this week.',
            'count': negatives,
        })

    return found


def _rate(part, whole) -> float:
    return round((part / whole) * 100, 2) if whole else 0.0
