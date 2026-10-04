"""
Dashboard property form → API.

Regression (2026-10-04): every edit of a Nepal listing failed with "Failed to save property"
because the seeded listings have no postal code and the API required one
({"postal_code": ["This field may not be blank."]}). Photos uploaded through their own
endpoint, so they appeared while the Update button failed.
"""
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Organization, OrganizationMembership, User
from apps.realestate.models import PropertyListing

pytestmark = pytest.mark.django_db


@pytest.fixture
def org():
    return Organization.objects.create(name='Agency', business_type='real_estate')


@pytest.fixture
def client(org):
    u = User.objects.create_user(username='o@x.com', email='o@x.com', password='pw-12345678')
    OrganizationMembership.objects.create(user=u, organization=org, role='owner')
    c = APIClient()
    c.force_authenticate(u)
    return c


def _payload(org, **over):
    """Exactly what PropertiesPage.tsx sends."""
    p = dict(organization=str(org.id), title='Residential Land 5 Aana, Bhaisepati', description='Land.',
             property_type='land', listing_type='sale', status='active', price=21000000.0,
             address_line1='Bhaisepati, Lalitpur', address_line2='', city='Lalitpur', state='Bagmati',
             postal_code='', country='Nepal', bedrooms=None, bathrooms=None, square_feet=None,
             lot_size=1711, year_built=None, is_featured=True)
    p.update(over)
    return p


def test_update_listing_without_postal_code_succeeds(org, client):
    listing = PropertyListing.objects.create(
        organization=org, title='Land', description='x', listing_type='sale', property_type='land',
        price=Decimal('21000000'), address_line1='Bhaisepati', city='Lalitpur', state='Bagmati', postal_code='',
        country='Nepal', images=['https://media.kribaat.com/listings/a.jpg'])
    r = client.put(f'/api/realestate/properties/{listing.id}/', _payload(org), format='json')
    assert r.status_code == 200, r.data
    listing.refresh_from_db()
    assert listing.lot_size == 1711 and listing.is_featured
    assert listing.images == ['https://media.kribaat.com/listings/a.jpg']   # PUT never wipes photos


def test_create_without_state_or_postal_code(org, client):
    r = client.post('/api/realestate/properties/', _payload(org, state='', status='coming_soon'), format='json')
    assert r.status_code == 201, r.data


def test_invalid_status_is_a_field_error_not_a_crash(org, client):
    r = client.post('/api/realestate/properties/', _payload(org, status='draft'), format='json')
    assert r.status_code == 400 and 'status' in r.data


def test_reorder_photos_sets_cover(org, client):
    a, b, c = (f'https://media.kribaat.com/listings/{n}.jpg' for n in 'abc')
    listing = PropertyListing.objects.create(
        organization=org, title='Room', description='x', listing_type='rent', property_type='room',
        price=Decimal('8000'), address_line1='a', city='Kathmandu', images=[a, b, c])
    url = f'/api/realestate/properties/{listing.id}/photos/order/'
    r = client.put(url, {'images': [c, a, b]}, format='json')
    assert r.status_code == 200 and r.data['images'] == [c, a, b]
    # Not a permutation (dropped / foreign URL) → rejected, order unchanged.
    for bad in ([c, a], [c, a, 'https://evil.example/x.jpg'], 'nope'):
        assert client.put(url, {'images': bad}, format='json').status_code == 400
    listing.refresh_from_db()
    assert listing.images == [c, a, b]


def test_reorder_other_org_listing_is_404(org, client):
    other = Organization.objects.create(name='Other', business_type='real_estate')
    listing = PropertyListing.objects.create(
        organization=other, title='Room', description='x', listing_type='rent', property_type='room',
        price=Decimal('8000'), address_line1='a', city='Kathmandu', images=['https://x/a.jpg'])
    r = client.put(f'/api/realestate/properties/{listing.id}/photos/order/', {'images': ['https://x/a.jpg']},
                   format='json')
    assert r.status_code == 404
