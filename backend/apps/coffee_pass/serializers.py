"""
Coffee Pass serializers.

Two families, deliberately separate:
- Dashboard serializers (owner/staff) may show operational detail.
- Public serializers show the customer ONLY their own data, and never expose
  another customer's pass, a raw token, or internal notes.

Validation that protects tenancy lives here AND in the service layer. That is
not duplication of knowledge — the serializer gives a good 400 for a typo, the
service is the invariant that holds even when called from a task or the admin.
"""
from decimal import Decimal

from rest_framework import serializers

from apps.restaurant.models import MenuItem

from .models import (
    CoffeeExperience, CoffeePass, CoffeePassPlan, CoffeePassPurchase,
    CoffeePassRedemption, PlanStatus, RoutineContext, Sentiment,
)
from .services import plan_service


# ──────────────────────────────────────────────────────────────────────
# Plans
# ──────────────────────────────────────────────────────────────────────
class MenuItemBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuItem
        fields = ['id', 'name', 'price', 'item_type', 'is_available', 'sold_out']


class CoffeePassPlanSerializer(serializers.ModelSerializer):
    eligible_items_detail = MenuItemBriefSerializer(
        source='eligible_items', many=True, read_only=True,
    )
    location_name = serializers.CharField(source='location.name', read_only=True)
    active_pass_count = serializers.SerializerMethodField()
    break_even = serializers.SerializerMethodField()
    #: The public QR path. Safe to show an owner — it is opaque and carries no PII.
    public_url_path = serializers.SerializerMethodField()

    class Meta:
        model = CoffeePassPlan
        fields = [
            'id', 'organization', 'location', 'location_name', 'name', 'description',
            'price_hkd', 'currency', 'discount_percent', 'duration_days',
            'eligible_items', 'eligible_items_detail', 'allow_neutral_feedback',
            'status', 'break_even_acknowledged', 'public_token', 'public_url_path',
            'active_pass_count', 'break_even', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'public_token', 'created_at', 'updated_at']

    def get_active_pass_count(self, obj):
        return obj.passes.filter(status='active').count()

    def get_break_even(self, obj):
        if not obj.pk:
            return None
        return plan_service.check_activation_readiness(obj)['break_even']

    def get_public_url_path(self, obj):
        return f'/public/coffee-pass/{obj.public_token}/'

    def validate_discount_percent(self, value):
        if not (Decimal('0') < value <= Decimal('50')):
            raise serializers.ValidationError('Discount must be between 0 and 50 percent.')
        return value

    def validate_price_hkd(self, value):
        if value <= 0:
            raise serializers.ValidationError('Price must be positive.')
        return value

    def validate_duration_days(self, value):
        if value <= 0:
            raise serializers.ValidationError('Duration must be at least 1 day.')
        return value

    def validate(self, attrs):
        """
        Cross-field tenancy: the location and every eligible item must belong to
        the plan's organization. MenuItem has no org column — it is reached via
        `category.organization` (Phase 3 convention).
        """
        org = attrs.get('organization') or getattr(self.instance, 'organization', None)
        location = attrs.get('location') or getattr(self.instance, 'location', None)

        if org and location and location.organization_id != org.id:
            raise serializers.ValidationError(
                {'location': 'Location does not belong to this organization.'}
            )

        items = attrs.get('eligible_items')
        if org and items:
            foreign = [i.id for i in items if i.category.organization_id != org.id]
            if foreign:
                raise serializers.ValidationError(
                    {'eligible_items': 'All eligible items must belong to this organization.'}
                )

            # A Coffee Pass may only cover coffee. The dashboard already filters
            # the picker, but the rule is enforced here too: the picker is a
            # convenience, this is the invariant. Calls the service helper so the
            # two definitions can never drift apart.
            allowed = plan_service.eligible_item_types()
            non_coffee = [i.name for i in items if i.item_type not in allowed]
            if non_coffee:
                raise serializers.ValidationError({
                    'eligible_items': (
                        'A Coffee Pass can only cover coffee items. Set the item '
                        'type to Coffee on the menu, or remove: '
                        + ', '.join(non_coffee[:5])
                    )
                })
        return attrs


class CoffeePassPlanWriteSerializer(CoffeePassPlanSerializer):
    """
    Update serializer that protects sold terms.

    Status is service-driven (activate/pause endpoints), never a free PATCH —
    otherwise a client could skip the break-even guard entirely.
    """
    class Meta(CoffeePassPlanSerializer.Meta):
        read_only_fields = [
            'id', 'public_token', 'status', 'created_at', 'updated_at',
        ]


# ──────────────────────────────────────────────────────────────────────
# Passes / purchases / redemptions (dashboard reads)
# ──────────────────────────────────────────────────────────────────────
class CoffeePassSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)
    plan_name = serializers.SerializerMethodField()
    discount_percent = serializers.SerializerMethodField()
    redemption_count = serializers.SerializerMethodField()
    total_saved_hkd = serializers.SerializerMethodField()
    is_redeemable = serializers.SerializerMethodField()

    class Meta:
        model = CoffeePass
        fields = [
            'id', 'organization', 'location', 'location_name', 'customer',
            'customer_name', 'plan', 'plan_name', 'purchase', 'status',
            'discount_percent', 'starts_at', 'expires_at', 'suspension_reason',
            'cancelled_at', 'cancel_reason', 'redemption_count', 'total_saved_hkd',
            'is_redeemable', 'created_at',
        ]
        # Every mutation goes through a service; this is a read model.
        read_only_fields = fields

    def get_plan_name(self, obj):
        return (obj.plan_snapshot or {}).get('name', '')

    def get_discount_percent(self, obj):
        return str(obj.discount_percent)

    def get_redemption_count(self, obj):
        return obj.redemptions.filter(status='redeemed').count()

    def get_total_saved_hkd(self, obj):
        from .services import webhook_service
        return str(webhook_service.savings_to_date(obj))

    def get_is_redeemable(self, obj):
        return obj.is_redeemable()


class CoffeePassPurchaseSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)

    class Meta:
        model = CoffeePassPurchase
        fields = [
            'id', 'organization', 'location', 'customer', 'customer_name', 'plan',
            'status', 'amount_hkd', 'currency', 'stripe_receipt_url',
            'refunded_amount_hkd', 'paid_at', 'created_at',
        ]
        read_only_fields = fields


class CoffeePassRedemptionSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)
    redeemed_by_email = serializers.EmailField(source='redeemed_by.email', read_only=True)

    class Meta:
        model = CoffeePassRedemption
        fields = [
            'id', 'organization', 'location', 'location_name', 'coffee_pass',
            'customer', 'customer_name', 'redeemed_by', 'redeemed_by_email',
            'eligible_subtotal_hkd', 'discount_amount_hkd', 'discount_percent_applied',
            'pos_receipt_reference', 'status', 'redeemed_at', 'voided_at',
            'void_reason', 'created_at',
        ]
        read_only_fields = fields


class CoffeeExperienceSerializer(serializers.ModelSerializer):
    """
    Owner-facing. INCLUDES the comment — the owner needs it for service recovery.
    The staff redemption endpoint uses `entitlement_service.preview` instead,
    which deliberately omits it (A.9).
    """
    customer_name = serializers.CharField(source='customer.name', read_only=True)

    class Meta:
        model = CoffeeExperience
        fields = [
            'id', 'organization', 'location', 'customer', 'customer_name',
            'sentiment', 'comment', 'routine_context', 'source',
            'offer_shown_at', 'created_at',
        ]
        read_only_fields = fields


# ──────────────────────────────────────────────────────────────────────
# Staff action inputs
# ──────────────────────────────────────────────────────────────────────
class VerificationResolveSerializer(serializers.Serializer):
    """Accepts either a scanned QR payload or a typed fallback code."""
    code = serializers.CharField(max_length=200, trim_whitespace=True)
    location = serializers.UUIDField(required=False, allow_null=True)


class RedemptionCreateSerializer(serializers.Serializer):
    verification_token_id = serializers.UUIDField()
    eligible_subtotal_hkd = serializers.DecimalField(max_digits=10, decimal_places=2)
    pos_receipt_reference = serializers.CharField(
        max_length=100, required=False, allow_blank=True, default='',
    )
    location = serializers.UUIDField(required=False, allow_null=True)

    def validate_eligible_subtotal_hkd(self, value):
        # The hard cap lives in the service (single source of truth); this is the
        # cheap early rejection so an obvious typo never reaches a transaction.
        if value < 0:
            raise serializers.ValidationError('Subtotal cannot be negative.')
        return value


class VoidSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, min_length=5)


class SuspendSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, min_length=5)


class RefundSerializer(serializers.Serializer):
    amount_hkd = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True,
    )
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')


# ──────────────────────────────────────────────────────────────────────
# Public customer inputs
# ──────────────────────────────────────────────────────────────────────
class PublicRequestCodeSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=30)


class PublicVerifyCodeSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=30)
    code = serializers.CharField(max_length=10)


class PublicExperienceSerializer(serializers.Serializer):
    sentiment = serializers.ChoiceField(choices=Sentiment.choices)
    comment = serializers.CharField(
        max_length=1000, required=False, allow_blank=True, default='',
    )
    routine_context = serializers.ChoiceField(
        choices=RoutineContext.choices, required=False, allow_blank=True, default='',
    )


class PublicCheckoutSerializer(serializers.Serializer):
    #: Client-supplied so a double-tap on a flaky mobile network can't open two
    #: Checkout sessions. Optional — the DB constraints remain the real backstop.
    idempotency_key = serializers.CharField(
        max_length=100, required=False, allow_blank=True, default='',
    )


class PublicPassSerializer(serializers.ModelSerializer):
    """The customer's own wallet view. No internal ids beyond their own pass."""
    location_name = serializers.CharField(source='location.name', read_only=True)
    plan_name = serializers.SerializerMethodField()
    discount_percent = serializers.SerializerMethodField()
    eligible_items = serializers.SerializerMethodField()
    total_saved_hkd = serializers.SerializerMethodField()
    redemption_count = serializers.SerializerMethodField()

    class Meta:
        model = CoffeePass
        fields = [
            'id', 'status', 'location_name', 'plan_name', 'discount_percent',
            'eligible_items', 'starts_at', 'expires_at', 'total_saved_hkd',
            'redemption_count',
        ]
        read_only_fields = fields

    def get_plan_name(self, obj):
        return (obj.plan_snapshot or {}).get('name', '')

    def get_discount_percent(self, obj):
        return str(obj.discount_percent)

    def get_eligible_items(self, obj):
        return [
            {'name': i.get('name', ''), 'price': i.get('price', '')}
            for i in (obj.plan_snapshot or {}).get('eligible_items', [])
        ]

    def get_total_saved_hkd(self, obj):
        from .services import webhook_service
        return str(webhook_service.savings_to_date(obj))

    def get_redemption_count(self, obj):
        return obj.redemptions.filter(status='redeemed').count()


__all__ = [
    'CoffeePassPlanSerializer', 'CoffeePassPlanWriteSerializer',
    'CoffeePassSerializer', 'CoffeePassPurchaseSerializer',
    'CoffeePassRedemptionSerializer', 'CoffeeExperienceSerializer',
    'VerificationResolveSerializer', 'RedemptionCreateSerializer',
    'VoidSerializer', 'SuspendSerializer', 'RefundSerializer',
    'PublicRequestCodeSerializer', 'PublicVerifyCodeSerializer',
    'PublicExperienceSerializer', 'PublicCheckoutSerializer',
    'PublicPassSerializer', 'MenuItemBriefSerializer', 'PlanStatus',
]
