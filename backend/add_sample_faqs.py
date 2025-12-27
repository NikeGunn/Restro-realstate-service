#!/usr/bin/env python
"""
Add sample FAQs to the knowledge base
Run: docker exec chatplatform_backend python add_sample_faqs.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.knowledge.models import KnowledgeBase, FAQ
from apps.accounts.models import Organization

# Get first organization
org = Organization.objects.first()
print(f'Organization: {org.name}')

# Create or get knowledge base
kb, created = KnowledgeBase.objects.get_or_create(
    organization=org,
    location=None,  # Organization-level knowledge
    defaults={
        'business_description': 'Authentic Italian restaurant serving traditional family recipes since 1985.',
        'opening_hours': {
            'monday': {'open': '11:00', 'close': '22:00'},
            'tuesday': {'open': '11:00', 'close': '22:00'},
            'wednesday': {'open': '11:00', 'close': '22:00'},
            'thursday': {'open': '11:00', 'close': '22:00'},
            'friday': {'open': '11:00', 'close': '23:00'},
            'saturday': {'open': '11:00', 'close': '23:00'},
            'sunday': {'open': '12:00', 'close': '21:00'},
        },
        'contact_info': {
            'phone': '(555) 123-4567',
            'email': 'info@bellaitalia.com',
            'address': '123 Main Street, Downtown, New York, NY 10001'
        },
        'services': ['Dine-in', 'Takeout', 'Delivery', 'Catering', 'Reservations'],
        'additional_info': 'We specialize in authentic Italian cuisine with fresh, locally-sourced ingredients.',
        'policies': {
            'reservation': 'Reservations recommended for parties of 6 or more',
            'cancellation': 'Please call at least 2 hours in advance for cancellations',
            'payment': 'We accept all major credit cards',
            'parking': 'Free parking available in the lot behind the restaurant'
        }
    }
)
print(f'Knowledge Base: {kb} ({"Created" if created else "Already exists"})')

# Add FAQs
faqs = [
    ('What are your hours?', 'We are open Monday-Thursday 11am-10pm, Friday-Saturday 11am-11pm, and Sunday 12pm-9pm.'),
    ('Do you have a menu?', 'Yes! We serve authentic Italian cuisine including pasta, pizza, meat dishes, and desserts. Our specialties include Spaghetti Carbonara ($16.99), Margherita Pizza ($14.99), Osso Buco ($28.99), and Tiramisu ($8.99).'),
    ('Can I make a reservation?', 'Yes! You can call us at (555) 123-4567 or email info@bellaitalia.com to make a reservation.'),
    ('Do you have vegetarian options?', 'Yes! We offer several vegetarian dishes including Margherita Pizza, Caprese Salad, Pasta Primavera, and Eggplant Parmigiana.'),
    ('Where are you located?', 'We are located at 123 Main Street, Downtown, New York, NY 10001.'),
    ('Do you offer delivery?', 'Yes, we partner with major delivery services. You can also call us for takeout orders.'),
    ('Do you have parking?', 'Yes, we have free parking available in the lot behind our restaurant.'),
    ('What is your most popular dish?', 'Our most popular dishes are the Spaghetti Carbonara and Margherita Pizza. Both are made with authentic Italian ingredients!'),
    ('Do you take credit cards?', 'Yes, we accept all major credit cards including Visa, Mastercard, American Express, and Discover.'),
    ('Is there a kids menu?', 'Yes, we have a kids menu with pasta, pizza, and chicken dishes, all priced under $10.'),
]

count = 0
for question, answer in faqs:
    faq, created = FAQ.objects.get_or_create(
        knowledge_base=kb,
        question=question,
        defaults={'answer': answer, 'is_active': True}
    )
    if created:
        count += 1
        print(f'✅ Added: {question[:50]}...')
    else:
        print(f'⏭️  Skipped (exists): {question[:50]}...')

print(f'\n✅ Total FAQs added: {count}')
print(f'📚 Total FAQs in knowledge base: {FAQ.objects.filter(knowledge_base=kb).count()}')
print(f'📚 Total FAQs in system: {FAQ.objects.count()}')
print('\n🎉 Done! Now test your chatbot again!')
