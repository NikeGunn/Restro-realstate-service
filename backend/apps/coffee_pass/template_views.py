"""
Public customer PAGE — a Django-rendered template, not React.

Same reasoning as the lucky-draw entry page: customers arrive by scanning a QR
on whatever browser their phone has, so the page must stand alone with vanilla
JS and never depend on the admin bundle. It talks to the JSON endpoints on the
same path prefix.
"""
from django.shortcuts import render

from .models import CoffeePassPlan, PlanStatus


def public_customer_page(request, public_token):
    """Render the mobile-first customer flow. Unknown token -> friendly 404 page."""
    plan = (
        CoffeePassPlan.objects
        .select_related('organization', 'location')
        .filter(public_token=public_token)
        .exclude(status=PlanStatus.ARCHIVED)
        .first()
    )
    context = {
        'public_token': public_token,
        'found': plan is not None,
        'organization_name': plan.organization.name if plan else '',
        'location_name': plan.location.name if plan else '',
        # The page reads ?checkout=success|cancelled after the Stripe redirect.
        'checkout_result': request.GET.get('checkout', ''),
    }
    return render(
        request, 'coffee_pass/customer.html', context, status=200 if plan else 404,
    )
