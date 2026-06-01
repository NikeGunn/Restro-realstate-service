"""
Draw engine (Phase 2) — pure selection + token generation + eligibility.

These are deliberately small, side-effect-light functions so they can be unit
tested in isolation. The CALLER (the public-entry view) owns the transaction:
it writes the Entry row and increments the prize counters under select_for_update
in a single atomic block. draw_prize() only PICKS.
"""
import random
import secrets

from django.utils import timezone

from ..models import CampaignStatus

# Coupon alphabet EXCLUDES ambiguous characters (0/O, 1/I/L) so codes are easy
# to read aloud and key in at a busy HK restaurant counter.
COUPON_ALPHABET = '23456789ABCDEFGHJKMNPQRSTUVWXYZ'
REFERRAL_ALPHABET = '23456789abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ'


def eligible_prizes(campaign):
    """
    Active prizes that still have daily AND total headroom (checked against the
    denormalized counters). Returns a list (may be empty for a degenerate config).
    """
    return [
        p for p in campaign.prizes.filter(active=True)
        if p.weight > 0 and p.has_daily_headroom() and p.has_total_headroom()
    ]


def draw_prize(campaign, _rng=None):
    """
    Weighted random over ACTIVE prizes that still have headroom.

    Pure selection — the caller writes the Entry and increments counters in one
    txn. Returns None only if every prize is exhausted (degenerate config).

    `_rng` is an injection point so tests can pass a seeded random.Random for
    deterministic distribution assertions.
    """
    prizes = eligible_prizes(campaign)
    if not prizes:
        return None
    rng = _rng or random
    weights = [p.weight for p in prizes]
    return rng.choices(prizes, weights=weights, k=1)[0]


def generate_coupon_code(length=8):
    """URL-safe UPPERCASE alphanumeric, excluding ambiguous chars. Uniqueness is
    the caller's responsibility (retry on clash)."""
    return ''.join(secrets.choice(COUPON_ALPHABET) for _ in range(length))


def generate_referral_token(length=12):
    """A hard-to-guess referral token. Uniqueness is the caller's responsibility."""
    return ''.join(secrets.choice(REFERRAL_ALPHABET) for _ in range(length))


def validate_entry_eligibility(campaign, phone, ip_hash):
    """
    (eligible, reason). Evaluated at draw time inside the entry-creation txn.

    - status must be active
    - today within [start_date, end_date]
    - daily_entry_limit per phone (HARD)
    - total_entry_limit per phone (HARD)
    - per-IP daily is SOFT: logged but allowed, because HK restaurants share NAT
      IPs (many real customers behind one address). It only blocks if the phone
      limit is also hit, which the phone check already covers.
    """
    from ..models import LuckyDrawEntry  # local import keeps this module import-light

    if campaign.status != CampaignStatus.ACTIVE:
        return False, 'campaign_not_active'

    today = timezone.localdate()
    if campaign.start_date and today < campaign.start_date:
        return False, 'campaign_not_started'
    if campaign.end_date and today > campaign.end_date:
        return False, 'campaign_ended'

    if phone:
        # HARD daily limit per phone.
        if campaign.daily_entry_limit_per_customer:
            today_count = LuckyDrawEntry.objects.filter(
                campaign=campaign, phone=phone, entered_at__date=today,
            ).count()
            if today_count >= campaign.daily_entry_limit_per_customer:
                return False, 'daily_limit_reached'

        # HARD total limit per phone.
        if campaign.total_entry_limit_per_customer is not None:
            total_count = LuckyDrawEntry.objects.filter(
                campaign=campaign, phone=phone,
            ).count()
            if total_count >= campaign.total_entry_limit_per_customer:
                return False, 'total_limit_reached'

    return True, 'ok'
