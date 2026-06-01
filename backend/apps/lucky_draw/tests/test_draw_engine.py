"""Draw engine tests (Phase 2) — pure selection + token generation + eligibility."""
import random

import pytest

from apps.lucky_draw.services import draw_engine, entry_service

pytestmark = pytest.mark.django_db


def test_coupon_alphabet_excludes_ambiguous_chars():
    code = draw_engine.generate_coupon_code(40)
    for ch in '01OIL':
        assert ch not in code
    # All chars come from the declared alphabet.
    assert set(code) <= set(draw_engine.COUPON_ALPHABET)


def test_coupon_code_length():
    assert len(draw_engine.generate_coupon_code(8)) == 8
    assert len(draw_engine.generate_coupon_code(12)) == 12


def test_referral_token_unique_enough():
    tokens = {draw_engine.generate_referral_token() for _ in range(500)}
    assert len(tokens) == 500  # no collisions in practice


def test_weighted_distribution_within_tolerance(campaign):
    """Over 1000 seeded draws the dominant bucket (1%, weight 60) lands within
    ±5 percentage points of its 60% theoretical share."""
    rng = random.Random(42)
    counts = {}
    for _ in range(1000):
        prize = draw_engine.draw_prize(campaign, _rng=rng)
        counts[prize.discount_percent] = counts.get(prize.discount_percent, 0) + 1
    one_pct_share = counts.get(1, 0) / 1000
    assert 0.55 <= one_pct_share <= 0.65  # 60% ± 5pp


def test_draw_respects_max_wins_per_day(campaign):
    """A prize at its daily cap is excluded from eligibility."""
    # Make ONLY the 50% prize eligible, capped at its already-reached daily max.
    campaign.prizes.exclude(discount_percent=50).update(active=False)
    fifty = campaign.prizes.get(discount_percent=50)
    fifty.max_wins_per_day = 1
    fifty.wins_today_count = 1  # cap reached
    fifty.save()
    # No eligible prize -> draw returns None.
    assert draw_engine.draw_prize(campaign) is None


def test_draw_respects_max_total_wins(campaign):
    campaign.prizes.exclude(discount_percent=50).update(active=False)
    fifty = campaign.prizes.get(discount_percent=50)
    fifty.max_total_wins = 5
    fifty.wins_total_count = 5
    fifty.save()
    assert draw_engine.draw_prize(campaign) is None


def test_draw_none_when_no_active_prizes(campaign):
    campaign.prizes.update(active=False)
    assert draw_engine.draw_prize(campaign) is None


def test_unique_coupon_retry_on_clash(campaign, monkeypatch):
    """If the first generated code clashes, the helper retries to a fresh one."""
    # Pre-seed an entry holding a known code.
    entry = entry_service.create_entry(
        campaign, name='Seed', phone='+85291110000', consent_given=False,
    )
    taken = entry.coupon_code
    calls = {'n': 0}
    real = draw_engine.generate_coupon_code

    def fake(length=8):
        calls['n'] += 1
        # First call returns the taken code, then fall back to real generation.
        return taken if calls['n'] == 1 else real(length)

    monkeypatch.setattr(draw_engine, 'generate_coupon_code', fake)
    code = entry_service._unique_coupon_code()
    assert code != taken
