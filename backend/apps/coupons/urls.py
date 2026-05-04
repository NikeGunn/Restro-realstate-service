from django.urls import path

from .views import CouponRedeemView, CouponValidateView

urlpatterns = [
    path('validate/', CouponValidateView.as_view(), name='coupon-validate'),
    path('redeem/', CouponRedeemView.as_view(), name='coupon-redeem'),
]
