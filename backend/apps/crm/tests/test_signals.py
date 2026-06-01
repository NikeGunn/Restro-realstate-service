"""Signal-integration tests: org seeding, booking + conversation sync, failure safety."""
import datetime
import pytest

from apps.accounts.models import Organization, Location
from apps.crm.models import CRMCustomer, CRMTag, CRMInteraction, InteractionType

pytestmark = pytest.mark.django_db


def test_org_creation_seeds_system_tags(db):
    org = Organization.objects.create(name='Fresh Org')
    tags = set(CRMTag.objects.filter(organization=org, is_system=True)
               .values_list('name', flat=True))
    assert tags == set(CRMTag.SYSTEM_TAGS)


def test_booking_confirmed_creates_customer_and_interaction(org):
    from apps.restaurant.models import Booking
    loc = Location.objects.create(organization=org, name='Main')
    Booking.objects.create(
        organization=org, location=loc, booking_date=datetime.date.today(),
        booking_time=datetime.time(19, 0), party_size=2,
        customer_name='Booker', customer_phone='91234567',
        status=Booking.Status.CONFIRMED,
    )
    cust = CRMCustomer.objects.filter(organization=org, phone='+85291234567').first()
    assert cust is not None
    assert CRMInteraction.objects.filter(
        customer=cust, interaction_type=InteractionType.BOOKING).exists()


def test_booking_completed_sets_last_visit(org):
    from apps.restaurant.models import Booking
    loc = Location.objects.create(organization=org, name='Main')
    today = datetime.date.today()
    Booking.objects.create(
        organization=org, location=loc, booking_date=today,
        booking_time=datetime.time(20, 0), party_size=4,
        customer_name='Diner', customer_phone='98887777',
        status=Booking.Status.COMPLETED,
    )
    cust = CRMCustomer.objects.get(organization=org, phone='+85298887777')
    assert cust.last_visit_date == today


def test_pending_booking_does_not_sync(org):
    from apps.restaurant.models import Booking
    loc = Location.objects.create(organization=org, name='Main')
    Booking.objects.create(
        organization=org, location=loc, booking_date=datetime.date.today(),
        booking_time=datetime.time(18, 0), party_size=2,
        customer_name='Maybe', customer_phone='90001111',
        status=Booking.Status.PENDING,
    )
    assert not CRMCustomer.objects.filter(organization=org, phone='+85290001111').exists()


def test_whatsapp_conversation_creates_customer(org):
    from apps.messaging.models import Conversation, Channel
    Conversation.objects.create(
        organization=org, channel=Channel.WHATSAPP,
        customer_name='WA User', customer_phone='95551234',
    )
    cust = CRMCustomer.objects.filter(organization=org, phone='+85295551234').first()
    assert cust is not None
    assert CRMInteraction.objects.filter(
        customer=cust, interaction_type=InteractionType.WHATSAPP_MESSAGE).exists()


def test_website_conversation_does_not_sync(org):
    from apps.messaging.models import Conversation, Channel
    Conversation.objects.create(
        organization=org, channel=Channel.WEBSITE,
        customer_name='Web', customer_phone='94443333',
    )
    assert not CRMCustomer.objects.filter(organization=org, phone='+85294443333').exists()


def test_booking_sync_failure_does_not_break_save(org, monkeypatch):
    # If the CRM sync raises, the booking must still save (inventory/messaging
    # downstream pattern). We force get_or_create to blow up and assert the
    # booking row is created anyway.
    from apps.restaurant.models import Booking
    from apps.crm.services import customer_service

    def _boom(*a, **k):
        raise RuntimeError('crm down')

    monkeypatch.setattr(customer_service, 'get_or_create_customer', _boom)
    loc = Location.objects.create(organization=org, name='Main')
    booking = Booking.objects.create(
        organization=org, location=loc, booking_date=datetime.date.today(),
        booking_time=datetime.time(21, 0), party_size=2,
        customer_name='Resilient', customer_phone='96665555',
        status=Booking.Status.CONFIRMED,
    )
    assert Booking.objects.filter(pk=booking.pk).exists()
    assert not CRMCustomer.objects.filter(organization=org, phone='+85296665555').exists()
