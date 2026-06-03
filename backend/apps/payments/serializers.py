"""Payments serializers."""
from rest_framework import serializers

from .models import CreditPack, CreditPurchase


class CreditPackSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreditPack
        fields = ['id', 'slug', 'name', 'description', 'credits', 'price_hkd',
                  'currency', 'sort_order']


class CreditPurchaseSerializer(serializers.ModelSerializer):
    pack_name = serializers.CharField(source='pack.name', read_only=True)

    class Meta:
        model = CreditPurchase
        fields = ['id', 'organization', 'pack', 'pack_name', 'status', 'credits',
                  'amount_hkd', 'currency', 'stripe_receipt_url',
                  'refunded_amount_hkd', 'created_at', 'paid_at']


class CheckoutRequestSerializer(serializers.Serializer):
    organization = serializers.UUIDField()
    pack = serializers.UUIDField()
    success_url = serializers.URLField(required=False, allow_blank=True)
    cancel_url = serializers.URLField(required=False, allow_blank=True)


class RefundRequestSerializer(serializers.Serializer):
    purchase = serializers.UUIDField()
    amount_hkd = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True)
    reason = serializers.ChoiceField(
        choices=['requested_by_customer', 'duplicate', 'fraudulent'],
        required=False, default='requested_by_customer')
