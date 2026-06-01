"""Segment DSL tests: correctness per op, rejection of unknown fields/ops, no eval."""
import datetime
import pytest
from rest_framework.exceptions import ValidationError

from apps.crm.models import CRMCustomer, CRMTag, CRMCustomerTag, CRMSegment, CustomerSource
from apps.crm.services import segment_service

pytestmark = pytest.mark.django_db


def _seg(org, rules):
    return CRMSegment.objects.create(organization=org, name='S', filter_rules=rules)


def test_eq_op(org):
    CRMCustomer.objects.create(organization=org, name='lucky', phone='+85200000001',
                               source=CustomerSource.LUCKY_DRAW)
    CRMCustomer.objects.create(organization=org, name='manual', phone='+85200000002',
                               source=CustomerSource.MANUAL)
    seg = _seg(org, {'logic': 'AND', 'rules': [
        {'field': 'source', 'op': 'eq', 'value': 'lucky_draw'}]})
    assert segment_service.evaluate_segment(seg).count() == 1


def test_in_and_neq_ops(org):
    for i, src in enumerate([CustomerSource.LUCKY_DRAW, CustomerSource.WIFI, CustomerSource.MANUAL]):
        CRMCustomer.objects.create(organization=org, name=f'c{i}',
                                   phone=f'+8520000010{i}', source=src)
    seg_in = _seg(org, {'logic': 'AND', 'rules': [
        {'field': 'source', 'op': 'in', 'value': ['lucky_draw', 'wifi']}]})
    assert segment_service.evaluate_segment(seg_in).count() == 2
    seg_neq = _seg(org, {'logic': 'AND', 'rules': [
        {'field': 'source', 'op': 'neq', 'value': 'manual'}]})
    assert segment_service.evaluate_segment(seg_neq).count() == 2


def test_relative_date_gte(org):
    recent = CRMCustomer.objects.create(organization=org, name='recent', phone='+85200000201',
                                        source=CustomerSource.MANUAL)
    recent.last_visit_date = datetime.date.today()
    recent.save()
    old = CRMCustomer.objects.create(organization=org, name='old', phone='+85200000202',
                                     source=CustomerSource.MANUAL)
    old.last_visit_date = datetime.date.today() - datetime.timedelta(days=200)
    old.save()
    seg = _seg(org, {'logic': 'AND', 'rules': [
        {'field': 'last_visit_date', 'op': 'gte', 'value': '-90d'}]})
    names = list(segment_service.evaluate_segment(seg).values_list('name', flat=True))
    assert names == ['recent']


def test_tags_field(org):
    c = CRMCustomer.objects.create(organization=org, name='vip', phone='+85200000301',
                                   source=CustomerSource.MANUAL)
    # `vip` is a seeded system tag for every org — reuse it rather than recreate.
    tag = CRMTag.objects.get(organization=org, name='vip')
    CRMCustomerTag.objects.create(customer=c, tag=tag)
    seg = _seg(org, {'logic': 'AND', 'rules': [
        {'field': 'tags', 'op': 'eq', 'value': 'vip'}]})
    assert segment_service.evaluate_segment(seg).count() == 1


def test_or_logic(org):
    CRMCustomer.objects.create(organization=org, name='a', phone='+85200000401',
                               source=CustomerSource.LUCKY_DRAW)
    CRMCustomer.objects.create(organization=org, name='b', phone='+85200000402',
                               source=CustomerSource.WALK_IN)
    seg = _seg(org, {'logic': 'OR', 'rules': [
        {'field': 'source', 'op': 'eq', 'value': 'lucky_draw'},
        {'field': 'source', 'op': 'eq', 'value': 'walk_in'}]})
    assert segment_service.evaluate_segment(seg).count() == 2


def test_unknown_field_rejected(org):
    with pytest.raises(ValidationError):
        segment_service.compile_rules({'logic': 'AND', 'rules': [
            {'field': 'password', 'op': 'eq', 'value': 'x'}]})


def test_unknown_op_rejected(org):
    with pytest.raises(ValidationError):
        segment_service.compile_rules({'logic': 'AND', 'rules': [
            {'field': 'source', 'op': 'regex', 'value': '.*'}]})


def test_no_eval_injection_rejected(org):
    # A malicious 'field' that would only "work" with eval/raw SQL must raise,
    # never execute. There is no code path that evaluates arbitrary strings.
    with pytest.raises(ValidationError):
        segment_service.compile_rules({'logic': 'AND', 'rules': [
            {'field': "name__regex='.*'; DROP TABLE", 'op': 'eq', 'value': 'x'}]})


def test_empty_rules_match_all(org):
    CRMCustomer.objects.create(organization=org, name='x', phone='+85200000501',
                               source=CustomerSource.MANUAL)
    seg = _seg(org, {})
    assert segment_service.evaluate_segment(seg).count() == 1


def test_in_op_requires_list(org):
    with pytest.raises(ValidationError):
        segment_service.compile_rules({'logic': 'AND', 'rules': [
            {'field': 'source', 'op': 'in', 'value': 'lucky_draw'}]})
