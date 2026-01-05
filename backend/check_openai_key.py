import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings

print('=== CONFIGURATION CHECK ===')
print(f'OpenAI API Key configured: {bool(settings.OPENAI_API_KEY)}')
if settings.OPENAI_API_KEY:
    print(f'Key starts with: {settings.OPENAI_API_KEY[:20]}...')
else:
    print('⚠️  OpenAI API Key is NOT SET!')
    print('This is why the AI is not responding!')
