"""
PUBLIC Coffee Pass URLs — mounted at /public/coffee-pass/ (no auth, throttled).

The customer page is a standalone Django template (matching the lucky_draw
pattern) so a QR scan on any old mobile browser never loads the React admin
bundle.
"""
from django.urls import path

from .public_views import (
    PublicCheckoutView, PublicExperienceView, PublicOfferView,
    PublicRequestCodeView, PublicVerificationMintView, PublicVerifyCodeView,
    PublicWalletView, StripeWebhookView,
)
from .template_views import public_customer_page

urlpatterns = [
    # Stripe webhook first — a fixed path must never be shadowed by the
    # <public_token> converter below.
    path('stripe/webhook/', StripeWebhookView.as_view(), name='coffee-pass-webhook'),

    path('<str:public_token>/', public_customer_page, name='coffee-pass-page'),
    path('<str:public_token>/offer/', PublicOfferView.as_view(), name='coffee-pass-offer'),
    path('<str:public_token>/auth/request-code/', PublicRequestCodeView.as_view(),
         name='coffee-pass-request-code'),
    path('<str:public_token>/auth/verify-code/', PublicVerifyCodeView.as_view(),
         name='coffee-pass-verify-code'),
    path('<str:public_token>/experiences/', PublicExperienceView.as_view(),
         name='coffee-pass-experience'),
    path('<str:public_token>/checkout/', PublicCheckoutView.as_view(),
         name='coffee-pass-checkout'),
    path('<str:public_token>/wallet/', PublicWalletView.as_view(),
         name='coffee-pass-wallet'),
    path('<str:public_token>/wallet/<uuid:pass_id>/verification/',
         PublicVerificationMintView.as_view(), name='coffee-pass-mint'),
]
