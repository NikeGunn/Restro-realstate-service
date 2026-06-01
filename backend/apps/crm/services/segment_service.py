"""
Segment DSL compiler & evaluator (Phase 1).

Compiles a strict, whitelisted JSON rule list into a Django Q object. It NEVER
uses eval or raw SQL — unknown fields/ops raise ValidationError. Relative dates
('-90d') are resolved server-side at evaluation time.

DSL shape (flat, no nesting in Lite):
    {"logic": "AND", "rules": [
        {"field": "source", "op": "in", "value": ["lucky_draw", "wifi"]},
        {"field": "last_visit_date", "op": "gte", "value": "-90d"}
    ]}
"""
import re
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from ..models import CRMCustomer

# Whitelisted segment field -> ORM lookup base.
_FIELD_MAP = {
    'source': 'source',
    'marketing_consent_status': 'marketing_consent_status',
    'tags': 'customer_tags__tag__name',
    'last_visit_date': 'last_visit_date',
    'last_interaction_at': 'last_interaction_at',
    'preferred_language': 'preferred_language',
    'birthday_month': 'birthday_month',
    'visit_count': 'visit_count',
}

# op -> (ORM suffix or sentinel). 'exists'/'not_exists' handled specially.
_OP_SUFFIX = {
    'eq': '',
    'neq': '',           # negated eq
    'in': '__in',
    'not_in': '__in',    # negated in
    'gte': '__gte',
    'lte': '__lte',
    'exists': '__isnull',
    'not_exists': '__isnull',
}

_NEGATED_OPS = {'neq', 'not_in', 'not_exists'}
_RELATIVE_DATE_RE = re.compile(r'^-(\d+)d$')


def _resolve_value(field, op, value):
    """Resolve relative dates and validate value shape per op."""
    if op in ('in', 'not_in'):
        if not isinstance(value, (list, tuple)):
            raise ValidationError(f"Operator '{op}' requires a list value.")
        return list(value)
    if op in ('exists', 'not_exists'):
        # __isnull=True means "does not exist"; flip for 'exists'.
        return op == 'not_exists'
    # Relative date resolution for date/datetime fields.
    if isinstance(value, str):
        m = _RELATIVE_DATE_RE.match(value)
        if m:
            days = int(m.group(1))
            now = timezone.now()
            if field == 'last_visit_date':
                return (now - timedelta(days=days)).date()
            return now - timedelta(days=days)
    return value


def _rule_to_q(rule):
    if not isinstance(rule, dict):
        raise ValidationError("Each rule must be an object.")
    field = rule.get('field')
    op = rule.get('op')
    value = rule.get('value')

    if field not in _FIELD_MAP:
        raise ValidationError(f"Unknown segment field: {field!r}")
    if op not in _OP_SUFFIX:
        raise ValidationError(f"Unknown segment operator: {op!r}")

    orm_field = _FIELD_MAP[field]
    suffix = _OP_SUFFIX[op]
    resolved = _resolve_value(field, op, value)

    lookup = f'{orm_field}{suffix}'
    q = Q(**{lookup: resolved})
    if op in _NEGATED_OPS:
        q = ~q
    return q


def compile_rules(filter_rules):
    """
    Compile a validated rule dict into a Q. Empty/blank rules -> match-all Q().
    Raises ValidationError on any unknown field/op or malformed structure.
    """
    if not filter_rules:
        return Q()
    if not isinstance(filter_rules, dict):
        raise ValidationError("filter_rules must be an object.")

    logic = (filter_rules.get('logic') or 'AND').upper()
    if logic not in ('AND', 'OR'):
        raise ValidationError("logic must be 'AND' or 'OR'.")

    rules = filter_rules.get('rules') or []
    if not isinstance(rules, list):
        raise ValidationError("rules must be a list.")
    if not rules:
        return Q()

    combined = None
    for rule in rules:
        q = _rule_to_q(rule)
        if combined is None:
            combined = q
        elif logic == 'AND':
            combined &= q
        else:
            combined |= q
    return combined if combined is not None else Q()


def evaluate_segment(segment):
    """Return the (distinct, active) QuerySet of customers matching the segment."""
    q = compile_rules(segment.filter_rules)
    return (
        CRMCustomer.objects.filter(organization=segment.organization, is_active=True)
        .filter(q)
        .distinct()
    )


def preview_count(filter_rules, org):
    """Count matching customers for an unsaved rule set (validates the DSL)."""
    q = compile_rules(filter_rules)
    return (
        CRMCustomer.objects.filter(organization=org, is_active=True)
        .filter(q)
        .distinct()
        .count()
    )


def refresh_counts(org=None):
    """Recompute and cache customer_count on segments (daily task / on demand)."""
    from ..models import CRMSegment
    qs = CRMSegment.objects.all()
    if org is not None:
        qs = qs.filter(organization=org)
    for segment in qs.iterator():
        try:
            count = evaluate_segment(segment).count()
        except ValidationError:
            count = 0
        CRMSegment.objects.filter(pk=segment.pk).update(
            customer_count=count, last_evaluated_at=timezone.now()
        )
