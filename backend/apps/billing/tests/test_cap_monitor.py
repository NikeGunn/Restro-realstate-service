"""Cap monitor: band transitions + owner notified on upward crossing."""
from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.billing.models import CapStatus
from apps.billing.services import cap_monitor

pytestmark = pytest.mark.django_db


def _set_spend(balance, hkd):
    balance.current_estimated_spend_hkd = Decimal(hkd)
    balance.save(update_fields=['current_estimated_spend_hkd'])


def test_band_active_below_50(org, balance, limit):
    _set_spend(balance, '40')  # 20% of 200
    assert cap_monitor.recompute_cap_status(balance) == CapStatus.ACTIVE


def test_band_warning_50(org, balance, limit):
    _set_spend(balance, '120')  # 60%
    assert cap_monitor.recompute_cap_status(balance) == CapStatus.WARNING_50


def test_band_warning_80(org, balance, limit):
    _set_spend(balance, '180')  # 90%
    assert cap_monitor.recompute_cap_status(balance) == CapStatus.WARNING_80


def test_band_blocked_at_100(org, balance, limit):
    _set_spend(balance, '200')  # 100%
    assert cap_monitor.recompute_cap_status(balance) == CapStatus.BLOCKED


def test_owner_notified_on_upward_crossing(org, balance, limit):
    _set_spend(balance, '180')  # crosses into warning_80
    with patch.object(cap_monitor, '_notify_owner') as notify:
        cap_monitor.recompute_cap_status(balance, persist=True)
        assert notify.called


def test_no_notify_when_band_unchanged(org, balance, limit):
    _set_spend(balance, '180')
    cap_monitor.recompute_cap_status(balance, persist=True)  # now warning_80
    with patch.object(cap_monitor, '_notify_owner') as notify:
        cap_monitor.recompute_cap_status(balance, persist=True)  # still warning_80
        assert not notify.called


def test_no_notify_on_downward_crossing(org, balance, limit):
    _set_spend(balance, '200')
    cap_monitor.recompute_cap_status(balance, persist=True)  # blocked
    _set_spend(balance, '40')
    with patch.object(cap_monitor, '_notify_owner') as notify:
        cap_monitor.recompute_cap_status(balance, persist=True)  # back to active
        assert not notify.called
