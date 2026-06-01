"""Model-level tests: constraints, append-only, denormalization."""
import datetime
import pytest
from django.db import IntegrityError, transaction

from apps.crm.models import (
    CRMCustomer, CRMInteraction, CRMConsent, CustomerSource,
    InteractionType, ConsentSource,
)

pytestmark = pytest.mark.django_db


def test_org_phone_unique_constraint(org):
    CRMCustomer.objects.create(organization=org, name='A', phone='+85211112222',
                               source=CustomerSource.MANUAL)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CRMCustomer.objects.create(organization=org, name='B', phone='+85211112222',
                                       source=CustomerSource.MANUAL)


def test_org_email_unique_constraint(org):
    CRMCustomer.objects.create(organization=org, name='A', email='dup@x.com',
                               source=CustomerSource.MANUAL)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CRMCustomer.objects.create(organization=org, name='B', email='dup@x.com',
                                       source=CustomerSource.MANUAL)


def test_null_phone_allows_multiple(org):
    # The partial constraint only applies to non-null/non-empty phones.
    CRMCustomer.objects.create(organization=org, name='A', email='a@x.com',
                               source=CustomerSource.MANUAL)
    CRMCustomer.objects.create(organization=org, name='B', email='b@x.com',
                               source=CustomerSource.MANUAL)
    assert CRMCustomer.objects.filter(organization=org).count() == 2


def test_birthday_month_derived_on_save(org):
    c = CRMCustomer.objects.create(organization=org, name='C', phone='+85233334444',
                                   birthday=datetime.date(1990, 7, 15),
                                   source=CustomerSource.MANUAL)
    assert c.birthday_month == 7


def test_email_lowercased_and_whatsapp_defaulted(org):
    c = CRMCustomer.objects.create(organization=org, name='D', phone='+85255556666',
                                   email='MixED@Case.COM', source=CustomerSource.MANUAL)
    assert c.email == 'mixed@case.com'
    assert c.whatsapp_number == '+85255556666'


def test_interaction_is_append_only(org, customer):
    i = CRMInteraction.objects.create(organization=org, customer=customer,
                                      interaction_type=InteractionType.MANUAL_NOTE)
    i.summary = 'changed'
    with pytest.raises(ValueError):
        i.save()


def test_consent_is_append_only(org, customer):
    rec = CRMConsent.objects.create(organization=org, customer=customer,
                                    consent_given=True, consent_source=ConsentSource.MANUAL,
                                    consent_text_snapshot='ok', consent_text_version='v1')
    rec.consent_given = False
    with pytest.raises(ValueError):
        rec.save()


def test_same_phone_different_orgs_allowed(org, org_b):
    CRMCustomer.objects.create(organization=org, name='A', phone='+85277778888',
                               source=CustomerSource.MANUAL)
    CRMCustomer.objects.create(organization=org_b, name='A2', phone='+85277778888',
                               source=CustomerSource.MANUAL)
    assert CRMCustomer.objects.filter(phone='+85277778888').count() == 2
