import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.messaging.models import Conversation, Message

# Get conversation
c = Conversation.objects.get(customer_phone='9779705651002')

print('=== CONVERSATION: Test User Nepal ===')
print(f'Phone: {c.customer_phone}')
print(f'State: {c.state}')
print(f'Messages: {c.messages.count()}\n')

for m in c.messages.all():
    print(f'{m.sender.upper()}: {m.content}')
    if m.sender == 'ai':
        print(f'  Confidence: {m.confidence_score}')
        print(f'  Intent: {m.intent}')
    print()
