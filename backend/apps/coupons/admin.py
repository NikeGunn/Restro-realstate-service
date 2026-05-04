"""Django admin for the coupon system."""
from django.contrib import admin, messages
from django.db import models, transaction
from django.utils import timezone
from django.utils.html import format_html

from apps.accounts.models import Organization

from .models import Coupon, CouponRedemption


class CouponRedemptionInline(admin.TabularInline):
    model = CouponRedemption
    extra = 0
    can_delete = False
    fields = ('organization', 'user', 'redeemed_at', 'granted_until')
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'plan_granted', 'duration_days',
        'redemptions_display', 'status_badge',
        'valid_until', 'created_at',
    )
    list_filter = ('is_active', 'plan_granted')
    search_fields = ('code', 'description')
    readonly_fields = ('id', 'redemption_count', 'created_at', 'updated_at', 'created_by')
    actions = ('activate_coupons', 'deactivate_coupons', 'hard_delete_with_redemptions')
    inlines = (CouponRedemptionInline,)

    fieldsets = (
        ('Code', {
            'fields': ('code', 'description', 'is_active'),
            'description': 'Codes are stored uppercased. Share the code with users exactly as entered.',
        }),
        ('Grant', {
            'fields': ('plan_granted', 'duration_days'),
            'description': 'What plan tier and for how long the coupon grants on redemption.',
        }),
        ('Limits', {
            'fields': ('max_redemptions', 'redemption_count', 'valid_from', 'valid_until'),
            'description': 'Leave max_redemptions blank for unlimited. valid_from/until are optional date windows.',
        }),
        ('Audit', {'fields': ('id', 'created_at', 'updated_at', 'created_by')}),
    )

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description='Redemptions')
    def redemptions_display(self, obj):
        cap = '∞' if obj.max_redemptions is None else obj.max_redemptions
        return f'{obj.redemption_count} / {cap}'

    @admin.display(description='Status')
    def status_badge(self, obj):
        ok, reason = obj.check_redeemable()
        if ok:
            return format_html('<span style="color:#0a7d2c;font-weight:600;">● Active</span>')
        return format_html('<span style="color:#9a3412;" title="{}">● {}</span>', reason, reason)

    @admin.action(description='Activate selected coupons')
    def activate_coupons(self, request, queryset):
        n = queryset.update(is_active=True)
        self.message_user(request, f'{n} coupon(s) activated.')

    @admin.action(description='Deactivate selected coupons')
    def deactivate_coupons(self, request, queryset):
        n = queryset.update(is_active=False)
        self.message_user(request, f'{n} coupon(s) deactivated.')

    # --- Soft-delete: admin's "Delete selected" archives instead of hard-deleting. -----
    # FAANG pattern (Stripe/Shopify): promo codes are never hard-deleted by default,
    # because their redemptions are part of the audit trail. "Delete" really means
    # "stop accepting this code from now on" → just set is_active=False.

    def get_actions(self, request):
        actions = super().get_actions(request)
        # Replace Django's built-in hard-delete with our soft-delete.
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def delete_model(self, request, obj):
        """Single-object delete (from change form) → soft-archive."""
        obj.is_active = False
        obj.save(update_fields=['is_active', 'updated_at'])
        self.message_user(
            request,
            f'Coupon "{obj.code}" archived (set inactive). It will stop accepting '
            f'redemptions immediately. Use "Permanently delete" if you also need to '
            f'remove the redemption history.',
            level=messages.WARNING,
        )

    def delete_queryset(self, request, queryset):
        """Bulk delete from list page → soft-archive."""
        n = queryset.update(is_active=False)
        self.message_user(
            request,
            f'{n} coupon(s) archived (set inactive). They will stop accepting '
            f'redemptions immediately.',
            level=messages.WARNING,
        )

    @admin.action(description='⚠ Permanently delete (incl. all redemption history)')
    def hard_delete_with_redemptions(self, request, queryset):
        """Genuinely remove coupons and all their redemption rows.

        Use this only when you really want the audit trail gone (e.g. test data
        cleanup). Production policy should normally be "deactivate, never delete."
        """
        total_redemptions = 0
        coupons_deleted = 0
        for coupon in queryset:
            with transaction.atomic():
                deleted_count, _ = CouponRedemption.objects.filter(coupon=coupon).delete()
                total_redemptions += deleted_count
                coupon.delete()
                coupons_deleted += 1
        self.message_user(
            request,
            f'Hard-deleted {coupons_deleted} coupon(s) and {total_redemptions} '
            f'redemption record(s).',
            level=messages.SUCCESS,
        )


@admin.register(CouponRedemption)
class CouponRedemptionAdmin(admin.ModelAdmin):
    list_display = ('coupon', 'organization', 'user', 'redeemed_at', 'granted_until', 'still_active')
    list_filter = ('coupon__plan_granted',)
    search_fields = ('coupon__code', 'organization__name', 'user__email')
    readonly_fields = ('coupon', 'organization', 'user', 'redeemed_at', 'granted_until')
    actions = ('revoke_redemption',)

    def has_add_permission(self, request):
        return False

    @admin.display(boolean=True, description='Active')
    def still_active(self, obj):
        return obj.granted_until > timezone.now()

    @admin.action(description='Revoke selected redemptions (downgrade org + free slot)')
    def revoke_redemption(self, request, queryset):
        """Roll back the redemption: org back to BASIC, decrement counter, delete redemption.

        After this the (coupon, organization) slot is free, so the org could redeem
        the same code again if you want to give them another chance.
        """
        revoked = 0
        for redemption in queryset.select_related('coupon', 'organization'):
            with transaction.atomic():
                org = redemption.organization
                # Only downgrade if this redemption is what's currently granting the plan.
                # If the org has redeemed something else later, leave the live grant alone.
                latest = (
                    CouponRedemption.objects
                    .filter(organization=org)
                    .order_by('-redeemed_at')
                    .first()
                )
                if latest and latest.pk == redemption.pk:
                    org.plan = Organization.Plan.BASIC
                    org.plan_expires_at = None
                    org.save(update_fields=['plan', 'plan_expires_at', 'updated_at'])
                Coupon.objects.filter(pk=redemption.coupon_id).update(
                    redemption_count=models.F('redemption_count') - 1
                )
                redemption.delete()
                revoked += 1
        self.message_user(
            request, f'Revoked {revoked} redemption(s).', level=messages.SUCCESS
        )
