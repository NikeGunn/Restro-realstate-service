from rest_framework import serializers

from .models import Coupon, CouponRedemption


class CouponPublicSerializer(serializers.ModelSerializer):
    """Safe public view of a coupon (e.g. dry-run validate)."""
    class Meta:
        model = Coupon
        fields = ('code', 'description', 'plan_granted', 'duration_days')


class CouponRedemptionSerializer(serializers.ModelSerializer):
    coupon = CouponPublicSerializer(read_only=True)

    class Meta:
        model = CouponRedemption
        fields = ('id', 'coupon', 'organization', 'redeemed_at', 'granted_until')
        read_only_fields = fields


class RedeemCouponInputSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=64)
    organization = serializers.UUIDField()

    def validate_code(self, value):
        return value.strip().upper()
