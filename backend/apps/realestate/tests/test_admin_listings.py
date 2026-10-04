"""Django admin listing management (/admin/realestate/propertylisting/), incl. the photo manager."""
import io
import json
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.accounts.models import Organization, User
from apps.realestate.models import PropertyListing

pytestmark = pytest.mark.django_db
URL = '/admin/realestate/propertylisting/'


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.PUBLIC_BASE_URL = 'https://kribaat.test'
    for k in ('R2_BUCKET', 'R2_ENDPOINT_URL', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_PUBLIC_DOMAIN'):
        setattr(settings, k, '')


@pytest.fixture
def admin_client(client):
    u = User.objects.create_superuser(username='nikhil@nikhil.com', email='nikhil@nikhil.com', password='pw-12345678')
    client.force_login(u)
    return client


@pytest.fixture
def org():
    return Organization.objects.create(name='Kribaat Realestate', business_type='real_estate')


def _jpeg(name='room.jpg', size=(800, 600)):
    buf = io.BytesIO()
    Image.new('RGB', size, (90, 140, 110)).save(buf, format='JPEG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/jpeg')


def _form(org, **over):
    data = {'organization': str(org.id), 'title': 'Room near Chabahil Chowk', 'description': 'Balcony.',
            'property_type': 'room', 'listing_type': 'rent', 'status': 'active', 'is_published': 'on',
            'price': '8000', 'rent_period': 'monthly', 'address_line1': 'Chabahil', 'city': 'Kathmandu',
            'country': 'Nepal', 'features': '[]', 'amenities': '[]', 'photo_order': '[]'}
    data.update(over)
    return data


def test_changelist_and_add_page_render(admin_client, org):
    PropertyListing.objects.create(organization=org, title='Land', description='x', listing_type='sale',
                                   property_type='land', price=Decimal('21000000'), address_line1='a',
                                   city='Lalitpur', country='Nepal', images=['https://media.kribaat.com/a.jpg'])
    r = admin_client.get(URL)
    assert r.status_code == 200 and b'Rs 2,10,00,000' in r.content and b'View on website' in r.content
    r = admin_client.get(URL + 'add/')
    html = r.content.decode()
    assert r.status_code == 200 and 'enctype="multipart/form-data"' in html and 'Drag & drop photos' in html


def test_create_listing_with_photos_no_postal_code(admin_client, org):
    r = admin_client.post(URL + 'add/', _form(org, new_photos=[_jpeg('a.jpg'), _jpeg('b.png')]))
    assert r.status_code == 302, r.content.decode()[:2000]
    listing = PropertyListing.objects.get()
    assert len(listing.images) == 2 and listing.postal_code == '' and listing.state == ''
    assert all(f'listings/{org.id}/{listing.id}/' in u for u in listing.images)


def test_reorder_and_remove_photos(admin_client, org):
    admin_client.post(URL + 'add/', _form(org, new_photos=[_jpeg('a.jpg'), _jpeg('b.jpg'), _jpeg('c.jpg')]))
    listing = PropertyListing.objects.get()
    a, b, c = listing.images
    r = admin_client.post(f'{URL}{listing.id}/change/', _form(org, photo_order=json.dumps([c, a])))  # drop b, c = cover
    assert r.status_code == 302
    listing.refresh_from_db()
    assert listing.images == [c, a]


def test_foreign_urls_cannot_be_injected(admin_client, org):
    admin_client.post(URL + 'add/', _form(org, new_photos=[_jpeg()]))
    listing = PropertyListing.objects.get()
    keep = listing.images[0]
    admin_client.post(f'{URL}{listing.id}/change/', _form(org, photo_order=json.dumps([keep, 'https://evil.example/x.jpg'])))
    listing.refresh_from_db()
    assert listing.images == [keep]


def test_bad_file_is_a_form_error_and_nothing_is_saved(admin_client, org):
    bad = SimpleUploadedFile('shell.jpg', b'<?php system($_GET[c]); ?>', content_type='image/jpeg')
    r = admin_client.post(URL + 'add/', _form(org, new_photos=[bad]))
    assert r.status_code == 200 and 'not a readable image' in r.content.decode()
    assert PropertyListing.objects.count() == 0


def test_photo_limit_enforced(admin_client, org):
    files = [_jpeg(f'{i}.jpg', (40, 30)) for i in range(16)]
    r = admin_client.post(URL + 'add/', _form(org, new_photos=files))
    assert r.status_code == 200 and 'at most 15 photos' in r.content.decode()


def test_bulk_actions(admin_client, org):
    p = PropertyListing.objects.create(organization=org, title='Flat', description='x', listing_type='rent',
                                       property_type='apartment', price=Decimal('25000'), address_line1='a',
                                       city='Pokhara', country='Nepal')
    admin_client.post(URL, {'action': 'mark_rented', '_selected_action': [str(p.id)]})
    admin_client.post(URL, {'action': 'unpublish', '_selected_action': [str(p.id)]})
    p.refresh_from_db()
    assert p.status == 'rented' and p.is_published is False
