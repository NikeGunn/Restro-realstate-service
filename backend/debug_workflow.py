#!/usr/bin/env python
"""
Debug Script for AI Business Chat Platform
==========================================
This script tests the entire workflow for both Restaurant and Real Estate verticals.
Run this after migrations to verify all endpoints and models work correctly.

Usage:
    python manage.py shell < debug_workflow.py
    OR
    docker-compose exec backend python manage.py shell < debug_workflow.py
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from datetime import date, time, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db import transaction
from uuid import uuid4

# Import all models
from apps.accounts.models import Organization, Location, OrganizationMembership
from apps.knowledge.models import KnowledgeBase, FAQ
from apps.messaging.models import Conversation, Message, WidgetSession

# Try importing restaurant and realestate models
try:
    from apps.restaurant.models import (
        MenuCategory, MenuItem, OpeningHours, DailySpecial, 
        Booking, BookingSettings
    )
    RESTAURANT_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Restaurant models not available: {e}")
    RESTAURANT_AVAILABLE = False

try:
    from apps.realestate.models import PropertyListing, Lead, Appointment
    REALESTATE_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Real Estate models not available: {e}")
    REALESTATE_AVAILABLE = False

User = get_user_model()


class DebugWorkflow:
    """Debug and test the entire platform workflow."""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.successes = []
        
    def log_success(self, message):
        self.successes.append(message)
        print(f"✅ {message}")
        
    def log_error(self, message, exception=None):
        full_msg = f"{message}: {exception}" if exception else message
        self.errors.append(full_msg)
        print(f"❌ {full_msg}")
        
    def log_warning(self, message):
        self.warnings.append(message)
        print(f"⚠️  {message}")
        
    def log_info(self, message):
        print(f"ℹ️  {message}")

    @transaction.atomic
    def test_restaurant_workflow(self):
        """Test complete restaurant workflow."""
        print("\n" + "="*60)
        print("🍽️  TESTING RESTAURANT WORKFLOW")
        print("="*60 + "\n")
        
        if not RESTAURANT_AVAILABLE:
            self.log_error("Restaurant app not installed. Run migrations first.")
            return None
            
        try:
            # 1. Create test user
            self.log_info("Creating test restaurant user...")
            user, created = User.objects.get_or_create(
                email='debug_restaurant@test.com',
                defaults={
                    'username': 'debug_restaurant',
                    'first_name': 'Debug',
                    'last_name': 'Restaurant',
                }
            )
            if created:
                user.set_password('testpass123')
                user.save()
                self.log_success(f"Created user: {user.email}")
            else:
                self.log_info(f"Using existing user: {user.email}")
                
            # 2. Create organization
            self.log_info("Creating restaurant organization...")
            org, created = Organization.objects.get_or_create(
                name='Debug Restaurant',
                defaults={
                    'business_type': 'restaurant',
                    'email': 'debug@restaurant.test',
                    'phone': '555-DEBUG-01',
                    'widget_greeting': 'Welcome to Debug Restaurant!',
                }
            )
            if created:
                OrganizationMembership.objects.create(
                    user=user, organization=org, role='owner'
                )
                self.log_success(f"Created organization: {org.name} (widget_key: {org.widget_key})")
            else:
                self.log_info(f"Using existing organization: {org.name}")
                
            # 3. Create location
            self.log_info("Creating location...")
            location, created = Location.objects.get_or_create(
                organization=org,
                name='Main Branch',
                defaults={
                    'address_line1': '123 Debug Street',
                    'city': 'Test City',
                    'state': 'TS',
                    'postal_code': '12345',
                    'is_primary': True,
                }
            )
            if created:
                self.log_success(f"Created location: {location.name}")
            else:
                self.log_info(f"Using existing location: {location.name}")
                
            # 4. Create menu category
            self.log_info("Creating menu category...")
            category, created = MenuCategory.objects.get_or_create(
                organization=org,
                name='Appetizers',
                defaults={
                    'description': 'Start your meal right',
                    'display_order': 1,
                    'is_active': True,
                }
            )
            if created:
                self.log_success(f"Created category: {category.name} (ID: {category.id})")
            else:
                self.log_info(f"Using existing category: {category.name} (ID: {category.id})")
                
            # 5. Create menu items
            self.log_info("Creating menu items...")
            items_data = [
                {'name': 'Bruschetta', 'price': Decimal('9.99'), 'dietary_info': ['vegetarian']},
                {'name': 'Calamari', 'price': Decimal('12.99'), 'dietary_info': []},
                {'name': 'Soup of the Day', 'price': Decimal('6.99'), 'dietary_info': ['vegetarian', 'gluten-free']},
            ]
            for i, item_data in enumerate(items_data):
                item, created = MenuItem.objects.get_or_create(
                    category=category,
                    name=item_data['name'],
                    defaults={
                        'description': f"Delicious {item_data['name']}",
                        'price': item_data['price'],
                        'dietary_info': item_data['dietary_info'],
                        'is_available': True,
                        'display_order': i + 1,
                    }
                )
                if created:
                    self.log_success(f"Created item: {item.name} (${item.price})")
                    
            # 6. Create opening hours
            self.log_info("Creating opening hours...")
            for day in range(7):
                hours, created = OpeningHours.objects.get_or_create(
                    location=location,
                    day_of_week=day,
                    defaults={
                        'open_time': time(11, 0) if day < 6 else time(12, 0),
                        'close_time': time(22, 0) if day < 4 else time(23, 0),
                        'is_closed': False,
                    }
                )
                if created:
                    day_name = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][day]
                    self.log_success(f"Created hours for {day_name}: {hours.open_time}-{hours.close_time}")
                    
            # 7. Create booking settings
            self.log_info("Creating booking settings...")
            settings, created = BookingSettings.objects.get_or_create(
                location=location,
                defaults={
                    'max_party_size': 12,
                    'min_party_size': 1,
                    'slot_duration_minutes': 90,
                    'advance_booking_days': 30,
                    'min_advance_hours': 2,
                    'auto_confirm': True,
                    'require_phone': True,
                    'require_email': True,
                }
            )
            if created:
                self.log_success(f"Created booking settings (max party: {settings.max_party_size})")
                
            # 8. Create a daily special
            self.log_info("Creating daily special...")
            special, created = DailySpecial.objects.get_or_create(
                organization=org,
                name='Pasta Tuesday',
                defaults={
                    'description': 'All pasta 20% off!',
                    'price': Decimal('15.99'),
                    'original_price': Decimal('19.99'),
                    'start_date': date.today(),
                    'end_date': date.today() + timedelta(days=365),
                    'recurring_days': [1],  # Tuesday
                    'is_active': True,
                }
            )
            if created:
                self.log_success(f"Created special: {special.name}")
                
            # 9. Create a test booking
            self.log_info("Creating test booking...")
            booking = Booking.objects.create(
                location=location,
                booking_date=date.today() + timedelta(days=3),
                booking_time=time(19, 0),
                party_size=4,
                customer_name='John Debug',
                customer_email='john@debug.test',
                customer_phone='555-1234',
                source='widget',
                status='confirmed' if settings.auto_confirm else 'pending',
            )
            self.log_success(f"Created booking: {booking.confirmation_code} for {booking.party_size} guests")
            
            # 10. Verify querysets
            self.log_info("Verifying querysets...")
            categories = MenuCategory.objects.filter(organization=org)
            items = MenuItem.objects.filter(category__organization=org)
            hours = OpeningHours.objects.filter(location=location)
            bookings = Booking.objects.filter(location__organization=org)
            
            self.log_success(f"Found {categories.count()} categories, {items.count()} items, {hours.count()} hours, {bookings.count()} bookings")
            
            return {
                'org': org,
                'location': location,
                'category': category,
                'booking': booking,
            }
            
        except Exception as e:
            self.log_error("Restaurant workflow failed", e)
            import traceback
            traceback.print_exc()
            return None

    @transaction.atomic
    def test_realestate_workflow(self):
        """Test complete real estate workflow."""
        print("\n" + "="*60)
        print("🏠 TESTING REAL ESTATE WORKFLOW")
        print("="*60 + "\n")
        
        if not REALESTATE_AVAILABLE:
            self.log_error("Real Estate app not installed. Run migrations first.")
            return None
            
        try:
            # 1. Create test user
            self.log_info("Creating test real estate user...")
            user, created = User.objects.get_or_create(
                email='debug_realestate@test.com',
                defaults={
                    'username': 'debug_realestate',
                    'first_name': 'Debug',
                    'last_name': 'RealEstate',
                }
            )
            if created:
                user.set_password('testpass123')
                user.save()
                self.log_success(f"Created user: {user.email}")
                
            # 2. Create organization
            self.log_info("Creating real estate organization...")
            org, created = Organization.objects.get_or_create(
                name='Debug Realty',
                defaults={
                    'business_type': 'real_estate',
                    'email': 'debug@realty.test',
                    'phone': '555-DEBUG-02',
                    'widget_greeting': 'Welcome to Debug Realty!',
                }
            )
            if created:
                OrganizationMembership.objects.create(
                    user=user, organization=org, role='owner'
                )
                self.log_success(f"Created organization: {org.name} (widget_key: {org.widget_key})")
                
            # 3. Create location (office)
            self.log_info("Creating office location...")
            location, created = Location.objects.get_or_create(
                organization=org,
                name='Main Office',
                defaults={
                    'address_line1': '456 Realty Ave',
                    'city': 'Test City',
                    'state': 'TS',
                    'postal_code': '12345',
                    'is_primary': True,
                }
            )
            if created:
                self.log_success(f"Created location: {location.name}")
                
            # 4. Create property listings
            self.log_info("Creating property listings...")
            properties_data = [
                {
                    'title': '4BR Family Home with Pool',
                    'listing_type': 'sale',
                    'property_type': 'house',
                    'price': Decimal('850000'),
                    'bedrooms': 4,
                    'bathrooms': Decimal('3.0'),
                    'square_feet': 2800,
                    'city': 'Austin',
                    'state': 'TX',
                },
                {
                    'title': 'Modern Downtown Condo',
                    'listing_type': 'rent',
                    'property_type': 'condo',
                    'price': Decimal('2500'),
                    'bedrooms': 2,
                    'bathrooms': Decimal('2.0'),
                    'square_feet': 1200,
                    'city': 'Austin',
                    'state': 'TX',
                },
            ]
            
            properties = []
            for prop_data in properties_data:
                prop, created = PropertyListing.objects.get_or_create(
                    organization=org,
                    title=prop_data['title'],
                    defaults={
                        **prop_data,
                        'description': f"Beautiful {prop_data['title']}",
                        'address_line1': '123 Test St',
                        'postal_code': '78701',
                        'features': ['garage', 'central-ac'],
                        'is_featured': True,
                        'status': 'active',
                    }
                )
                properties.append(prop)
                if created:
                    self.log_success(f"Created property: {prop.title} (${prop.price})")
                    
            # 5. Create a lead
            self.log_info("Creating test lead...")
            lead = Lead.objects.create(
                organization=org,
                name='Jane Debug',
                email='jane@debug.test',
                phone='555-5678',
                intent='buy',
                budget_min=500000,
                budget_max=900000,
                preferred_areas=['Austin', 'Round Rock'],
                property_type_preference='house',
                bedrooms_min=3,
                source='widget',
                priority='high',
            )
            # Calculate lead score
            lead.lead_score = lead.calculate_score()
            lead.save()
            self.log_success(f"Created lead: {lead.name} (score: {lead.lead_score})")
            
            # 6. Create an appointment
            self.log_info("Creating test appointment...")
            appointment = Appointment.objects.create(
                lead=lead,
                property=properties[0],
                appointment_date=date.today() + timedelta(days=2),
                appointment_time=time(14, 0),
                duration_minutes=60,
                appointment_type='in_person',
                status='confirmed',
            )
            self.log_success(f"Created appointment: {appointment.confirmation_code}")
            
            # 7. Verify querysets
            self.log_info("Verifying querysets...")
            all_properties = PropertyListing.objects.filter(organization=org)
            all_leads = Lead.objects.filter(organization=org)
            all_appointments = Appointment.objects.filter(lead__organization=org)
            
            self.log_success(f"Found {all_properties.count()} properties, {all_leads.count()} leads, {all_appointments.count()} appointments")
            
            return {
                'org': org,
                'location': location,
                'properties': properties,
                'lead': lead,
                'appointment': appointment,
            }
            
        except Exception as e:
            self.log_error("Real Estate workflow failed", e)
            import traceback
            traceback.print_exc()
            return None

    def test_api_endpoints(self, restaurant_data, realestate_data):
        """Test API endpoint accessibility."""
        print("\n" + "="*60)
        print("🔌 TESTING API ENDPOINT CONFIGURATION")
        print("="*60 + "\n")
        
        from django.urls import reverse, NoReverseMatch
        from django.test import RequestFactory
        
        # Test URL patterns exist
        endpoints_to_test = []
        
        if RESTAURANT_AVAILABLE:
            endpoints_to_test.extend([
                ('restaurant:menu-category-list', 'Restaurant Categories'),
                ('restaurant:menu-item-list', 'Restaurant Items'),
                ('restaurant:opening-hours-list', 'Restaurant Hours'),
                ('restaurant:daily-special-list', 'Restaurant Specials'),
                ('restaurant:booking-list', 'Restaurant Bookings'),
                ('restaurant:booking-settings-list', 'Restaurant Booking Settings'),
            ])
            
        if REALESTATE_AVAILABLE:
            endpoints_to_test.extend([
                ('realestate:property-listing-list', 'Real Estate Properties'),
                ('realestate:lead-list', 'Real Estate Leads'),
                ('realestate:appointment-list', 'Real Estate Appointments'),
            ])
            
        for url_name, description in endpoints_to_test:
            try:
                url = reverse(url_name)
                self.log_success(f"{description}: {url}")
            except NoReverseMatch as e:
                self.log_error(f"{description} URL not found", e)

    def print_summary(self):
        """Print test summary."""
        print("\n" + "="*60)
        print("📊 TEST SUMMARY")
        print("="*60)
        print(f"\n✅ Successes: {len(self.successes)}")
        print(f"⚠️  Warnings: {len(self.warnings)}")
        print(f"❌ Errors: {len(self.errors)}")
        
        if self.errors:
            print("\n❌ ERRORS:")
            for error in self.errors:
                print(f"   - {error}")
                
        if self.warnings:
            print("\n⚠️  WARNINGS:")
            for warning in self.warnings:
                print(f"   - {warning}")
                
        print("\n" + "="*60)
        if not self.errors:
            print("🎉 ALL TESTS PASSED!")
        else:
            print("❌ SOME TESTS FAILED - Check errors above")
        print("="*60 + "\n")


def main():
    print("\n" + "="*60)
    print("🔍 AI BUSINESS CHAT PLATFORM - DEBUG WORKFLOW")
    print("="*60)
    
    debug = DebugWorkflow()
    
    # Test Restaurant workflow
    restaurant_data = debug.test_restaurant_workflow()
    
    # Test Real Estate workflow
    realestate_data = debug.test_realestate_workflow()
    
    # Test API endpoints
    debug.test_api_endpoints(restaurant_data, realestate_data)
    
    # Print summary
    debug.print_summary()
    
    return debug.errors == []


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
