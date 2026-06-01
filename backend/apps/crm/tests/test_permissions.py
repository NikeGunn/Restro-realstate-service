"""Permission tests: manager read-only, owner write/merge, outsider isolation."""
import pytest

from apps.crm.models import CRMCustomer, CustomerSource

pytestmark = pytest.mark.django_db


def test_outsider_denied(api_client, outsider, org, customer):
    # A user with no org membership cannot access CRM at all (IsOrgMember -> 403),
    # which also means they can never see another org's customers.
    api_client.force_authenticate(user=outsider)
    resp = api_client.get('/api/v1/crm/customers/')
    assert resp.status_code == 403


def test_manager_cannot_delete(manager_client, customer):
    resp = manager_client.delete(f'/api/v1/crm/customers/{customer.id}/')
    assert resp.status_code in (403, 405)
    assert CRMCustomer.objects.filter(pk=customer.id).exists()


def test_manager_cannot_merge(manager_client, org):
    p = CRMCustomer.objects.create(organization=org, name='P', phone='+85212340000',
                                   source=CustomerSource.MANUAL)
    d = CRMCustomer.objects.create(organization=org, name='D', email='d2@x.com',
                                   source=CustomerSource.MANUAL)
    resp = manager_client.post(f'/api/v1/crm/customers/{p.id}/merge/',
                               {'duplicate_id': str(d.id)}, format='json')
    assert resp.status_code == 403


def test_unauthenticated_denied(api_client):
    assert api_client.get('/api/v1/crm/customers/').status_code in (401, 403)
