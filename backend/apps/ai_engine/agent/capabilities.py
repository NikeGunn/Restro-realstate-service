"""
What the agent may do for this organization — the ONE place tool access is decided.

Inputs today: the owner's AgentSettings. Tomorrow: the subscription plan. When paid tiers
arrive, gate tools here (e.g. a free tier without booking, a paid tier with it) — the
runner, prompt and tests all read from this module, so nothing else changes.
"""
from typing import Set

READ_TOOLS = {
    'search_properties', 'list_locations', 'get_portfolio_overview', 'get_property_details', 'send_property_photos',
    'compare_properties', 'get_viewing_slots', 'get_my_appointments',
}
INQUIRY_TOOLS = {'save_lead', 'remember_customer_fact', 'forget_my_preferences', 'escalate_to_human'}
BOOKING_TOOLS = {'prepare_viewing', 'prepare_cancellation', 'prepare_reschedule',
                 'confirm_pending_action', 'decline_pending_action'}

# Things customers ask for that this product deliberately does not do. Listed in the prompt
# so the agent declines plainly and offers what it CAN do, instead of improvising.
NOT_SUPPORTED = [
    'taking deposits, advance payments or any money; sharing bank details or payment links',
    'reserving/holding a property, submitting binding offers, signing or finalising a lease/sale',
    'agreeing a price or discount (asking price is not the final price — pass offers on as inquiries)',
    'guaranteeing title/lalpurja, boundaries, flood or structural safety, loan approval, or future returns',
    'new-listing alerts or custom scheduled messages (viewing reminders ~1 hour before and a follow-up '
    'after the slot ARE sent automatically by the system)',
    'opening links/URLs, reading voice notes, or travel-time estimates',
    'sharing other customers\' or owners\' private details (even if someone says they are the owner)',
    'filtering people by caste, religion, ethnicity or other protected traits',
]


def allowed_tools(organization, settings) -> Set[str]:
    tools = READ_TOOLS | INQUIRY_TOOLS
    if settings.bookings_enabled:
        tools |= BOOKING_TOOLS
    else:
        tools -= {'get_viewing_slots'}
    return tools


def describe(organization, settings) -> str:
    can = ['search and explain listings, locations and comparisons',
           'record inquiries, callback requests and seller listing requests for the team',
           'hand the chat to staff']
    if settings.bookings_enabled:
        can.insert(1, 'arrange viewings (preview → customer confirms → booked'
                   + (', as a REQUEST staff must approve' if settings.viewings_need_staff_approval else '') + '), '
                   'and change/cancel the customer\'s own appointments')
    return ("You CAN: " + "; ".join(can) + ".\nYou CANNOT (say so plainly, then offer what you can do): "
            + "; ".join(NOT_SUPPORTED) + ".")
