"""
Billing plan constants — the single source of truth for the seeded plans.

Seed migration (0002) and the provisioning service both read these so the
admin-seeded `SubscriptionPlan` rows and runtime defaults never drift.
HKD 200 "Growth" = power, 20 monthly image credits (REQUIREMENTS § Phase 6).
"""

# slug, name, plan_code, price_hkd, monthly_image_credits, enabled_modules
SEED_PLANS = [
    {
        'slug': 'basic',
        'name': 'Basic',
        'plan_code': 'basic',
        'price_hkd': '0.00',
        'monthly_image_credits': 0,
        'enabled_modules': ['chatbot_ai'],
    },
    {
        'slug': 'power',
        'name': 'Growth',
        'plan_code': 'power',
        'price_hkd': '200.00',
        'monthly_image_credits': 20,
        'enabled_modules': [
            'chatbot_ai', 'inventory_ai', 'content_studio',
        ],
    },
]

# Default spend cap when an org has no explicit UsageLimit yet.
DEFAULT_SPEND_CAP_HKD = '200.00'
DEFAULT_ALERT_PERCENT = 80
