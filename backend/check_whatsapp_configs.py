import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, '/app')
django.setup()

from apps.channels.models import WhatsAppConfig
from apps.accounts.models import Organization

print('=== ALL WHATSAPP CONFIGURATIONS IN DATABASE ===\n')

configs = WhatsAppConfig.objects.all()
if not configs:
    print('No WhatsApp configurations found!')
else:
    for i, c in enumerate(configs, 1):
        print(f'Config {i}:')
        print(f'  Organization: {c.organization.name}')
        print(f'  Phone Number ID: {c.phone_number_id}')
        print(f'  Business Account ID: {c.business_account_id}')
        print(f'  Is Active: {c.is_active}')
        print(f'  Is Verified: {c.is_verified}')
        print(f'  Verify Token: {c.verify_token}')
        print()

print('\n=== SCREENSHOT ANALYSIS ===')
print('From your WhatsApp Manager screenshot, you have 3 Business Accounts:')
print('1. Test WhatsApp Business Account - ID: 254968522189957494')
print('2. Restro Service - ID: 858394640489971')
print('3. Resto and realstate service - ID: 945295628170745')
print()
print('Phone Number shown: 15551477652 (Status: Connected)')
print()
print('We need to get the Phone Number ID for 15551477652 from the connected account.')
