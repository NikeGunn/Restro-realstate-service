"""
Referral service (Phase 2) — 🇭🇰 loop 2: share-for-bonus.

apply_referral links a NEW entry to the referrer's entry (by referral_token),
increments the referrer's referral_count, and grants the campaign's configured
bonus. Self-referral and same-phone referral are rejected. Idempotent per
(referrer, referee phone): a phone can only ever count once toward a referrer.

Bonus semantics:
- extra_entry: the referrer earns one extra entry allowance for today (recorded
  as referral_count; the eligibility check grants +1 daily slot per referral so
  the public flow stays simple and the counter is the single source of truth).
- better_odds: same counter; the frontend/UX surfaces it as "better odds", and
  the value is available to future draw weighting. We record it identically so
  the data model is uniform; the difference is purely how it's presented/redeemed.
"""
import logging

from django.db import transaction
from django.db.models import F

from ..models import LuckyDrawEntry

logger = logging.getLogger(__name__)


@transaction.atomic
def apply_referral(new_entry, referral_token):
    """
    Attribute `new_entry` to the referrer identified by `referral_token`.

    Returns the referrer entry on success, or None if the referral is invalid
    (unknown token, self-referral, same phone, or already attributed). Never
    raises — a bad referral must not break the entry pipeline.
    """
    if not referral_token:
        return None
    try:
        referrer = (
            LuckyDrawEntry.objects.select_for_update()
            .filter(
                referral_token=referral_token,
                campaign=new_entry.campaign,
            )
            .first()
        )
        if referrer is None:
            return None

        # Reject self-referral and same-phone referral (anti-abuse).
        if referrer.pk == new_entry.pk:
            return None
        if new_entry.phone and referrer.phone and new_entry.phone == referrer.phone:
            return None

        # Idempotent per (referrer, referee phone): this phone may only count once.
        if new_entry.phone:
            already = LuckyDrawEntry.objects.filter(
                referred_by_entry=referrer, phone=new_entry.phone,
            ).exclude(pk=new_entry.pk).exists()
            if already:
                return None

        # Link the new entry to its referrer (allowed mutable field).
        new_entry.referred_by_entry = referrer
        new_entry.save(update_fields=['referred_by_entry'])

        # Grant the referrer their bonus by bumping the counter atomically.
        LuckyDrawEntry.objects.filter(pk=referrer.pk).update(
            referral_count=F('referral_count') + 1
        )
        referrer.refresh_from_db(fields=['referral_count'])
        return referrer
    except Exception:
        logger.exception("apply_referral failed for token=%s", referral_token)
        return None


def bonus_daily_allowance(campaign, phone):
    """
    Extra daily entry slots this phone has earned via referrals on this campaign
    (only meaningful when referral_bonus_type == extra_entry). Equals the sum of
    referral_count over the phone's entries in this campaign.
    """
    from django.db.models import Sum
    if not phone:
        return 0
    agg = LuckyDrawEntry.objects.filter(
        campaign=campaign, phone=phone,
    ).aggregate(total=Sum('referral_count'))
    return int(agg['total'] or 0)
