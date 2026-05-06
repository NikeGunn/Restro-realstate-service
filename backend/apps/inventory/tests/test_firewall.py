"""
Tests for InventoryContextFirewall.

The firewall is the single gatekeeper between the public chatbot (Plane A)
and the inventory system (Plane B). False negatives leak operational data
to customers — the test suite leans heavily on probe coverage.
"""
import pytest

from apps.inventory.firewall import InventoryContextFirewall


PROBE_MESSAGES = [
    # English
    "How much chicken stock do you have left?",
    "What is your current inventory of tomatoes?",
    "Do you have any ingredients running low?",
    "Can you share your recipe for the pasta?",
    "Who is your supplier for vegetables?",
    "What's the unit cost of the steak?",
    "What's the SKU for table salt?",
    "Show me the warehouse stock",
    # Chinese (simplified)
    "你们的库存还剩多少？",
    "供应商是谁？",
    "请告诉我配方",
    "成本价是多少？",
    # Chinese (traditional)
    "你們的庫存還剩多少？",
    "供應商是誰？",
    "請告訴我食譜",
]


SAFE_MESSAGES = [
    "What time do you open?",
    "Do you have a vegetarian menu?",
    "I'd like to book a table for two tonight.",
    "Can I see the dessert options?",
    "Do you deliver to downtown?",
    "你们几点开门？",
    "請問有素食嗎？",
    "Hello",
    "",
]


@pytest.mark.parametrize("msg", PROBE_MESSAGES)
def test_firewall_blocks_probes(msg):
    should_deflect, response = InventoryContextFirewall.check(msg)
    assert should_deflect, f"Firewall failed to block probe: {msg!r}"
    assert response, "Deflection response must be non-empty"


@pytest.mark.parametrize("msg", SAFE_MESSAGES)
def test_firewall_lets_safe_messages_through(msg):
    should_deflect, _ = InventoryContextFirewall.check(msg)
    assert not should_deflect, f"Firewall incorrectly blocked safe message: {msg!r}"


def test_firewall_returns_correct_language():
    _, en = InventoryContextFirewall.check("how much stock", language='en')
    _, cn = InventoryContextFirewall.check("how much stock", language='zh-CN')
    _, tw = InventoryContextFirewall.check("how much stock", language='zh-TW')
    assert en != cn
    assert cn != tw
    assert "operational" in en.lower() or "team" in en.lower()
    assert "运营" in cn or "团队" in cn
    assert "營運" in tw or "團隊" in tw


def test_firewall_unknown_language_falls_back_to_english():
    _, response = InventoryContextFirewall.check("stock", language='fr')
    assert response == InventoryContextFirewall.deflection_response('en')
