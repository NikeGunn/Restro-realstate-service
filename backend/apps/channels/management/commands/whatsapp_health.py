"""
Management command: check_whatsapp
Diagnoses the WhatsApp configuration for all organizations and prints
a detailed health report. Run on production to find exactly what is broken.

Usage:
    python manage.py check_whatsapp
    python manage.py check_whatsapp --org <org_name_or_id>
    python manage.py check_whatsapp --send-test +919876543210
"""
import requests
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = "Diagnose WhatsApp configuration and connectivity"

    def add_arguments(self, parser):
        parser.add_argument('--org', help='Organization name or UUID to check (default: all)')
        parser.add_argument('--send-test', metavar='PHONE', help='Send a test message to this phone number')

    def handle(self, *args, **options):
        from apps.channels.models import WhatsAppConfig, WebhookLog
        from apps.accounts.models import Organization

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== WhatsApp Health Check ===\n"))

        # 1. Environment variables
        self.stdout.write(self.style.HTTP_INFO("[ Environment ]"))
        openai_key = getattr(settings, 'OPENAI_API_KEY', '')
        meta_secret = getattr(settings, 'META_APP_SECRET', '')
        self.stdout.write(f"  OPENAI_API_KEY    : {'✅ SET (' + openai_key[:6] + '...)' if openai_key else '❌ NOT SET — AI will not reply'}")
        self.stdout.write(f"  META_APP_SECRET   : {'✅ SET' if meta_secret else '⚠️  NOT SET — signature verification skipped (OK for dev)'}")
        self.stdout.write("")

        # 2. WhatsApp configs
        configs = WhatsAppConfig.objects.select_related('organization').all()
        if options.get('org'):
            configs = configs.filter(organization__name__icontains=options['org'])

        if not configs.exists():
            self.stdout.write(self.style.ERROR("❌ No WhatsApp configs found in database!"))
            self.stdout.write("   → Go to kribaat.com/settings/channels and create a WhatsApp config.")
            return

        for config in configs:
            org = config.organization
            self.stdout.write(self.style.HTTP_INFO(f"[ Organization: {org.name} ]"))
            self.stdout.write(f"  Config ID         : {config.id}")
            self.stdout.write(f"  is_active         : {'✅ True' if config.is_active else '❌ False — must be True'}")
            self.stdout.write(f"  is_verified       : {'✅ True' if config.is_verified else '⚠️  False (webhook not verified yet)'}")
            self.stdout.write(f"  phone_number_id   : {'✅ ' + config.phone_number_id if config.phone_number_id else '❌ EMPTY — must match Meta phone_number_id'}")
            self.stdout.write(f"  business_acct_id  : {'✅ ' + config.business_account_id if config.business_account_id else '⚠️  EMPTY'}")
            self.stdout.write(f"  access_token      : {'✅ SET (' + config.access_token[:12] + '...)' if config.access_token else '❌ EMPTY — Meta API calls will fail'}")
            self.stdout.write(f"  verify_token      : {config.verify_token}")
            self.stdout.write(f"  webhook_url       : https://kribaat.com/api/webhooks/whatsapp/")
            self.stdout.write("")

            # 3. Test Meta API connection
            if config.access_token and config.phone_number_id:
                self.stdout.write("  Testing Meta API connection...")
                try:
                    url = f"https://graph.facebook.com/v18.0/{config.phone_number_id}"
                    resp = requests.get(url, headers={"Authorization": f"Bearer {config.access_token}"}, timeout=10)
                    if resp.ok:
                        data = resp.json()
                        self.stdout.write(self.style.SUCCESS(f"  ✅ Meta API OK — phone: {data.get('display_phone_number', 'N/A')}, name: {data.get('verified_name', 'N/A')}"))
                    else:
                        err = resp.json()
                        self.stdout.write(self.style.ERROR(f"  ❌ Meta API FAILED — {err.get('error', {}).get('message', resp.text)}"))
                        self.stdout.write("     → access_token may be expired or phone_number_id is wrong")
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  ❌ Meta API ERROR — {e}"))
            else:
                self.stdout.write(self.style.ERROR("  ❌ Skipping Meta API test — access_token or phone_number_id missing"))

            # 4. Recent webhook logs
            from datetime import timedelta
            from django.utils import timezone
            cutoff = timezone.now() - timedelta(hours=24)
            logs = WebhookLog.objects.filter(
                source=WebhookLog.Source.WHATSAPP,
                organization=org,
                created_at__gte=cutoff,
            )
            total = logs.count()
            processed = logs.filter(is_processed=True).count()
            failed = logs.filter(is_processed=False).count()
            self.stdout.write(f"\n  Last 24h webhooks : total={total}, processed={processed}, failed={failed}")

            if total == 0:
                self.stdout.write(self.style.WARNING("  ⚠️  No webhooks received in 24h — Meta is not sending webhooks to this server"))
                self.stdout.write("     Check: Is the webhook URL registered in Meta Developer Console?")
                self.stdout.write("     Check: Is the webhook subscription active (messages, messaging)?")
            elif failed > 0:
                self.stdout.write(self.style.ERROR(f"  ❌ {failed} failed webhooks — check error messages below:"))
                for log in logs.filter(is_processed=False).order_by('-created_at')[:3]:
                    self.stdout.write(f"     [{log.created_at:%H:%M:%S}] {log.error_message or 'no error message'}")

            # 5. Send test message
            if options.get('send_test') and config.is_active and config.access_token:
                phone = options['send_test']
                self.stdout.write(f"\n  Sending test message to {phone}...")
                from apps.channels.whatsapp_service import WhatsAppService
                service = WhatsAppService(config)
                sid = service.send_message(phone, "🤖 Kribaat WhatsApp test message — if you see this, sending works!")
                if sid:
                    self.stdout.write(self.style.SUCCESS(f"  ✅ Test message sent — ID: {sid}"))
                else:
                    self.stdout.write(self.style.ERROR("  ❌ Test message FAILED — check logs above for Graph API error"))

            self.stdout.write("")

        self.stdout.write(self.style.MIGRATE_HEADING("=== Summary / Next Steps ==="))
        self.stdout.write("1. Ensure OPENAI_API_KEY is set in GitHub Secrets → triggers new deploy")
        self.stdout.write("2. Ensure WhatsApp config is_active=True with valid phone_number_id + access_token")
        self.stdout.write("3. In Meta Developer Console:")
        self.stdout.write("   → Set webhook URL to: https://kribaat.com/api/webhooks/whatsapp/")
        self.stdout.write("   → Set verify_token to the value shown above")
        self.stdout.write("   → Subscribe to 'messages' and 'messaging' webhook fields")
        self.stdout.write("4. Message the WhatsApp number linked to your Meta app")
        self.stdout.write("   (NOT +14155238886 which is Twilio — use your Meta phone number)\n")
