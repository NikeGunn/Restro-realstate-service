import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import Location, Organization
from apps.ai_engine.models import AgentMemory
from apps.realestate.models import PropertyListing
from apps.realestate.serializers import PropertyListingListSerializer

pytestmark = pytest.mark.django_db


@pytest.fixture
def org():
    o = Organization.objects.create(name='Kribaat Test', business_type='real_estate')
    Location.objects.create(organization=o, name='KTM', is_primary=True, is_active=True, country='Nepal')
    return o


def test_seed_is_idempotent_and_covers_land_in_many_districts(org):
    call_command('seed_nepal_portfolio', org='Kribaat Test')
    call_command('seed_nepal_portfolio', org='Kribaat Test')
    qs = PropertyListing.objects.filter(organization=org)
    assert qs.count() >= 25
    land = qs.filter(property_type='land', listing_type='sale')
    assert land.count() >= 6 and land.values('city').distinct().count() >= 5
    assert set(qs.values_list('country', flat=True)) == {'Nepal'}
    bhaisepati = land.get(title__contains='Bhaisepati')
    assert bhaisepati.lot_size == 1711 and 'Land area: 5 aana' in bhaisepati.features


def test_wipe_resets_demo_data_but_keeps_owner_playbook(org):
    PropertyListing.objects.create(organization=org, title='Old HK flat', description='x', listing_type='rent',
                                   property_type='apartment', price=32000, address_line1='a', city='Wan Chai',
                                   state='HK', postal_code='0')
    AgentMemory.objects.create(organization=org, subject_type='customer', subject_key='977', summary='HK$ stuff')
    AgentMemory.objects.create(organization=org, subject_type='owner', subject_key=AgentMemory.OWNER_KEY)
    call_command('seed_nepal_portfolio', org='Kribaat Test', wipe=True)
    assert not PropertyListing.objects.filter(organization=org, title='Old HK flat').exists()
    assert not AgentMemory.objects.filter(organization=org, subject_type='customer').exists()
    assert AgentMemory.objects.filter(organization=org, subject_type='owner').exists()


def test_refuses_org_without_nepal_location():
    o = Organization.objects.create(name='HK Co', business_type='real_estate')
    Location.objects.create(organization=o, name='HQ', is_primary=True, is_active=True, country='Hong Kong')
    with pytest.raises(CommandError):
        call_command('seed_nepal_portfolio', org='HK Co')


def test_list_serializer_exposes_country_for_currency_formatting(org):
    call_command('seed_nepal_portfolio', org='Kribaat Test')
    data = PropertyListingListSerializer(PropertyListing.objects.filter(organization=org).first()).data
    assert data['country'] == 'Nepal' and 'rent_period' in data and 'lot_size' in data
