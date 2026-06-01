"""API tests: CRUD, segment preview, ready_to_engage consent filter, cross-org isolation."""
import pytest

from apps.crm.models import (
    CRMCustomer, CRMTag, CRMSegment, CustomerSource, ConsentSource,
)
from apps.crm.services import consent_service

pytestmark = pytest.mark.django_db


def test_customer_crud_owner(owner_client, org):
    resp = owner_client.post('/api/v1/crm/customers/', {
        'organization': str(org.id), 'name': 'New Cust', 'phone': '91234567',
        'source': CustomerSource.MANUAL,
    }, format='json')
    assert resp.status_code == 201, resp.content
    cust_id = resp.data['id']
    # phone normalized to E.164 on save.
    assert resp.data['phone'] == '+85291234567'

    resp = owner_client.get('/api/v1/crm/customers/')
    assert resp.status_code == 200
    assert resp.data['count'] == 1

    resp = owner_client.patch(f'/api/v1/crm/customers/{cust_id}/',
                              {'notes': 'VIP guest'}, format='json')
    assert resp.status_code == 200
    assert resp.data['notes'] == 'VIP guest'


def test_manager_can_read_cannot_create(manager_client, org):
    assert manager_client.get('/api/v1/crm/customers/').status_code == 200
    resp = manager_client.post('/api/v1/crm/customers/', {
        'organization': str(org.id), 'name': 'X', 'phone': '90000000',
        'source': CustomerSource.MANUAL}, format='json')
    assert resp.status_code in (403, 400)


def test_cross_org_isolation(owner_client, org_b):
    other = CRMCustomer.objects.create(organization=org_b, name='Hidden',
                                       phone='+85299998888', source=CustomerSource.MANUAL)
    # Not in owner's org -> 404, no existence leak.
    assert owner_client.get(f'/api/v1/crm/customers/{other.id}/').status_code == 404
    # List excludes it.
    assert owner_client.get('/api/v1/crm/customers/').data['count'] == 0


def test_segment_preview(owner_client, org):
    CRMCustomer.objects.create(organization=org, name='L', phone='+85288887777',
                               source=CustomerSource.LUCKY_DRAW)
    resp = owner_client.post(
        f'/api/v1/crm/segments/preview/?organization={org.id}',
        {'filter_rules': {'logic': 'AND', 'rules': [
            {'field': 'source', 'op': 'eq', 'value': 'lucky_draw'}]}},
        format='json')
    assert resp.status_code == 200
    assert resp.data['count'] == 1


def test_ready_to_engage_excludes_non_consenting(owner_client, org):
    consenting = CRMCustomer.objects.create(organization=org, name='Yes',
                                            phone='+85211110000', source=CustomerSource.MANUAL)
    CRMCustomer.objects.create(organization=org, name='No', phone='+85222220000',
                               source=CustomerSource.MANUAL)
    consent_service.record_consent(consenting, given=True, source=ConsentSource.MANUAL,
                                   channels=['whatsapp'])
    seg = CRMSegment.objects.create(
        organization=org, name='All',
        filter_rules={'logic': 'AND', 'rules': [
            {'field': 'source', 'op': 'eq', 'value': 'manual'}]})

    all_resp = owner_client.get(f'/api/v1/crm/segments/{seg.id}/customers/')
    assert all_resp.data['count'] == 2
    rte = owner_client.get(f'/api/v1/crm/segments/{seg.id}/ready-to-engage/')
    assert rte.data['count'] == 1
    assert rte.data['results'][0]['name'] == 'Yes'


def test_system_tag_cannot_be_deleted(owner_client, org):
    # System tags were seeded for this org via the post_save signal.
    tag = CRMTag.objects.get(organization=org, name='vip')
    resp = owner_client.delete(f'/api/v1/crm/tags/{tag.id}/')
    assert resp.status_code == 403
    assert CRMTag.objects.filter(pk=tag.id).exists()


def test_consent_record_endpoint(owner_client, customer):
    resp = owner_client.post('/api/v1/crm/consents/record/', {
        'customer': str(customer.id), 'consent_given': True,
        'consent_source': ConsentSource.LUCKY_DRAW_FORM,
        'marketing_channels_allowed': ['whatsapp'],
    }, format='json')
    assert resp.status_code == 201
    customer.refresh_from_db()
    assert customer.marketing_consent_status == 'given'


def test_consent_not_given_creates_no_consent(owner_client, customer):
    # consent_given=False -> a 'refused' record, status not 'given'.
    resp = owner_client.post('/api/v1/crm/consents/record/', {
        'customer': str(customer.id), 'consent_given': False,
        'consent_source': ConsentSource.BOOKING_FORM,
    }, format='json')
    assert resp.status_code == 201
    customer.refresh_from_db()
    assert customer.marketing_consent_status != 'given'


def test_customer_tag_action(owner_client, org, customer):
    tag = CRMTag.objects.get(organization=org, name='vip')
    resp = owner_client.post(f'/api/v1/crm/customers/{customer.id}/tags/',
                             {'tag_id': str(tag.id), 'action': 'add'}, format='json')
    assert resp.status_code == 200
    assert any(t['name'] == 'vip' for t in resp.data)


def test_merge_endpoint_owner_only(owner_client, org):
    primary = CRMCustomer.objects.create(organization=org, name='P', phone='+85233330000',
                                         source=CustomerSource.MANUAL)
    dup = CRMCustomer.objects.create(organization=org, name='D', email='d@x.com',
                                     source=CustomerSource.MANUAL)
    resp = owner_client.post(f'/api/v1/crm/customers/{primary.id}/merge/',
                             {'duplicate_id': str(dup.id)}, format='json')
    assert resp.status_code == 200
    dup.refresh_from_db()
    assert dup.is_active is False
