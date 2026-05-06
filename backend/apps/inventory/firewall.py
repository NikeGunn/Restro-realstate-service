"""
InventoryContextFirewall
========================
Stateless guard that sits between the public chatbot (Plane A) and the
inventory system (Plane B). The ONLY interface between the two planes.

It does NOT touch the database. It does NOT import any inventory model.
It only inspects an incoming customer message for inventory-probing intent
and returns a safe deflection string in the conversation's detected language.

False positives (deflecting an innocent message) are acceptable.
False negatives (leaking operational data to a customer) are NOT.
"""
import re
from typing import Tuple


_INVENTORY_PROBE_PATTERNS = [
    # English
    r'\b(stock|inventory|ingredient[s]?|supplies|supply)\b',
    r'\b(how much .{0,20}(have|left|remaining|available|in stock))\b',
    r'\b(running low|reorder|purchase order|supplier|vendor)\b',
    r'\b(recipe|formula|yield|batch size)\b',
    r'\b(warehouse|storage|shelf|bin|sku|barcode)\b',
    r'\b(cost price|unit cost|wholesale|procurement|markup)\b',
    # Chinese (simplified + traditional)
    r'(库存|庫存|存货|存貨|进货|進貨|采购|採購)',
    r'(供应商|供應商|供货商|供貨商|批发|批發)',
    r'(配方|食谱|食譜|成本价|成本價|进价|進價)',
    r'(仓库|倉庫|条码|條碼|货号|貨號)',
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _INVENTORY_PROBE_PATTERNS]


_DEFLECTION_RESPONSES = {
    'en': (
        "I can help you with our menu, opening hours, bookings, and general "
        "questions about our services. For operational inquiries, please "
        "contact our team directly."
    ),
    'zh-CN': (
        "我可以帮您了解菜单、营业时间、预订和一般服务问题。"
        "如需运营相关咨询，请直接联系我们的团队。"
    ),
    'zh-TW': (
        "我可以幫您了解菜單、營業時間、訂位和一般服務問題。"
        "如需營運相關諮詢，請直接聯繫我們的團隊。"
    ),
}


class InventoryContextFirewall:
    """Stateless, import-safe. Safe to call from anywhere — no side effects."""

    @staticmethod
    def is_inventory_probe(message: str) -> bool:
        if not message:
            return False
        return any(p.search(message) for p in _COMPILED)

    @staticmethod
    def deflection_response(language: str = 'en') -> str:
        return _DEFLECTION_RESPONSES.get(language, _DEFLECTION_RESPONSES['en'])

    @classmethod
    def check(cls, message: str, language: str = 'en') -> Tuple[bool, str]:
        """
        Returns (should_deflect, deflection_message).
        If True, caller MUST return the deflection without any AI/knowledge lookup.
        """
        if cls.is_inventory_probe(message):
            return True, cls.deflection_response(language)
        return False, ''
