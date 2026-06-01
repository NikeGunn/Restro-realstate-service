"""Lucky Draw serializers (Phase 2)."""
from rest_framework import serializers

from .models import (
    LuckyDrawCampaign, LuckyDrawPrize, LuckyDrawEntry, LuckyDrawQRCode,
)


class LuckyDrawPrizeSerializer(serializers.ModelSerializer):
    win_probability = serializers.SerializerMethodField()

    class Meta:
        model = LuckyDrawPrize
        fields = [
            'id', 'campaign', 'label', 'discount_percent', 'weight',
            'max_wins_per_day', 'max_total_wins', 'wins_today_count',
            'wins_total_count', 'active', 'win_probability', 'created_at',
        ]
        read_only_fields = ['wins_today_count', 'wins_total_count', 'created_at']

    def get_win_probability(self, obj):
        """Approximate probability across this campaign's active prizes."""
        prizes = list(obj.campaign.prizes.filter(active=True))
        total = sum(p.weight for p in prizes) or 0
        if total == 0 or not obj.active:
            return 0.0
        return round(obj.weight / total, 4)


class LuckyDrawCampaignSerializer(serializers.ModelSerializer):
    prizes = LuckyDrawPrizeSerializer(many=True, read_only=True)
    entry_count = serializers.SerializerMethodField()
    max_discount = serializers.SerializerMethodField()

    class Meta:
        model = LuckyDrawCampaign
        fields = [
            'id', 'organization', 'name', 'description', 'status',
            'start_date', 'end_date',
            'daily_entry_limit_per_customer', 'total_entry_limit_per_customer',
            'requires_name', 'requires_phone', 'requires_email',
            'consent_text', 'privacy_notice_text', 'default_language',
            'deliver_coupon_via_whatsapp', 'referral_enabled',
            'referral_bonus_type', 'coupon_validity_days', 'tag_redeemers_as_buffet',
            'prizes', 'entry_count', 'max_discount', 'created_at', 'updated_at',
        ]
        read_only_fields = ['status', 'created_at', 'updated_at']

    def get_entry_count(self, obj):
        return obj.entries.count()

    def get_max_discount(self, obj):
        pcts = [p.discount_percent for p in obj.prizes.filter(active=True)]
        return max(pcts) if pcts else 0


class LuckyDrawEntrySerializer(serializers.ModelSerializer):
    prize_discount = serializers.SerializerMethodField()

    class Meta:
        model = LuckyDrawEntry
        fields = [
            'id', 'campaign', 'crm_customer', 'customer_name', 'phone', 'email',
            'table_number', 'consent_given', 'prize', 'prize_discount',
            'coupon_code', 'status', 'referred_by_entry', 'referral_count',
            'whatsapp_sent_at', 'reminder_sent_at', 'entered_at', 'drawn_at',
            'expires_at', 'redeemed_at', 'redeemed_by',
        ]
        read_only_fields = fields  # entries are created via the public pipeline

    def get_prize_discount(self, obj):
        return obj.prize.discount_percent if obj.prize else None


class LuckyDrawQRCodeSerializer(serializers.ModelSerializer):
    entry_url = serializers.SerializerMethodField()

    class Meta:
        model = LuckyDrawQRCode
        fields = [
            'id', 'campaign', 'label', 'qr_image', 'poster_image',
            'url_token', 'scan_count', 'entry_url', 'created_at',
        ]
        read_only_fields = ['qr_image', 'poster_image', 'url_token', 'scan_count', 'created_at']

    def get_entry_url(self, obj):
        from .services import qr_service
        return qr_service.get_campaign_entry_url(obj)


# ── Action / public payload serializers ───────────────────────────────
class PrizeWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = LuckyDrawPrize
        fields = [
            'label', 'discount_percent', 'weight', 'max_wins_per_day',
            'max_total_wins', 'active',
        ]


class QRCodeCreateSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')


class PublicEntrySerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default='')
    email = serializers.EmailField(required=False, allow_blank=True, default='')
    table_number = serializers.CharField(max_length=20, required=False, allow_blank=True, default='')
    consent_given = serializers.BooleanField(default=False)
    referral_token = serializers.CharField(max_length=32, required=False, allow_blank=True, default='')
    idempotency_key = serializers.CharField(max_length=128, required=False, allow_blank=True, default='')


class RedeemSerializer(serializers.Serializer):
    coupon_code = serializers.CharField(max_length=20)
