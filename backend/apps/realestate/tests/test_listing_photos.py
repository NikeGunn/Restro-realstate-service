"""Listing photos: upload safety, storage, tenancy, and the agent sending real photos."""
import io
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import Location, Organization, OrganizationMembership, User
from apps.ai_engine.agent.tools import RealEstateTools
from apps.messaging.models import Channel, Conversation
from apps.realestate import photo_storage
from apps.realestate.models import PropertyListing

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.PUBLIC_BASE_URL = 'https://kribaat.test'
    for k in ('R2_BUCKET', 'R2_ENDPOINT_URL', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_PUBLIC_DOMAIN'):
        setattr(settings, k, '')


@pytest.fixture
def org():
    o = Organization.objects.create(name='Agency', business_type='real_estate')
    Location.objects.create(organization=o, name='KTM', is_primary=True, is_active=True, country='Nepal')
    return o


@pytest.fixture
def listing(org):
    return PropertyListing.objects.create(organization=org, title='Room, Kirtipur', description='x', listing_type='rent',
                                          property_type='room', price=Decimal('6000'), address_line1='a',
                                          city='Kirtipur', state='Bagmati', postal_code='0')


def _client(org, email='owner@x.com'):
    u = User.objects.create_user(username=email, email=email, password='pw-12345678')
    OrganizationMembership.objects.create(user=u, organization=org, role='owner')
    c = APIClient()
    c.force_authenticate(u)
    return c


def _jpeg(size=(2400, 1800), exif_gps=False, name='room.jpg'):
    img = Image.new('RGB', size, (200, 120, 40))
    buf = io.BytesIO()
    kwargs = {}
    if exif_gps:
        exif = Image.Exif()
        exif[0x8825] = {1: 'N', 2: (27.0, 40.0, 0.0)}  # GPSInfo: a landlord's home location
        kwargs['exif'] = exif.tobytes()
    img.save(buf, format='JPEG', **kwargs)
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/jpeg')


def _url(listing):
    return f'/api/realestate/properties/{listing.id}/photos/'


def test_upload_reencodes_resizes_and_strips_gps(org, listing, settings):
    r = _client(org).post(_url(listing), {'photo': [_jpeg(exif_gps=True)]}, format='multipart')
    assert r.status_code == 201 and len(r.data['images']) == 1
    url = r.data['images'][0]
    assert url.startswith('https://kribaat.test/') and f'listings/{org.id}/{listing.id}/' in url
    stored = Image.open(settings.MEDIA_ROOT / url.split('/media/')[1])
    assert max(stored.size) == 1600 and stored.format == 'JPEG'
    assert 0x8825 not in stored.getexif()          # GPS gone


@pytest.mark.parametrize('payload,name', [
    (b'%PDF-1.4 not an image', 'doc.jpg'),
    (b'<?php system($_GET["c"]); ?>', 'shell.png'),
    (b'\xff\xd8\xff' + b'garbage' * 10, 'broken.jpg'),
])
def test_non_images_and_polyglots_are_rejected(org, listing, payload, name):
    r = _client(org).post(_url(listing), {'photo': [SimpleUploadedFile(name, payload, 'image/jpeg')]},
                          format='multipart')
    assert r.status_code == 400 and r.data['errors'] and PropertyListing.objects.get().images == []


def test_oversized_and_limit(org, listing, monkeypatch):
    monkeypatch.setattr(photo_storage, 'MAX_UPLOAD_BYTES', 100)
    r = _client(org).post(_url(listing), {'photo': [_jpeg()]}, format='multipart')
    assert r.status_code == 400 and '10 MB' in r.data['errors'][0]
    monkeypatch.setattr(photo_storage, 'MAX_UPLOAD_BYTES', 10 * 1024 * 1024)
    PropertyListing.objects.filter(pk=listing.pk).update(images=[f'https://x/{i}.jpg' for i in range(15)])
    r = _client(org, 'o2@x.com').post(_url(listing), {'photo': [_jpeg()]}, format='multipart')
    assert r.status_code == 400 and 'at most 15' in r.data['errors'][0]


def test_other_org_cannot_touch_photos(org, listing):
    other = Organization.objects.create(name='Other', business_type='real_estate')
    r = _client(other, 'x@y.com').post(_url(listing), {'photo': [_jpeg()]}, format='multipart')
    assert r.status_code == 404


def test_delete_removes_url_and_file(org, listing, settings):
    c = _client(org)
    url = c.post(_url(listing), {'photo': [_jpeg()]}, format='multipart').data['images'][0]
    path = settings.MEDIA_ROOT / url.split('/media/')[1]
    assert path.exists()
    assert c.delete(_url(listing), {'url': url}, format='json').data['images'] == []
    assert not path.exists()
    assert c.delete(_url(listing), {'url': 'https://evil/x.jpg'}, format='json').status_code == 404


def test_r2_is_used_only_when_fully_configured(settings):
    assert photo_storage.r2_configured() is False
    for k in ('R2_BUCKET', 'R2_ENDPOINT_URL', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY'):
        setattr(settings, k, 'x')
    assert photo_storage.r2_configured() is False      # public domain still missing → fallback
    settings.R2_PUBLIC_DOMAIN = 'pub-x.r2.dev'
    assert photo_storage.r2_configured() is True


def test_agent_sends_only_real_uploaded_photos(org, listing):
    conv = Conversation.objects.create(organization=org, channel=Channel.WHATSAPP, customer_phone='9779800000001')
    tools = RealEstateTools(conv)
    res = tools.send_property_photos(listing.reference_number)
    assert not res['ok'] and 'NO_PHOTOS' in res['error'] and tools.attachments == []
    PropertyListing.objects.filter(pk=listing.pk).update(images=['https://cdn/a.jpg', 'https://cdn/b.jpg'])
    res = tools.send_property_photos(listing.reference_number)
    assert res['ok'] and [a['url'] for a in tools.attachments] == ['https://cdn/a.jpg', 'https://cdn/b.jpg']
    assert listing.reference_number in tools.attachments[0]['caption']
