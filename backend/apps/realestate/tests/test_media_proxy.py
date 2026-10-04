"""media.kribaat.com photo proxy + domain rewrite."""
import uuid
from decimal import Decimal
from io import StringIO

import pytest
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command

from apps.accounts.models import Organization
from apps.realestate.models import PropertyListing

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def local_storage(settings, tmp_path):
    cache.clear()
    settings.MEDIA_ROOT = tmp_path
    for k in ('R2_BUCKET', 'R2_ENDPOINT_URL', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_PUBLIC_DOMAIN'):
        setattr(settings, k, '')


def _key():
    return f"listings/{uuid.uuid4()}/{uuid.uuid4()}/{uuid.uuid4().hex}.jpg"


def test_serves_photo_with_immutable_cache_and_etag(client):
    key = _key()
    default_storage.save(key, ContentFile(b'\xff\xd8\xff jpeg bytes'))
    r = client.get('/' + key, HTTP_HOST='media.kribaat.com')
    assert r.status_code == 200 and r['Content-Type'] == 'image/jpeg'
    assert 'immutable' in r['Cache-Control'] and r.content.startswith(b'\xff\xd8\xff')
    r2 = client.get('/' + key, HTTP_HOST='media.kribaat.com', HTTP_IF_NONE_MATCH=r['ETag'])
    assert r2.status_code == 304


@pytest.mark.parametrize('path', [
    '/listings/../../etc/passwd', '/listings/x.jpg', '/listings/a/b/c.png',
    f'/listings/{uuid.uuid4()}/{uuid.uuid4()}/{"0" * 32}.jpg',      # well-formed but missing
])
def test_only_listing_photo_keys_and_missing_is_404(client, path):
    assert client.get(path).status_code == 404


def test_rewrite_photo_domain_command():
    org = Organization.objects.create(name='A', business_type='real_estate')
    old = 'https://pub-x.r2.dev/listings/a.jpg'
    p = PropertyListing.objects.create(organization=org, title='t', description='d', listing_type='rent',
                                       property_type='room', price=Decimal('1'), address_line1='a', city='c',
                                       images=[old, 'https://elsewhere.example/b.jpg'])
    out = StringIO()
    call_command('rewrite_photo_domain', '--from', 'pub-x.r2.dev', '--to', 'media.kribaat.com', '--dry-run', stdout=out)
    p.refresh_from_db()
    assert p.images[0] == old and 'Would rewrite 1' in out.getvalue()
    call_command('rewrite_photo_domain', '--from', 'pub-x.r2.dev', '--to', 'media.kribaat.com', stdout=out)
    p.refresh_from_db()
    assert p.images == ['https://media.kribaat.com/listings/a.jpg', 'https://elsewhere.example/b.jpg']
