"""
Customer identity & merge service (Phase 1).

The hot path: get_or_create_customer is called from public/booking/conversation
flows that can fire near-simultaneously, so it dedupes inside a transaction with
a row lock to avoid creating duplicates under concurrency.
"""
import logging
from django.conf import settings
from django.db import transaction

from ..models import CRMCustomer, CustomerSource

logger = logging.getLogger(__name__)

try:
    import phonenumbers
except ImportError:  # pragma: no cover - dependency is in requirements
    phonenumbers = None


def normalize_phone(raw, default_region='HK'):
    """
    Best-effort E.164 normalization (HK default region). Never raises:
    on unparseable input, returns the digits we could salvage (or None).
    """
    if not raw:
        return None
    raw = str(raw).strip()
    if phonenumbers is not None:
        try:
            parsed = phonenumbers.parse(raw, default_region)
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(
                    parsed, phonenumbers.PhoneNumberFormat.E164
                )
        except Exception:
            pass
    # Fallback: keep leading + and digits only.
    cleaned = ''.join(ch for ch in raw if ch.isdigit() or ch == '+')
    return cleaned or None


def _lookup(org, phone, email):
    """Find an existing customer by normalized phone first, then email."""
    if phone:
        c = CRMCustomer.objects.filter(organization=org, phone=phone).first()
        if c:
            return c
    if email:
        c = CRMCustomer.objects.filter(organization=org, email=email.strip().lower()).first()
        if c:
            return c
    return None


@transaction.atomic
def get_or_create_customer(org, phone=None, email=None, defaults=None):
    """
    Merge-by-identity upsert. Looks up by normalized phone then email within the
    org; locks the matched row (select_for_update) so two concurrent touchpoints
    can't both create. Returns (customer, created).

    Raises ValueError if neither phone nor email is provided.
    """
    if not phone and not email:
        raise ValueError("get_or_create_customer requires at least one of phone/email.")

    norm_phone = normalize_phone(phone) if phone else None
    norm_email = email.strip().lower() if email else None
    defaults = dict(defaults or {})

    # First, an unlocked lookup to see if a row exists.
    existing = _lookup(org, norm_phone, norm_email)
    if existing is not None:
        # Re-fetch under a row lock to serialize concurrent writers.
        locked = (
            CRMCustomer.objects.select_for_update()
            .filter(pk=existing.pk)
            .first()
        )
        if locked is not None:
            _backfill(locked, norm_phone, norm_email, phone, defaults)
            return locked, False

    # No match -> create. The partial unique constraints are the real backstop:
    # if a racing transaction created the same identity, we catch IntegrityError
    # and fall back to the now-existing row.
    try:
        with transaction.atomic():
            customer = CRMCustomer(
                organization=org,
                name=defaults.get('name') or 'Customer',
                phone=norm_phone,
                phone_raw=str(phone) if phone else '',
                email=norm_email,
                source=defaults.get('source') or CustomerSource.MANUAL,
            )
            for field in ('whatsapp_number', 'birthday', 'gender',
                          'preferred_language', 'notes', 'last_visit_date'):
                if field in defaults and defaults[field] is not None:
                    setattr(customer, field, defaults[field])
            customer.save()
            return customer, True
    except Exception:
        # Likely a unique-constraint race; return the existing row.
        existing = _lookup(org, norm_phone, norm_email)
        if existing is not None:
            return existing, False
        raise


def _backfill(customer, norm_phone, norm_email, phone_raw, defaults):
    """Fill in blanks on an existing customer without overwriting set values."""
    dirty = False
    if norm_phone and not customer.phone:
        customer.phone = norm_phone
        customer.phone_raw = str(phone_raw) if phone_raw else customer.phone_raw
        dirty = True
    if norm_email and not customer.email:
        customer.email = norm_email
        dirty = True
    for field in ('birthday', 'gender', 'preferred_language'):
        val = defaults.get(field)
        if val and not getattr(customer, field, None):
            setattr(customer, field, val)
            dirty = True
    if dirty:
        customer.save()


@transaction.atomic
def merge_customers(primary, duplicate):
    """
    Owner-only merge: re-point all of `duplicate`'s related rows to `primary`
    (the older id), then soft-delete the duplicate. Both must be the same org.
    """
    if primary.organization_id != duplicate.organization_id:
        raise ValueError("Cannot merge customers across organizations.")
    if primary.pk == duplicate.pk:
        return primary

    primary = CRMCustomer.objects.select_for_update().get(pk=primary.pk)
    duplicate = CRMCustomer.objects.select_for_update().get(pk=duplicate.pk)

    duplicate.interactions.update(customer=primary)
    duplicate.consent_records.update(customer=primary)
    # Re-point tags, skipping ones the primary already has (unique constraint).
    primary_tag_ids = set(primary.customer_tags.values_list('tag_id', flat=True))
    for ct in duplicate.customer_tags.all():
        if ct.tag_id in primary_tag_ids:
            ct.delete()
        else:
            ct.customer = primary
            ct.save(update_fields=['customer'])

    # Best-effort: re-point lucky-draw entries if that app is installed (Phase 2).
    _repoint_lucky_draw(primary, duplicate)

    # Capture the duplicate's identity, then release its unique phone/email FIRST
    # (the partial unique constraints count the soft-deleted row too), so the
    # backfill onto `primary` can't collide with the still-present duplicate.
    dup_phone, dup_email, dup_phone_raw = duplicate.phone, duplicate.email, duplicate.phone_raw
    dup_visits = duplicate.visit_count
    duplicate.is_active = False
    duplicate.phone = None
    duplicate.email = None
    duplicate.save(update_fields=['is_active', 'phone', 'email', 'updated_at'])

    # Now backfill primary blanks from the (released) duplicate identity.
    _backfill(primary, dup_phone, dup_email, dup_phone_raw, {})
    primary.visit_count = primary.visit_count + dup_visits
    primary.save()
    return primary


def _repoint_lucky_draw(primary, duplicate):
    try:
        from apps.lucky_draw.models import LuckyDrawEntry  # noqa: WPS433
    except Exception:
        return
    try:
        LuckyDrawEntry.objects.filter(crm_customer=duplicate).update(crm_customer=primary)
    except Exception:
        logger.warning("Lucky-draw re-point during merge failed", exc_info=True)


FREQUENT_THRESHOLD = getattr(settings, 'CRM_FREQUENT_THRESHOLD', 5)
