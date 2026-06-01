"""customer_service tests: normalization, merge-by-identity, dedupe, merge."""
import pytest

from apps.crm.models import CRMCustomer, CRMInteraction, CustomerSource, InteractionType
from apps.crm.services import customer_service

pytestmark = pytest.mark.django_db


def test_normalize_hk_phone():
    # Local HK 8-digit number -> +852 E.164.
    assert customer_service.normalize_phone('91234567', 'HK') == '+85291234567'


def test_normalize_keeps_plus_for_unparseable():
    out = customer_service.normalize_phone('not-a-number')
    assert out is None or out == ''  # salvages nothing useful


def test_requires_phone_or_email(org):
    with pytest.raises(ValueError):
        customer_service.get_or_create_customer(org)


def test_create_then_dedupe_by_phone(org):
    c1, created1 = customer_service.get_or_create_customer(
        org, phone='91234567', defaults={'name': 'First', 'source': 'manual'})
    assert created1 is True
    c2, created2 = customer_service.get_or_create_customer(
        org, phone='+85291234567', defaults={'name': 'Again'})
    assert created2 is False
    assert c1.pk == c2.pk
    assert CRMCustomer.objects.filter(organization=org).count() == 1


def test_dedupe_by_email(org):
    c1, _ = customer_service.get_or_create_customer(
        org, email='Bob@X.com', defaults={'name': 'Bob', 'source': 'manual'})
    c2, created = customer_service.get_or_create_customer(org, email='bob@x.com')
    assert created is False
    assert c1.pk == c2.pk


def test_backfill_email_onto_phone_match(org):
    c1, _ = customer_service.get_or_create_customer(
        org, phone='91234567', defaults={'name': 'Phone Only', 'source': 'manual'})
    assert c1.email is None
    c2, created = customer_service.get_or_create_customer(
        org, phone='91234567', email='new@x.com')
    assert created is False
    c2.refresh_from_db()
    assert c2.email == 'new@x.com'


def test_merge_customers_repoints_interactions(org):
    primary, _ = customer_service.get_or_create_customer(
        org, phone='91110000', defaults={'name': 'Primary', 'source': 'manual'})
    dup, _ = customer_service.get_or_create_customer(
        org, email='dup@x.com', defaults={'name': 'Dup', 'source': 'manual'})
    CRMInteraction.objects.create(organization=org, customer=dup,
                                  interaction_type=InteractionType.MANUAL_NOTE)

    merged = customer_service.merge_customers(primary, dup)
    dup.refresh_from_db()
    assert merged.pk == primary.pk
    assert dup.is_active is False
    assert CRMInteraction.objects.filter(customer=primary).count() == 1
    assert CRMInteraction.objects.filter(customer=dup).count() == 0


def test_merge_cross_org_rejected(org, org_b):
    a = CRMCustomer.objects.create(organization=org, name='A', phone='+85200001111',
                                   source=CustomerSource.MANUAL)
    b = CRMCustomer.objects.create(organization=org_b, name='B', phone='+85200002222',
                                   source=CustomerSource.MANUAL)
    with pytest.raises(ValueError):
        customer_service.merge_customers(a, b)
