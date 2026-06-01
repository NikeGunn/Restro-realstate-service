"""
Public entry PAGE (Phase 2) — a Django-rendered HTML page (NOT React).

Customers scan a QR on arbitrary/old mobile browsers, so this page must stand
alone with vanilla JS and not depend on the React admin bundle. It talks to the
JSON endpoints (config/ and enter/) on the same path.
"""
from django.shortcuts import render

from .models import LuckyDrawQRCode


def public_entry_page(request, url_token):
    """Render the mobile-first entry form. Missing token -> a friendly 404 page."""
    qr = (
        LuckyDrawQRCode.objects.select_related('campaign__organization')
        .filter(url_token=url_token)
        .first()
    )
    referral_token = request.GET.get('ref', '')
    context = {
        'url_token': url_token,
        'found': qr is not None,
        'referral_token': referral_token,
        'default_language': qr.campaign.default_language if qr else 'zh-TW',
    }
    return render(request, 'lucky_draw/entry_form.html', context, status=200 if qr else 404)
