"""
Lucky Draw admin (Phase 2).

Every model registered. LuckyDrawEntry is APPEND-ONLY in the admin (no add/
change/delete) per the cross-cutting Admin convention. Prizes are inline on the
campaign; QR codes are inline too.
"""
from django.contrib import admin

from .models import (
    LuckyDrawCampaign, LuckyDrawPrize, LuckyDrawEntry, LuckyDrawQRCode,
)


class LuckyDrawPrizeInline(admin.TabularInline):
    model = LuckyDrawPrize
    extra = 0
    readonly_fields = ('wins_today_count', 'wins_total_count', 'created_at')


class LuckyDrawQRCodeInline(admin.TabularInline):
    model = LuckyDrawQRCode
    extra = 0
    readonly_fields = ('url_token', 'scan_count', 'created_at')


@admin.register(LuckyDrawCampaign)
class LuckyDrawCampaignAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'status', 'start_date', 'end_date',
                    'deliver_coupon_via_whatsapp', 'referral_enabled', 'created_at')
    list_filter = ('status', 'referral_enabled', 'deliver_coupon_via_whatsapp')
    search_fields = ('name', 'organization__name')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [LuckyDrawPrizeInline, LuckyDrawQRCodeInline]


@admin.register(LuckyDrawPrize)
class LuckyDrawPrizeAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'campaign', 'discount_percent', 'weight',
                    'wins_today_count', 'wins_total_count', 'active')
    list_filter = ('active',)
    search_fields = ('label', 'campaign__name')
    readonly_fields = ('wins_today_count', 'wins_total_count', 'created_at')


@admin.register(LuckyDrawEntry)
class LuckyDrawEntryAdmin(admin.ModelAdmin):
    list_display = ('customer_name', 'campaign', 'status', 'coupon_code',
                    'prize', 'whatsapp_sent_at', 'entered_at')
    list_filter = ('status', 'consent_given', 'campaign')
    search_fields = ('customer_name', 'phone', 'coupon_code', 'referral_token')
    readonly_fields = [f.name for f in LuckyDrawEntry._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LuckyDrawQRCode)
class LuckyDrawQRCodeAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'campaign', 'scan_count', 'created_at')
    search_fields = ('label', 'campaign__name', 'url_token')
    readonly_fields = ('url_token', 'scan_count', 'created_at')
