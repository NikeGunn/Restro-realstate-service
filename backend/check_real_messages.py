import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.messaging.models import Conversation, Message

# Get the conversation
c = Conversation.objects.get(customer_phone='9779705651002')

print(f'=== CONVERSATION: {c.customer_name} ===')
print(f'ID: {c.id}')
print(f'Phone: {c.customer_phone}')
print(f'State: {c.state}')
print(f'Total Messages: {c.messages.count()}')
print()

# Get messages from real WhatsApp (after 11:34)
print('Messages from real WhatsApp webhook (after 11:34):')
recent_messages = c.messages.filter(created_at__hour__gte=11, created_at__minute__gte=34).order_by('created_at')

for m in recent_messages:
    time_str = m.created_at.strftime('%H:%M')
    print(f'  [{time_str}] {m.sender.upper()}: {m.content}')
    if m.sender == 'ai':
        print(f'           Confidence: {m.confidence_score}')

print()
print(f'Expected: AI should have responded to "What are your hours?"')
print(f'Actual: {recent_messages.filter(sender="ai").count()} AI responses found')
