import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.knowledge.models import KnowledgeBase, FAQ
from apps.accounts.models import Organization

# Get organization
org = Organization.objects.get(id='a52c5135-677e-49af-854c-afdc12d96fe1')

# Create or update knowledge base
kb, created = KnowledgeBase.objects.update_or_create(
    organization=org,
    location=None,  # Organization-level
    defaults={
        'business_description': 'We are a premium restaurant and real estate service provider in Nepal. We offer authentic cuisine and professional real estate consultation.',
        'services': ['Restaurant Dining', 'Takeaway', 'Delivery', 'Real Estate Consultation', 'Property Management'],
        'opening_hours': 'Mon-Fri: 9am-9pm, Sat-Sun: 10am-10pm',
        'contact_info': 'Phone: +977 981-4344114, Email: info@restro.np, Address: Kathmandu, Nepal',
        'policies': 'Reservations recommended for groups of 6+. 24-hour cancellation policy. No-show fees may apply.',
        'additional_info': 'We specialize in traditional Nepali cuisine with modern fusion options. Also providing commercial property management and real estate consultation services.'
    }
)

print(f'✅ Knowledge Base {"created" if created else "updated"}!')
print(f'ID: {kb.id}')
print(f'Organization: {kb.organization.name}')
print(f'Services: {", ".join(kb.services)}')
print()

# Create sample FAQs
faqs_data = [
    {
        'question': 'What are your operating hours?',
        'answer': 'We are open Monday to Friday from 9am to 9pm, and weekends (Saturday-Sunday) from 10am to 10pm.',
        'order': 0
    },
    {
        'question': 'Do you offer delivery service?',
        'answer': 'Yes! We offer delivery service within Kathmandu valley. Delivery is free for orders above NPR 1000.',
        'order': 1
    },
    {
        'question': 'What types of cuisine do you serve?',
        'answer': 'We specialize in traditional Nepali cuisine including Dal Bhat, Momos, and Newari dishes. We also offer modern fusion options.',
        'order': 2
    },
    {
        'question': 'Do you take reservations?',
        'answer': 'Yes, we recommend reservations especially for groups of 6 or more. You can call us at +977 981-4344114 or book through our website.',
        'order': 3
    },
    {
        'question': 'What real estate services do you provide?',
        'answer': 'We offer comprehensive real estate services including property consultation, commercial property management, rental assistance, and investment guidance.',
        'order': 4
    },
    {
        'question': 'Can I book a table through WhatsApp?',
        'answer': 'Absolutely! You can send us a WhatsApp message at +977 981-4344114 with your preferred date, time, and number of guests.',
        'order': 5
    }
]

print('Adding sample FAQs...')
for faq_data in faqs_data:
    faq, created = FAQ.objects.update_or_create(
        knowledge_base=kb,
        question=faq_data['question'],
        defaults={
            'answer': faq_data['answer'],
            'order': faq_data['order']
        }
    )
    status = "✓ Created" if created else "✓ Updated"
    print(f'{status}: {faq.question}')

print()
print(f'✅ Complete! Added {len(faqs_data)} FAQs to knowledge base')
print(f'Total FAQs: {kb.faqs.count()}')
