"""
Entry pipeline (Phase 2) — the heart of the public scan→win flow.

create_entry() runs the ENTIRE money-like artifact creation in ONE transaction:
  1. eligibility (re-checked under the txn)
  2. draw a prize (weighted) and consume a slot with select_for_update on the
     prize rows so two simultaneous scans can't both take the last daily slot
  3. write the Entry (status=drawn), generate a unique coupon_code + referral_token,
     set expires_at, increment the denormalized prize counters (F())
  4. upsert the CRM customer (source=lucky_draw) and link it
  5. record consent IFF consent_given (never pre-assumed)
  6. apply the lucky_draw_lead system tag
  7. log a lucky_draw_entry CRM interaction
  8. apply referral attribution if a referral_token was presented

The WhatsApp delivery (loop 1) is intentionally NOT done here — the caller
queues it on transaction.on_commit so the public POST returns fast.

Idempotency and throttling are handled at the view layer (Phase 0 helpers).
"""
import hashlib
import logging

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from ..models import (
    LuckyDrawCampaign, LuckyDrawEntry, LuckyDrawPrize, EntryStatus,
)
from . import draw_engine, referral_service

logger = logging.getLogger(__name__)


class EntryError(Exception):
    """Raised when an entry cannot be created. `.reason` is a stable code."""
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def hash_ip(ip):
    if not ip:
        return ''
    return hashlib.sha256(ip.encode('utf-8')).hexdigest()


def hash_ua(ua):
    if not ua:
        return ''
    return hashlib.sha256(ua.encode('utf-8')).hexdigest()


def _unique_coupon_code():
    """Generate a coupon code, retrying on the (rare) uniqueness clash."""
    for _ in range(8):
        code = draw_engine.generate_coupon_code()
        if not LuckyDrawEntry.objects.filter(coupon_code=code).exists():
            return code
    # Fall back to a longer code if we somehow keep colliding.
    return draw_engine.generate_coupon_code(12)


def _unique_referral_token():
    for _ in range(8):
        token = draw_engine.generate_referral_token()
        if not LuckyDrawEntry.objects.filter(referral_token=token).exists():
            return token
    return draw_engine.generate_referral_token(20)


@transaction.atomic
def create_entry(campaign, *, name, phone='', email='', table_number='',
                 consent_given=False, referral_token=None,
                 ip_address=None, user_agent=None, marketing_channels=None):
    """
    Run the full entry pipeline. Returns the created LuckyDrawEntry (status=drawn,
    or status=invalid if the campaign has no usable prize). Raises EntryError on
    ineligibility (the view maps .reason to a 422 body).
    """
    from apps.crm.services import customer_service, consent_service, interaction_service
    from apps.crm.models import CustomerSource

    norm_phone = customer_service.normalize_phone(phone) if phone else ''

    # 1. Eligibility, re-checked inside the txn.
    eligible, reason = draw_engine.validate_entry_eligibility(campaign, norm_phone, hash_ip(ip_address))
    if not eligible:
        raise EntryError(reason)

    # 2. Draw under a row lock on the campaign's prizes so concurrent scans can't
    #    both consume the last daily/total slot.
    locked_prizes = list(
        LuckyDrawPrize.objects.select_for_update()
        .filter(campaign=campaign, active=True)
    )
    prize = draw_engine.draw_prize(
        _CampaignWithPrizes(campaign, locked_prizes)
    )

    # 3. Build the entry.
    entry = LuckyDrawEntry(
        campaign=campaign,
        customer_name=name or 'Customer',
        phone=norm_phone or '',
        email=(email or '').strip().lower(),
        table_number=table_number or '',
        consent_given=bool(consent_given),
        ip_address_hashed=hash_ip(ip_address),
        user_agent_hash=hash_ua(user_agent),
        referral_token=_unique_referral_token(),
    )

    if prize is None:
        # Degenerate config: no prize available. Record an invalid entry so the
        # lead is still captured, but no coupon is issued.
        entry.status = EntryStatus.INVALID
        entry.save()
    else:
        entry.prize = prize
        entry.status = EntryStatus.DRAWN
        entry.drawn_at = timezone.now()
        entry.expires_at = timezone.now() + timezone.timedelta(
            days=campaign.coupon_validity_days
        )
        entry.coupon_code = _unique_coupon_code()
        # Save with a coupon clash retry as a final backstop on the unique col.
        for attempt in range(5):
            try:
                entry.save()
                break
            except IntegrityError:
                entry.coupon_code = _unique_coupon_code()
                entry.referral_token = _unique_referral_token()
        else:
            raise EntryError('coupon_generation_failed')

        # Increment the denormalized counters atomically.
        LuckyDrawPrize.objects.filter(pk=prize.pk).update(
            wins_today_count=F('wins_today_count') + 1,
            wins_total_count=F('wins_total_count') + 1,
        )

    # 4. CRM customer upsert + link (only when we have an identity).
    customer = None
    if norm_phone or email:
        try:
            customer, _ = customer_service.get_or_create_customer(
                campaign.organization, phone=norm_phone or None, email=email or None,
                defaults={'name': name or 'Customer', 'source': CustomerSource.LUCKY_DRAW},
            )
            entry.crm_customer = customer
            entry.save(update_fields=['crm_customer'])
        except Exception:
            logger.exception("Lucky-draw CRM upsert failed for campaign %s", campaign.id)

    # 5. Consent (append-only, only if given — never pre-assumed).
    if customer is not None and consent_given:
        try:
            consent_service.record_consent(
                customer, given=True, source='lucky_draw_form',
                text_snapshot=campaign.consent_text or '',
                channels=marketing_channels or ['whatsapp'],
                ip_hash=hash_ip(ip_address),
                privacy_notice_version='v1',
            )
        except Exception:
            logger.exception("Lucky-draw consent record failed for campaign %s", campaign.id)

    # 6. Tag lucky_draw_lead.
    if customer is not None:
        _apply_lead_tag(customer)

    # 7. Log interaction.
    if customer is not None:
        try:
            label = (
                f"Won {prize.discount_percent}% ({entry.coupon_code})"
                if prize else "Entered (no prize available)"
            )
            interaction_service.log_interaction(
                customer, 'lucky_draw_entry', source_channel='lucky_draw',
                summary=f"{campaign.name}: {label}",
                entity_type='lucky_draw_entry', entity_id=entry.id,
            )
        except Exception:
            logger.exception("Lucky-draw interaction log failed for campaign %s", campaign.id)

    # 8. Referral attribution.
    if referral_token and campaign.referral_enabled:
        referral_service.apply_referral(entry, referral_token)

    return entry


def _apply_lead_tag(customer):
    try:
        from apps.crm.models import CRMTag, CRMCustomerTag
        tag = CRMTag.objects.filter(
            organization=customer.organization, name='lucky_draw_lead'
        ).first()
        if tag is not None:
            CRMCustomerTag.objects.get_or_create(customer=customer, tag=tag)
    except Exception:
        logger.warning("Lucky-draw lead tag failed", exc_info=True)


class _CampaignWithPrizes:
    """
    Thin adapter so draw_engine.draw_prize() can operate on a pre-locked prize
    list (avoids a second query while preserving the engine's simple interface).
    """
    def __init__(self, campaign, locked_prizes):
        self._campaign = campaign
        self._prizes = locked_prizes

    @property
    def prizes(self):
        return _PrizeManagerShim(self._prizes)

    def __getattr__(self, item):
        return getattr(self._campaign, item)


class _PrizeManagerShim:
    def __init__(self, prizes):
        self._prizes = prizes

    def filter(self, **kwargs):
        result = self._prizes
        if 'active' in kwargs:
            result = [p for p in result if p.active == kwargs['active']]
        return result
