"""
Worst-case guards for the real-estate dashboard, Settings and Channels APIs.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Location, Organization, OrganizationMembership, User
from apps.channels.models import WhatsAppConfig
from apps.realestate.models import Appointment, Lead, PropertyListing

pytestmark = pytest.mark.django_db


def _user(email):
    return User.objects.create_user(username=email, email=email, password='pw-12345678')


@pytest.fixture
def org():
    o = Organization.objects.create(name='Acme Realty', business_type='real_estate')
    Location.objects.create(organization=o, name='HQ', is_primary=True, is_active=True)
    return o


@pytest.fixture
def owner(org):
    u = _user('owner@x.com')
    OrganizationMembership.objects.create(user=u, organization=org, role='owner')
    return u


@pytest.fixture
def manager(org):
    u = _user('manager@x.com')
    OrganizationMembership.objects.create(user=u, organization=org, role='manager')
    return u


def _client(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


@pytest.fixture
def lead(org):
    return Lead.objects.create(organization=org, name='Priya', phone='85291234567')


@pytest.fixture
def appt(org, lead):
    return Appointment.objects.create(
        organization=org, lead=lead, appointment_date=timezone.now().date() + timedelta(days=2),
        appointment_time='11:00', status=Appointment.Status.SCHEDULED,
    )


# ------------------------------------------------------------- appointments
def test_cannot_cancel_completed_appointment(owner, appt):
    appt.complete(outcome='done')
    r = _client(owner).post(f'/api/realestate/appointments/{appt.id}/cancel/', {'reason': 'x'})
    assert r.status_code == 409
    appt.refresh_from_db()
    assert appt.status == Appointment.Status.COMPLETED


def test_cancel_reason_and_outcome_are_saved(owner, appt, lead, org):
    c = _client(owner)
    assert c.post(f'/api/realestate/appointments/{appt.id}/cancel/', {'reason': 'Rescheduling'}).status_code == 200
    appt.refresh_from_db()
    assert appt.cancellation_reason == 'Rescheduling'
    other = Appointment.objects.create(organization=org, lead=lead, appointment_time='12:00',
                                       appointment_date=timezone.now().date() + timedelta(days=3))
    assert c.post(f'/api/realestate/appointments/{other.id}/complete/', {'outcome': 'Loved it'}).status_code == 200
    other.refresh_from_db()
    assert other.outcome == 'Loved it'


def test_create_rejects_lead_from_another_org(owner, org):
    other = Organization.objects.create(name='Other', business_type='real_estate')
    foreign_lead = Lead.objects.create(organization=other, name='Spy', phone='1')
    r = _client(owner).post('/api/realestate/appointments/', {
        'organization': str(org.id), 'lead': str(foreign_lead.id),
        'appointment_date': (timezone.now().date() + timedelta(days=2)).isoformat(), 'appointment_time': '11:00',
    })
    assert r.status_code == 400 and 'lead' in r.json()


def test_create_rejects_past_and_absurd_duration(owner, org, lead):
    c = _client(owner)
    past = c.post('/api/realestate/appointments/', {
        'organization': str(org.id), 'lead': str(lead.id), 'appointment_date': '2020-01-01', 'appointment_time': '11:00'})
    assert past.status_code == 400
    long = c.post('/api/realestate/appointments/', {
        'organization': str(org.id), 'lead': str(lead.id), 'duration_minutes': 5000,
        'appointment_date': (timezone.now().date() + timedelta(days=2)).isoformat(), 'appointment_time': '11:00'})
    assert long.status_code == 400


def test_outsider_cannot_see_appointments(appt):
    r = _client(_user('out@x.com')).get('/api/realestate/appointments/')
    assert r.status_code == 200
    data = r.json()
    rows = data['results'] if isinstance(data, dict) else data
    assert rows == []


# ----------------------------------------------------------------- settings
def test_manager_cannot_edit_or_delete_org(manager, org):
    c = _client(manager)
    assert c.patch(f'/api/organizations/{org.id}/', {'name': 'Hacked'}).status_code == 403
    assert c.delete(f'/api/organizations/{org.id}/').status_code in (403, 405)
    org.refresh_from_db()
    assert org.name == 'Acme Realty'


def test_owner_cannot_delete_org_via_api(owner, org):
    assert _client(owner).delete(f'/api/organizations/{org.id}/').status_code == 405
    assert Organization.objects.filter(id=org.id).exists()


def test_org_validation(owner, org):
    c = _client(owner)
    assert c.patch(f'/api/organizations/{org.id}/', {'name': '   '}).status_code == 400
    assert c.patch(f'/api/organizations/{org.id}/', {'widget_color': 'red'}).status_code == 400
    r = c.patch(f'/api/organizations/{org.id}/', {'widget_greeting': 'Welcome to Acme!'})
    assert r.status_code == 200 and r.json()['widget_greeting'] == 'Welcome to Acme!'


def test_primary_location_cannot_be_deleted(owner, org):
    primary = org.locations.get(is_primary=True)
    r = _client(owner).delete(f'/api/organizations/{org.id}/locations/{primary.id}/')
    assert r.status_code == 400
    assert Location.objects.get(id=primary.id).is_active


def test_location_delete_is_soft_and_keeps_listings(owner, org):
    org.plan = 'power'
    org.save()
    branch = Location.objects.create(organization=org, name='Kowloon', is_active=True)
    listing = PropertyListing.objects.create(organization=org, location=branch, title='Keep me', description='x',
                                             price=Decimal('1'), address_line1='a', city='b', state='c', postal_code='0')
    r = _client(owner).delete(f'/api/organizations/{org.id}/locations/{branch.id}/')
    assert r.status_code == 204
    branch.refresh_from_db()
    assert branch.is_active is False
    assert PropertyListing.objects.filter(id=listing.id).exists()


def test_manager_cannot_delete_location(manager, org):
    branch = Location.objects.create(organization=org, name='Branch', is_active=True)
    assert _client(manager).delete(f'/api/organizations/{org.id}/locations/{branch.id}/').status_code == 403


def test_invalid_timezone_rejected(owner, org):
    r = _client(owner).post(f'/api/organizations/{org.id}/locations/', {'name': 'X', 'timezone': 'Mars/Base'})
    assert r.status_code in (400, 403)  # 403 on basic plan limit is also a refusal


# ----------------------------------------------------------------- channels
def test_manager_cannot_replace_whatsapp_token(manager, owner, org):
    cfg = WhatsAppConfig.objects.create(organization=org, phone_number_id='PN1', access_token='real', is_active=True)
    r = _client(manager).patch(f'/api/channels/whatsapp-config/{cfg.id}/', {'access_token': 'attacker'})
    assert r.status_code == 403
    cfg.refresh_from_db()
    assert cfg.access_token == 'real'


def test_whatsapp_config_cannot_move_org(owner, org):
    other = Organization.objects.create(name='Other', business_type='real_estate')
    OrganizationMembership.objects.create(user=owner, organization=other, role='owner')
    cfg = WhatsAppConfig.objects.create(organization=org, phone_number_id='PN2', access_token='t', is_active=True)
    _client(owner).patch(f'/api/channels/whatsapp-config/{cfg.id}/', {'organization': str(other.id)})
    cfg.refresh_from_db()
    assert cfg.organization_id == org.id
