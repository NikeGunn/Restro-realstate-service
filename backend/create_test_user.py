"""
Script to create test user for testing channels
Run with: docker exec chatplatform_backend python create_test_user.py
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, '/app')
django.setup()

from apps.accounts.models import User, Organization, OrganizationMembership
from django.contrib.auth.hashers import make_password

def create_test_user():
    # Create or get user
    user, created = User.objects.get_or_create(
        email='owner@restaurant.com',
        defaults={
            'username': 'owner',
            'first_name': 'John',
            'last_name': 'Smith',
            'password': make_password('password123'),
            'is_active': True
        }
    )
    if created:
        print(f'✅ Created user: {user.email}')
    else:
        user.password = make_password('password123')
        user.save()
        print(f'✅ Updated password for: {user.email}')

    # Create or get organization
    org, created = Organization.objects.get_or_create(
        name='John Restro Organization',
        defaults={
            'business_type': 'restaurant',
            'plan': 'power'
        }
    )
    if created:
        print(f'✅ Created org: {org.name}')
    else:
        org.plan = 'power'
        org.save()
        print(f'✅ Updated org: {org.name} (Plan: power)')

    # Create membership
    membership, created = OrganizationMembership.objects.get_or_create(
        user=user,
        organization=org,
        defaults={'role': 'owner'}
    )
    if created:
        print('✅ Created membership')
    else:
        print('✅ Membership exists')

    print(f'\n📧 Test Credentials:')
    print(f'   Email: owner@restaurant.com')
    print(f'   Password: password123')
    print(f'   Organization: {org.name} (ID: {org.id})')

if __name__ == '__main__':
    create_test_user()
