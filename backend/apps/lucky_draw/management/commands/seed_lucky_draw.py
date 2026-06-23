"""
Seed rich, realistic Lucky Draw demo data into one organization.

Goal: let an owner see the WHOLE lucky-draw lifecycle end-to-end — every
campaign status, every prize-limit edge, the WhatsApp coupon delivery flag, the
referral viral loop, consent given/refused, CRM linkage, and entries in every
status (drawn / redeemed / expired / invalid) — so they can then reproduce and
EDIT the same things from the dashboard UI.

Everything is created through the REAL services (entry_service.create_entry,
referral_service.apply_referral, the redeem transition, qr_service) so the
denormalized prize counters, CRM customers, consent rows, tags and interactions
are all internally consistent — never raw inserts that drift from invariants.

Idempotent-ish: pass --wipe to delete this org's existing lucky-draw campaigns
(and their cascade) before seeding, so re-running gives a clean known state.

Usage:
    python manage.py seed_lucky_draw
    python manage.py seed_lucky_draw --owner-email bagaichahk@gmail.com --wipe
"""
import random
from datetime import timedelta

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Organization, OrganizationMembership
from apps.lucky_draw.models import (
    LuckyDrawCampaign, LuckyDrawPrize, LuckyDrawQRCode,
    CampaignStatus, EntryStatus, ReferralBonusType,
)
from apps.lucky_draw.services import entry_service, qr_service, draw_engine
from apps.messaging.models import LanguageChoice

DEFAULT_OWNER_EMAIL = 'bagaichahk@gmail.com'

# A pool of believable HK customers (name + local mobile). Phones normalize to
# E.164 +852… via the CRM service. Mix of Chinese + English names.
CUSTOMERS = [
    ('Chan Tai Man', '91234501'), ('Wong Mei Ling', '91234502'),
    ('Lee Ka Ho', '91234503'), ('Cheung Siu Fong', '91234504'),
    ('Lam Chi Wai', '91234505'), ('Ng Wing Yan', '91234506'),
    ('Tsang Ho Yin', '91234507'), ('Lau Ka Yi', '91234508'),
    ('Ho Chun Kit', '91234509'), ('Yip Sze Wan', '91234510'),
    ('Marcus Tan', '91234511'), ('Priya Sharma', '91234512'),
    ('Kenji Sato', '91234513'), ('Sophie Leung', '91234514'),
    ('David Kwok', '91234515'), ('Aisha Khan', '91234516'),
    ('Ryan Choi', '91234517'), ('Emily Fung', '91234518'),
    ('Jason Pang', '91234519'), ('Natalie So', '91234520'),
]


class Command(BaseCommand):
    help = "Seed rich Lucky Draw demo data (all statuses, prizes, referrals, CRM) into one org."

    def add_arguments(self, parser):
        parser.add_argument('--owner-email', default=DEFAULT_OWNER_EMAIL,
                            help='Email of the org owner to seed into (default: %(default)s).')
        parser.add_argument('--org-id', default=None,
                            help='Explicit organization UUID (overrides --owner-email lookup).')
        parser.add_argument('--wipe', action='store_true',
                            help="Delete this org's existing lucky-draw campaigns before seeding.")
        parser.add_argument('--no-qr', action='store_true',
                            help='Skip QR/poster image generation (faster, no Pillow/qrcode needed).')

    # ── entry point ────────────────────────────────────────────────────
    def handle(self, *args, **opts):
        self.rng = random.Random(20260623)  # deterministic-ish demo
        self.make_qr = not opts['no_qr']
        org = self._resolve_org(opts)
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Seeding Lucky Draw demo into org: {org.name} ({org.id})"))

        if opts['wipe']:
            n, _ = LuckyDrawCampaign.objects.filter(organization=org).delete()
            self.stdout.write(self.style.WARNING(f"  Wiped {n} existing lucky-draw rows."))

        with transaction.atomic():
            self._seed_mega(org)
            self._seed_happy_hour(org)
            self._seed_buffet(org)
            self._seed_draft(org)
            self._seed_paused(org)
            self._seed_ended(org)

        self._summary(org)

    # ── org resolution ─────────────────────────────────────────────────
    def _resolve_org(self, opts):
        if opts['org_id']:
            try:
                return Organization.objects.get(id=opts['org_id'])
            except Organization.DoesNotExist:
                raise CommandError(f"No organization with id={opts['org_id']}")

        email = opts['owner_email'].strip().lower()
        membership = (
            OrganizationMembership.objects
            .filter(user__email__iexact=email, role=OrganizationMembership.Role.OWNER)
            .select_related('organization').first()
        )
        if membership is None:
            # Fall back to any membership for that user.
            membership = (
                OrganizationMembership.objects
                .filter(user__email__iexact=email)
                .select_related('organization').first()
            )
        if membership is None:
            raise CommandError(
                f"No organization found for owner '{email}'. "
                f"Pass --org-id or a different --owner-email.")
        return membership.organization

    # ── shared helpers ─────────────────────────────────────────────────
    def _prize(self, campaign, label, pct, weight, **kw):
        return LuckyDrawPrize.objects.create(
            campaign=campaign, label=label, discount_percent=pct, weight=weight, **kw)

    def _qr(self, campaign, label):
        qr = LuckyDrawQRCode.objects.create(
            campaign=campaign, label=label,
            url_token=draw_engine.generate_referral_token(20),
        )
        if not self.make_qr:
            return qr
        try:
            url = qr_service.get_campaign_entry_url(qr)
            png = qr_service.generate_qr_image(url)
            qr.qr_image.save(f"qr_{qr.url_token}.png", ContentFile(png), save=False)
            poster = qr_service.generate_poster(campaign, qr)
            qr.poster_image.save(f"poster_{qr.url_token}.png", ContentFile(poster), save=False)
            qr.save(update_fields=['qr_image', 'poster_image'])
        except Exception as e:  # noqa: BLE001 — image libs optional in some envs
            self.stdout.write(self.style.WARNING(f"    QR/poster gen skipped: {e}"))
        return qr

    def _enter(self, campaign, name, phone, *, consent, email='', table='',
               referral_token=None, ip=None):
        """Create a real entry. ip varied so per-IP soft-limit logic is exercised."""
        ip = ip or f"203.0.113.{self.rng.randint(2, 250)}"
        try:
            return entry_service.create_entry(
                campaign, name=name, phone=phone, email=email, table_number=table,
                consent_given=consent, referral_token=referral_token,
                ip_address=ip, user_agent='Mozilla/5.0 (SeedBot demo)',
                marketing_channels=['whatsapp'] if consent else None,
            )
        except entry_service.EntryError as e:
            self.stdout.write(self.style.WARNING(f"    entry blocked ({e.reason}) for {name}"))
            return None

    def _redeem(self, entry, redeemer):
        """Replicate the redeem viewset transition + CRM side-effects."""
        if entry is None or entry.status != EntryStatus.DRAWN:
            return
        entry.status = EntryStatus.REDEEMED
        entry.redeemed_at = timezone.now()
        entry.redeemed_by = redeemer
        entry.save(update_fields=['status', 'redeemed_at', 'redeemed_by'])
        cust = entry.crm_customer
        if cust is None:
            return
        from apps.crm.services import interaction_service
        from apps.crm.models import CRMTag, CRMCustomerTag
        try:
            interaction_service.log_interaction(
                cust, 'coupon_redeemed', source_channel='lucky_draw',
                summary=f"Redeemed {entry.coupon_code} "
                        f"({entry.prize.discount_percent if entry.prize else 0}% off)",
                entity_type='lucky_draw_entry', entity_id=entry.id, user=redeemer,
            )
        except Exception:
            pass
        if entry.campaign.tag_redeemers_as_buffet:
            tag = CRMTag.objects.filter(
                organization=cust.organization, name='buffet_customer').first()
            if tag:
                CRMCustomerTag.objects.get_or_create(customer=cust, tag=tag)

    def _expire(self, entry):
        """Force an entry into EXPIRED + backdate, so the dashboard shows lapsed coupons."""
        if entry is None or entry.status != EntryStatus.DRAWN:
            return
        entry.status = EntryStatus.EXPIRED
        entry.expires_at = timezone.now() - timedelta(days=1)
        entry.save(update_fields=['status', 'expires_at'])

    def _mark_whatsapp_sent(self, entry):
        """Simulate the loop-1 WhatsApp coupon delivery having succeeded."""
        if entry is None or entry.coupon_code is None:
            return
        entry.whatsapp_sent_at = timezone.now()
        entry.save(update_fields=['whatsapp_sent_at'])

    def _owner(self, org):
        m = OrganizationMembership.objects.filter(
            organization=org, role=OrganizationMembership.Role.OWNER).select_related('user').first()
        return m.user if m else None

    # ── SCENARIO 1: Mega draw (full viral loop, all statuses) ───────────
    def _seed_mega(self, org):
        c = LuckyDrawCampaign.objects.create(
            organization=org,
            name='Lunar New Year Mega Draw 🧧',
            description='Scan, spin, and win up to 88% off! Share with friends for extra entries.',
            status=CampaignStatus.ACTIVE,
            start_date=timezone.localdate() - timedelta(days=3),
            end_date=timezone.localdate() + timedelta(days=27),
            daily_entry_limit_per_customer=1,
            total_entry_limit_per_customer=5,
            requires_name=True, requires_phone=True, requires_email=False,
            consent_text='I agree to receive marketing offers from this restaurant via WhatsApp.',
            privacy_notice_text='We store your phone to deliver your prize and offers. Opt out anytime.',
            default_language=LanguageChoice.TRADITIONAL_CHINESE,
            deliver_coupon_via_whatsapp=True,
            referral_enabled=True, referral_bonus_type=ReferralBonusType.EXTRA_ENTRY,
            coupon_validity_days=14,
        )
        self._prize(c, '88% OFF Jackpot 🎉', 88, weight=1, max_total_wins=2)
        self._prize(c, '50% OFF', 50, weight=3, max_wins_per_day=5)
        self._prize(c, '20% OFF', 20, weight=10)
        self._prize(c, '10% OFF', 10, weight=25)
        self._prize(c, '5% OFF', 5, weight=40)
        self._qr(c, 'Table tent — entrance')
        self._qr(c, 'Receipt footer QR')

        owner = self._owner(org)
        pool = list(CUSTOMERS)
        self.rng.shuffle(pool)

        # 8 fresh winners, mostly consenting → WhatsApp delivery marked.
        winners = []
        for i, (name, ph) in enumerate(pool[:8]):
            consent = i % 4 != 0  # ~75% consent; 1-in-4 refuses
            e = self._enter(c, name, ph, consent=consent)
            if e:
                self._mark_whatsapp_sent(e)
                winners.append((e, name, ph))

        # Referral chain: first winner refers 3 new people (extra-entry loop).
        if winners:
            referrer_entry = winners[0][0]
            token = referrer_entry.referral_token
            for name, ph in pool[8:11]:
                e = self._enter(c, name, ph, consent=True, referral_token=token)
                self._mark_whatsapp_sent(e)
            # Second-level referral: one of those refers again.
            second = referrer_entry.referrals.first()
            if second and second.referral_token:
                e = self._enter(c, pool[11][0], pool[11][1], consent=True,
                                referral_token=second.referral_token)
                self._mark_whatsapp_sent(e)

        # Redeem 3 winners in-store; expire 1; leave the rest live.
        for e, _, _ in winners[:3]:
            self._redeem(e, owner)
        if len(winners) > 3:
            self._expire(winners[3][0])

        self.stdout.write(self.style.SUCCESS("  ✔ Lunar New Year Mega Draw (active, full loop)"))

    # ── SCENARIO 2: Happy hour — prize caps / headroom exhaustion ───────
    def _seed_happy_hour(self, org):
        c = LuckyDrawCampaign.objects.create(
            organization=org,
            name='Happy Hour Spin 🍻',
            description='5–7pm only. Limited daily prizes — first come first served!',
            status=CampaignStatus.ACTIVE,
            start_date=timezone.localdate() - timedelta(days=1),
            end_date=timezone.localdate() + timedelta(days=14),
            daily_entry_limit_per_customer=2,
            total_entry_limit_per_customer=None,  # unlimited total
            requires_name=True, requires_phone=True,
            consent_text='I agree to receive WhatsApp offers.',
            default_language=LanguageChoice.ENGLISH,
            deliver_coupon_via_whatsapp=True,
            referral_enabled=False,
            coupon_validity_days=3,
        )
        # One prize ALREADY MAXED OUT so the owner sees a sold-out tier.
        free_drink = self._prize(c, 'Free Drink (SOLD OUT today) 🥤', 100,
                                  weight=2, max_wins_per_day=2)
        self._prize(c, '30% OFF', 30, weight=8)
        self._prize(c, '15% OFF', 15, weight=20)

        owner = self._owner(org)
        pool = list(CUSTOMERS)
        self.rng.shuffle(pool)
        for name, ph in pool[:6]:
            e = self._enter(c, name, ph, consent=True)
            self._mark_whatsapp_sent(e)
            if e and e.prize_id == free_drink.id and e.status == EntryStatus.DRAWN:
                self._redeem(e, owner)

        # Drive the free-drink tier to its daily cap so headroom logic is visible.
        free_drink.refresh_from_db()
        if free_drink.wins_today_count < free_drink.max_wins_per_day:
            LuckyDrawPrize.objects.filter(pk=free_drink.pk).update(
                wins_today_count=free_drink.max_wins_per_day,
                wins_total_count=free_drink.max_wins_per_day,
            )
        self.stdout.write(self.style.SUCCESS("  ✔ Happy Hour Spin (active, capped prizes)"))

    # ── SCENARIO 3: Buffet — tag redeemers as buffet_customer ───────────
    def _seed_buffet(self, org):
        c = LuckyDrawCampaign.objects.create(
            organization=org,
            name='Weekend Buffet Lucky Spin 🍤',
            description='Win buffet discounts. Redeemers get tagged for our buffet club.',
            status=CampaignStatus.ACTIVE,
            start_date=timezone.localdate() - timedelta(days=2),
            end_date=timezone.localdate() + timedelta(days=20),
            daily_entry_limit_per_customer=1,
            requires_name=True, requires_phone=True, requires_email=True,
            consent_text='I agree to receive buffet promotions via WhatsApp.',
            default_language=LanguageChoice.SIMPLIFIED_CHINESE,
            deliver_coupon_via_whatsapp=True,
            referral_enabled=True, referral_bonus_type=ReferralBonusType.EXTRA_ENTRY,
            coupon_validity_days=30,
            tag_redeemers_as_buffet=True,
        )
        self._prize(c, 'Buffet 40% OFF', 40, weight=4)
        self._prize(c, 'Buffet 25% OFF', 25, weight=12)
        self._prize(c, 'Free Dessert (10% token)', 10, weight=20)
        self._qr(c, 'Buffet station QR')

        owner = self._owner(org)
        pool = list(CUSTOMERS)
        self.rng.shuffle(pool)
        for i, (name, ph) in enumerate(pool[:5]):
            email = f"{name.split()[0].lower()}{i}@example.com"
            e = self._enter(c, name, ph, consent=True, email=email)
            self._mark_whatsapp_sent(e)
            # Redeem ~half → they get buffet_customer tag.
            if i % 2 == 0:
                self._redeem(e, owner)
        self.stdout.write(self.style.SUCCESS("  ✔ Weekend Buffet Lucky Spin (active, buffet tagging)"))

    # ── SCENARIO 4: Draft (pre-launch, no entries) ──────────────────────
    def _seed_draft(self, org):
        c = LuckyDrawCampaign.objects.create(
            organization=org,
            name='Summer Splash Promo (DRAFT) ☀️',
            description='Not launched yet — edit me from the dashboard, add prizes, then activate.',
            status=CampaignStatus.DRAFT,
            start_date=timezone.localdate() + timedelta(days=7),
            end_date=timezone.localdate() + timedelta(days=37),
            daily_entry_limit_per_customer=1,
            requires_name=True, requires_phone=True,
            consent_text='I agree to receive marketing offers via WhatsApp.',
            default_language=LanguageChoice.TRADITIONAL_CHINESE,
            deliver_coupon_via_whatsapp=True, referral_enabled=True,
            coupon_validity_days=14,
        )
        self._prize(c, '25% OFF', 25, weight=10)
        self._prize(c, '10% OFF', 10, weight=30)
        # No QR, no entries — a clean editable starting point.
        self.stdout.write(self.style.SUCCESS("  ✔ Summer Splash Promo (draft, no entries)"))

    # ── SCENARIO 5: Paused (email-required, better_odds) ────────────────
    def _seed_paused(self, org):
        c = LuckyDrawCampaign.objects.create(
            organization=org,
            name='Members Club Draw (PAUSED) 🎴',
            description='Temporarily paused. New scans are blocked until you resume it.',
            status=CampaignStatus.PAUSED,
            start_date=timezone.localdate() - timedelta(days=10),
            end_date=timezone.localdate() + timedelta(days=40),
            daily_entry_limit_per_customer=1,
            total_entry_limit_per_customer=3,
            requires_name=True, requires_phone=True, requires_email=True,
            consent_text='I agree to receive members-only offers via WhatsApp.',
            default_language=LanguageChoice.ENGLISH,
            deliver_coupon_via_whatsapp=True,
            referral_enabled=True, referral_bonus_type=ReferralBonusType.BETTER_ODDS,
            coupon_validity_days=21,
        )
        self._prize(c, 'VIP 35% OFF', 35, weight=5)
        self._prize(c, '15% OFF', 15, weight=15)
        self._qr(c, 'Member card QR')

        # Seed a few entries while it was active, THEN it was paused — so the
        # campaign has history. Flip to ACTIVE, enter, flip back to PAUSED.
        owner = self._owner(org)
        c.status = CampaignStatus.ACTIVE
        c.save(update_fields=['status'])
        pool = list(CUSTOMERS); self.rng.shuffle(pool)
        for i, (name, ph) in enumerate(pool[:3]):
            e = self._enter(c, name, ph, consent=True, email=f"member{i}@example.com")
            self._mark_whatsapp_sent(e)
            if i == 0:
                self._redeem(e, owner)
        c.status = CampaignStatus.PAUSED
        c.save(update_fields=['status'])
        self.stdout.write(self.style.SUCCESS("  ✔ Members Club Draw (paused, with prior history)"))

    # ── SCENARIO 6: Ended (historical, expired coupons) ─────────────────
    def _seed_ended(self, org):
        c = LuckyDrawCampaign.objects.create(
            organization=org,
            name='Christmas Cracker Draw 2025 🎄',
            description='Finished campaign — read-only history of a completed draw.',
            # Seed with an OPEN window (active + future end) so eligibility lets
            # entries through; we close + backdate it at the very end.
            status=CampaignStatus.ACTIVE,
            start_date=timezone.localdate() - timedelta(days=60),
            end_date=timezone.localdate() + timedelta(days=1),
            daily_entry_limit_per_customer=1,
            requires_name=True, requires_phone=True,
            consent_text='I agree to receive festive offers via WhatsApp.',
            default_language=LanguageChoice.TRADITIONAL_CHINESE,
            deliver_coupon_via_whatsapp=True, referral_enabled=True,
            coupon_validity_days=10,
        )
        self._prize(c, 'Festive 50% OFF', 50, weight=2)
        self._prize(c, '20% OFF', 20, weight=10)
        self._prize(c, '10% OFF', 10, weight=25)

        owner = self._owner(org)
        pool = list(CUSTOMERS); self.rng.shuffle(pool)
        entries = []
        for name, ph in pool[:7]:
            e = self._enter(c, name, ph, consent=self.rng.random() > 0.3)
            self._mark_whatsapp_sent(e)
            if e:
                entries.append(e)
        # 3 redeemed, the rest expired (campaign is over).
        for e in entries[:3]:
            self._redeem(e, owner)
        for e in entries[3:]:
            self._expire(e)
        # Backdate entered_at so it reads as a past campaign.
        for e in entries:
            type(e).objects.filter(pk=e.pk).update(
                entered_at=timezone.now() - timedelta(days=45))
        # Now close the campaign: past end_date + ENDED status.
        c.status = CampaignStatus.ENDED
        c.end_date = timezone.localdate() - timedelta(days=30)
        c.save(update_fields=['status', 'end_date'])
        self.stdout.write(self.style.SUCCESS("  ✔ Christmas Cracker Draw 2025 (ended, historical)"))

    # ── summary ────────────────────────────────────────────────────────
    def _summary(self, org):
        from apps.lucky_draw.models import LuckyDrawEntry
        camps = LuckyDrawCampaign.objects.filter(organization=org)
        entries = LuckyDrawEntry.objects.filter(campaign__organization=org)
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("── Seed summary ──"))
        self.stdout.write(f"  Campaigns: {camps.count()}")
        for st, _ in CampaignStatus.choices:
            n = camps.filter(status=st).count()
            if n:
                self.stdout.write(f"    {st:>7}: {n}")
        self.stdout.write(f"  Entries: {entries.count()}")
        for st, _ in EntryStatus.choices:
            n = entries.filter(status=st).count()
            if n:
                self.stdout.write(f"    {st:>9}: {n}")
        self.stdout.write(f"  Referred entries: {entries.filter(referred_by_entry__isnull=False).count()}")
        self.stdout.write(f"  WhatsApp-delivered: {entries.filter(whatsapp_sent_at__isnull=False).count()}")
        self.stdout.write(f"  CRM customers linked: {entries.filter(crm_customer__isnull=False).values('crm_customer').distinct().count()}")
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            "Done. Open the dashboard → Engage → Lucky Draw to view/edit these campaigns."))
