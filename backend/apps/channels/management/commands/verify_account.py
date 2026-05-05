"""
Verify and activate a customer account end-to-end.

Usage (run on production via kubectl exec):
    python manage.py verify_account --email bagaichahk@gmail.com

Idempotent: safe to run repeatedly. Only flips inactive flags to active;
never overwrites credentials.
"""
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from apps.accounts.models import Organization, OrganizationMembership, Location

User = get_user_model()


class Command(BaseCommand):
    help = "Verify a user, their organization, default location, and report channel/widget status."

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True, help='User email to verify')

    def handle(self, *args, **options):
        email = options['email'].strip().lower()
        out = self.stdout.write

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise CommandError(f"❌ No user with email '{email}' found.")

        out(self.style.SUCCESS(f"✅ User found: {user.email} (id={user.id})"))
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=['is_active'])
            out(self.style.WARNING("   ↳ Activated user (was inactive)."))

        memberships = OrganizationMembership.objects.filter(user=user).select_related('organization')
        if not memberships.exists():
            out(self.style.ERROR("❌ User has no organization memberships. They need to complete /setup-organization."))
            return

        for m in memberships:
            org = m.organization
            out(f"\n— Organization: {org.name} (role={m.role}, plan={org.plan}, business_type={org.business_type})")

            if not org.is_active:
                org.is_active = True
                org.save(update_fields=['is_active'])
                out(self.style.WARNING("   ↳ Activated org (was inactive)."))

            out(f"   widget_key: {org.widget_key}")

            # Ensure at least one Location
            loc_qs = Location.objects.filter(organization=org)
            if not loc_qs.exists():
                Location.objects.create(
                    organization=org,
                    name=f"{org.name} - Main",
                    is_active=True,
                )
                out(self.style.WARNING("   ↳ Created default Location."))
            else:
                out(f"   locations: {loc_qs.count()}")

            # Channel status
            wa = getattr(org, 'whatsapp_config', None)
            tw = getattr(org, 'twilio_config', None)
            ig = getattr(org, 'instagram_config', None)
            out(f"   whatsapp_meta:    {'configured & active' if wa and wa.is_active else ('configured (inactive)' if wa else 'not configured')}")
            out(f"   whatsapp_twilio:  {'configured & active' if tw and tw.is_active else ('configured (inactive)' if tw else 'not configured')}")
            out(f"   instagram:        {'configured & active' if ig and ig.is_active else ('configured (inactive)' if ig else 'not configured')}")

            # Knowledge base / FAQ counts
            try:
                from apps.knowledge.models import KnowledgeBase, FAQ
                kb_count = KnowledgeBase.objects.filter(organization=org).count()
                faq_count = FAQ.objects.filter(knowledge_base__organization=org).count()
                out(f"   knowledge_base entries: {kb_count}, FAQs: {faq_count}")
            except Exception as e:
                out(f"   knowledge: (could not query: {e})")

        out(self.style.SUCCESS("\n✅ Verification complete."))
