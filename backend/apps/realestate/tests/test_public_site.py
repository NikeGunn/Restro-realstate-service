"""Public SEO listings site + WhatsApp handoff (kribaat.com/realestate/properties)."""
import json
import re
from decimal import Decimal
from urllib.parse import parse_qs, unquote, urlparse

import pytest
from django.core.cache import cache

from apps.accounts.models import Location, Organization
from apps.realestate.models import PropertyListing
from apps.realestate.public_site import canonical_path

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def site(settings):
    cache.clear()
    settings.PUBLIC_WHATSAPP_NUMBER = '+977 981-4344114'
    settings.PUBLIC_SITE_URL = 'https://kribaat.com'


@pytest.fixture
def org(settings):
    o = Organization.objects.create(name='Kribaat Realestate', business_type='real_estate')
    Location.objects.create(organization=o, name='Kathmandu Office', is_primary=True, is_active=True,
                            country='Nepal', city='Kathmandu')
    settings.PUBLIC_LISTINGS_ORG = str(o.id)
    return o


def _listing(org, **kw):
    data = dict(organization=org, title='Room with Balcony near Chabahil Chowk', description='Bachelor allowed.',
                listing_type='rent', property_type='room', price=Decimal('8000'), address_line1='Chabahil',
                city='Kathmandu', neighborhood='Chabahil', country='Nepal', status='active',
                images=['https://media.kribaat.com/listings/a.jpg'])
    data.update(kw)
    return PropertyListing.objects.create(**data)


@pytest.fixture
def room(org):
    return _listing(org)


@pytest.fixture
def land(org):
    return _listing(org, title='Residential Land 5 Aana, Bhaisepati', listing_type='sale', property_type='land',
                    price=Decimal('21000000'), city='Lalitpur', neighborhood='Bhaisepati', state='Bagmati', images=[])


def _jsonld(html):
    return json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))


def test_listing_page_is_public_indexable_and_structured(client, room, land):
    r = client.get('/realestate/properties/')
    html = r.content.decode()
    assert r.status_code == 200 and 'public' in r['Cache-Control']
    assert room.title in html and land.title in html
    assert 'Rs 8,000/mo' in html and 'Rs 2.1 crore' in html         # Nepal money, never "$"
    assert '<link rel="canonical" href="https://kribaat.com/realestate/properties/">' in html
    assert 'index, follow' in html
    graph = {n['@type']: n for n in _jsonld(html)['@graph']}
    assert graph['CollectionPage']['mainEntity']['numberOfItems'] == 2
    assert graph['RealEstateAgent']['telephone'] == '+9779814344114'
    assert 'FAQPage' in graph


def test_category_city_landing_page(client, room, land):
    r = client.get('/realestate/properties/land-for-sale/lalitpur/')
    html = r.content.decode()
    assert r.status_code == 200
    assert 'Land for sale in Lalitpur' in html and land.title in html and room.title not in html
    assert client.get('/realestate/properties/land-for-sale/atlantis/').status_code == 404
    assert client.get('/realestate/properties/castles-for-sale/').status_code == 404


def test_filters_are_noindex_and_cannot_break_the_page(client, room, land):
    r = client.get('/realestate/properties/', {'max': 'abc', 'q': "'; DROP TABLE x;--", 'sort': 'evil'})
    assert r.status_code == 200 and 'noindex' in r.content.decode()
    r = client.get('/realestate/properties/', {'deal': 'rent', 'max': '10000'})
    assert room.title in r.content.decode() and land.title not in r.content.decode()


def test_detail_redirects_to_canonical_slug_and_counts_views_once(client, room):
    url = canonical_path(room)
    assert url.startswith(f"/realestate/properties/{room.reference_number.lower()}-room-with-balcony")
    r = client.get(f"/realestate/properties/{room.reference_number}/")
    assert r.status_code == 301 and r['Location'] == url
    for _ in range(3):
        r = client.get(url)
    assert r.status_code == 200
    room.refresh_from_db()
    assert room.view_count == 1                                       # refresh spam counted once
    graph = {n['@type']: n for n in _jsonld(r.content.decode())['@graph']}
    offer = graph['RealEstateListing']['offers']
    assert offer['priceCurrency'] == 'NPR' and offer['price'] == '8000'
    assert graph['RealEstateListing']['identifier'] == room.reference_number


def test_whatsapp_handoff_names_the_listing(client, room):
    r = client.get(f"/realestate/properties/{room.reference_number.lower()}/chat/")
    assert r.status_code == 302
    link = urlparse(r['Location'])
    assert link.netloc == 'wa.me' and link.path == '/9779814344114'
    text = unquote(parse_qs(link.query)['text'][0])
    assert room.reference_number in text and room.title in text and 'Rs 8,000' in text
    assert r['Cache-Control'] == 'no-store'
    room.refresh_from_db()
    assert room.whatsapp_clicks == 1
    ne = unquote(parse_qs(urlparse(client.get(f"/realestate/properties/{room.reference_number}/chat/?lang=ne")['Location']).query)['text'][0])
    assert ne.startswith('Namaste! Malai ' + room.reference_number)


def test_needs_form_goes_to_whatsapp_with_a_natural_first_message(client, room):
    r = client.get('/realestate/properties/chat/', {'type': 'room', 'deal': 'rent', 'q': 'Chabahil', 'max': '10000'})
    text = unquote(parse_qs(urlparse(r['Location']).query)['text'][0])
    assert text.startswith("Namaste! I'm looking to rent a room in Chabahil.") and 'Rs 10,000' in text
    r = client.get('/realestate/properties/chat/', {'type': 'land', 'deal': 'sale', 'q': 'Lalitpur', 'lang': 'ne'})
    text = unquote(parse_qs(urlparse(r['Location']).query)['text'][0])
    assert 'Lalitpur ma land kinna chahiyo' in text
    # Garbage is neutralised, never echoed as markup
    r = client.get('/realestate/properties/chat/', {'type': '<script>', 'q': 'x' * 500, 'max': '<b>9</b>'})
    assert r.status_code == 302 and '<script>' not in unquote(r['Location'])


def test_unpublished_draft_and_other_tenants_never_leak(client, org, room):
    hidden = _listing(org, title='Secret owner listing', is_published=False)
    other_org = Organization.objects.create(name='Other Agency', business_type='real_estate')
    foreign = _listing(other_org, title='Foreign agency flat')
    html = client.get('/realestate/properties/').content.decode()
    assert hidden.title not in html and foreign.title not in html
    assert client.get(canonical_path(hidden)).status_code == 404
    assert client.get(canonical_path(foreign)).status_code == 404
    assert client.get(f"/realestate/properties/{foreign.reference_number}/chat/").status_code == 404


def test_rented_listing_page_stays_but_is_noindex_and_out_of_lists(client, room):
    room.status = 'rented'
    room.save()
    r = client.get(canonical_path(room))
    html = r.content.decode()
    assert r.status_code == 200 and 'noindex' in html and 'no longer available' in html
    assert room.title not in client.get('/realestate/properties/').content.decode()


def test_sitemap_and_robots(client, room, land):
    xml = client.get('/sitemap.xml').content.decode()
    assert 'https://kribaat.com/realestate/properties/rooms-for-rent/' in xml
    assert 'https://kribaat.com/realestate/properties/land-for-sale/lalitpur/' in xml
    assert 'https://kribaat.com' + canonical_path(room) in xml
    robots = client.get('/robots.txt').content.decode()
    assert 'Sitemap: https://kribaat.com/sitemap.xml' in robots and 'Disallow: /api/' in robots


def test_misconfigured_org_is_404_not_500(client, settings):
    settings.PUBLIC_LISTINGS_ORG = '00000000-0000-0000-0000-000000000000'
    assert client.get('/realestate/properties/').status_code == 404
    assert client.get('/sitemap.xml').status_code == 200


def test_no_whatsapp_number_hides_chat_buttons(client, settings, room):
    settings.PUBLIC_WHATSAPP_NUMBER = ''
    html = client.get(canonical_path(room)).content.decode()
    assert '/chat/' not in html
    assert client.get(f"/realestate/properties/{room.reference_number}/chat/").status_code == 404
