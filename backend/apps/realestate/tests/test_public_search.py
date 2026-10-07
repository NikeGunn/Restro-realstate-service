"""
Hero search + filter bar on kribaat.com/realestate/properties (prod bugs 2026-10-04):
- "50 lakh", "Rs 15000", "2 crore" were silently ignored, so every listing showed.
- The placeholder's own example "Chabahil, Lalitpur" returned nothing (words were AND-ed, comma kept).
- "ktm" returned nothing although Kathmandu has listings.
- Rent + Land (land is only for sale) was a dead end.
"""
import re
from decimal import Decimal

import pytest
from django.core.cache import cache

from apps.accounts.models import Location, Organization
from apps.realestate.models import PropertyListing
from apps.realestate.public_site import parse_budget

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


def _l(org, title, deal, ptype, price, city, hood):
    return PropertyListing.objects.create(
        organization=org, title=title, description=title, listing_type=deal, property_type=ptype,
        price=Decimal(price), address_line1=hood, city=city, neighborhood=hood, country='Nepal', status='active')


@pytest.fixture
def stock(org):
    return {
        'room': _l(org, 'Room near Chabahil Chowk', 'rent', 'room', 8000, 'Kathmandu', 'Chabahil'),
        'flat': _l(org, '2BHK Flat, Jhamsikhel', 'rent', 'apartment', 28000, 'Lalitpur', 'Jhamsikhel'),
        'land': _l(org, 'Land 5 Aana, Bhaisepati', 'sale', 'land', 21000000, 'Lalitpur', 'Bhaisepati'),
        'cheap_land': _l(org, 'Land 3 Kattha, Biratnagar', 'sale', 'land', 6000000, 'Biratnagar', 'Tinpaini'),
        'house': _l(org, 'House in Budhanilkantha', 'sale', 'house', 38500000, 'Kathmandu', 'Budhanilkantha'),
    }


def _refs(client, qs):
    html = client.get('/realestate/properties/?' + qs).content.decode()
    main = html.split('class="near"')[0]          # exact results only
    return set(re.findall(r'PROP\d{6}', main)), html


@pytest.mark.parametrize('raw,value', [
    ('15000', 15000), ('15,000', 15000), ('Rs 15000', 15000), ('NPR 15,000', 15000), ('50 lakh', 5_000_000),
    ('1.2 crore', 12_000_000), ('2 cr', 20_000_000), ('15k', 15000), ('15 hajar', 15000), ('५० लाख', 5_000_000),
    ('', None), ('cheap', None), ('0', None),
])
def test_parse_budget(raw, value):
    assert parse_budget(raw) == (Decimal(value) if value is not None else None)


def test_rent_buy_either(client, stock):
    rent, _ = _refs(client, 'deal=rent')
    sale, _ = _refs(client, 'deal=sale')
    either, _ = _refs(client, 'deal=')
    assert rent == {stock['room'].reference_number, stock['flat'].reference_number}
    assert stock['room'].reference_number not in sale and len(sale) == 3
    assert either == rent | sale


def test_budget_in_lakh_is_applied(client, stock):
    refs, _ = _refs(client, 'deal=sale&max=70+lakh')
    assert refs == {stock['cheap_land'].reference_number}


def test_unreadable_budget_says_so_instead_of_lying(client, stock):
    refs, html = _refs(client, 'deal=sale&max=cheap')
    assert len(refs) == 3 and 'could not read the budget' in html


def test_comma_separated_areas_match_any(client, stock):
    refs, _ = _refs(client, 'deal=&q=Chabahil%2C+Lalitpur')
    assert stock['room'].reference_number in refs and stock['flat'].reference_number in refs


def test_area_aliases(client, stock):
    refs, _ = _refs(client, 'deal=&q=ktm')
    assert refs == {stock['room'].reference_number, stock['house'].reference_number}
    refs, _ = _refs(client, 'deal=&q=patan')
    assert stock['flat'].reference_number in refs


def test_type_words_in_the_area_box(client, stock):
    refs, _ = _refs(client, 'q=jagga+lalitpur')
    assert refs == {stock['land'].reference_number}


def test_either_is_not_narrowed_by_a_rent_word(client, stock):
    refs, _ = _refs(client, 'deal=&q=bhada+lalitpur')
    assert stock['land'].reference_number in refs and stock['flat'].reference_number in refs


def test_rent_plus_land_shows_closest_matches_not_a_dead_end(client, stock):
    refs, html = _refs(client, 'deal=rent&type=land')
    assert not refs
    assert 'Closest matches for both rent and sale' in html
    assert stock['land'].reference_number in html.split('class="near"')[1]


def test_over_budget_shows_closest_without_the_limit(client, stock):
    _, html = _refs(client, 'deal=sale&type=house&max=1+crore')
    assert 'Closest matches without the budget limit' in html and stock['house'].reference_number in html


def test_nav_uses_short_labels_and_footer_has_agent_column(client, stock):
    html = client.get('/realestate/properties/').content.decode()
    nav = html.split('class="nav"')[1].split('</nav>')[0]
    assert '>Rooms<' in nav and 'Shops &amp; shutters for rent<' not in nav and 'AI agent' in nav
    assert '<h4>AI agent</h4>' in html and 'Our AI agent does the legwork' in html


def test_hero_deal_radios_do_not_cover_the_buttons(client, stock):
    # Regression: `.field input{width:100%}` stretched the hidden radios over the whole
    # Rent/Buy/Either row, so every click landed on "Either" and Buy could not be chosen.
    html = client.get('/realestate/properties/').content.decode()
    rule = html.split('.seg input{')[1].split('}')[0]
    assert 'pointer-events:none' in rule and 'width:1px' in rule
    assert '.seg{position:relative' in html
