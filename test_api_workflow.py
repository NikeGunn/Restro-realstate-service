"""
Complete API Workflow Testing & Debugging Script
Tests authentication, organizations, menu, bookings, properties, and leads.
"""

import requests
import json
import sys
from datetime import datetime, timedelta

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Configuration
BASE_URL = "http://localhost:8000/api"
TEST_EMAIL = f"test_user_{datetime.now().strftime('%Y%m%d%H%M%S')}@example.com"
TEST_PASSWORD = "SecurePass123!"

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_success(msg):
    print(f"{Colors.OKGREEN}[OK] {msg}{Colors.ENDC}")

def print_error(msg):
    print(f"{Colors.FAIL}[ERROR] {msg}{Colors.ENDC}")

def print_info(msg):
    print(f"{Colors.OKCYAN}[INFO] {msg}{Colors.ENDC}")

def print_section(title):
    print(f"\n{Colors.BOLD}{Colors.HEADER}{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}{Colors.ENDC}\n")

# Test storage
test_data = {
    'access_token': None,
    'refresh_token': None,
    'user_id': None,
    'organization_id': None,
    'location_id': None,
    'category_id': None,
    'item_id': None,
    'booking_id': None,
    'property_id': None,
    'lead_id': None,
}

def test_health_check():
    """Test if backend is accessible"""
    print_section("1. HEALTH CHECK")
    try:
        response = requests.get(f"{BASE_URL}/")
        print_error(f"API root returned {response.status_code} - Expected 404 but backend is responding")
        print_success("Backend is accessible")
        return True
    except requests.exceptions.ConnectionError:
        print_error("Cannot connect to backend at http://localhost:8000")
        print_info("Make sure Docker containers are running: docker-compose ps")
        return False
    except Exception as e:
        print_error(f"Health check failed: {str(e)}")
        return False

def test_authentication():
    """Test user registration and login"""
    print_section("2. AUTHENTICATION")
    
    # Register new user
    print_info("Registering new user...")
    register_data = {
        "email": TEST_EMAIL,
        "username": TEST_EMAIL.split('@')[0],
        "first_name": "Test",
        "last_name": "User",
        "password": TEST_PASSWORD,
        "password_confirm": TEST_PASSWORD
    }
    
    try:
        response = requests.post(f"{BASE_URL}/auth/register/", json=register_data)
        if response.status_code == 201:
            data = response.json()
            test_data['access_token'] = data['tokens']['access']
            test_data['refresh_token'] = data['tokens']['refresh']
            test_data['user_id'] = data['user']['id']
            print_success(f"User registered: {data['user']['email']}")
            print_success(f"Access token obtained")
            return True
        else:
            print_error(f"Registration failed: {response.status_code}")
            print_error(f"Response: {response.text}")
            return False
    except Exception as e:
        print_error(f"Registration error: {str(e)}")
        return False

def test_current_user():
    """Test getting current user info"""
    print_section("3. CURRENT USER")
    
    headers = {"Authorization": f"Bearer {test_data['access_token']}"}
    
    try:
        response = requests.get(f"{BASE_URL}/auth/me/", headers=headers)
        if response.status_code == 200:
            user = response.json()
            print_success(f"Current user: {user['email']}")
            print_success(f"User ID: {user['id']}")
            return True
        else:
            print_error(f"Get current user failed: {response.status_code}")
            print_error(f"Response: {response.text}")
            return False
    except Exception as e:
        print_error(f"Current user error: {str(e)}")
        return False

def test_organizations():
    """Test organization creation and listing"""
    print_section("4. ORGANIZATIONS")
    
    headers = {"Authorization": f"Bearer {test_data['access_token']}"}
    
    # Create restaurant organization
    print_info("Creating restaurant organization...")
    org_data = {
        "name": "Test Restaurant",
        "business_type": "restaurant",
        "email": "restaurant@test.com",
        "phone": "(555) 123-4567",
        "widget_greeting": "Welcome to our restaurant!",
        "widget_color": "#E74C3C"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/organizations/", json=org_data, headers=headers)
        if response.status_code == 201:
            org = response.json()
            test_data['organization_id'] = org['id']
            print_success(f"Organization created: {org['name']}")
            print_success(f"Organization ID: {org['id']}")
            print_success(f"Widget Key: {org.get('widget_key', 'N/A')}")
        else:
            print_error(f"Organization creation failed: {response.status_code}")
            print_error(f"Response: {response.text}")
            return False
    except Exception as e:
        print_error(f"Organization creation error: {str(e)}")
        return False
    
    # List organizations
    print_info("Listing organizations...")
    try:
        response = requests.get(f"{BASE_URL}/organizations/", headers=headers)
        if response.status_code == 200:
            data = response.json()
            # Handle both list and paginated response
            if isinstance(data, dict) and 'results' in data:
                orgs = data['results']
            elif isinstance(data, list):
                orgs = data
            else:
                print_error(f"Unexpected response format: {type(data)}")
                print_error(f"Response: {data}")
                return False
            
            print_success(f"Found {len(orgs)} organization(s)")
            for org in orgs:
                print_info(f"  - {org['name']} ({org['business_type']})")
            return True
        else:
            print_error(f"List organizations failed: {response.status_code}")
            print_error(f"Response: {response.text}")
            return False
    except Exception as e:
        print_error(f"List organizations error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_location():
    """Test location creation or use existing default location"""
    print_section("5. LOCATION")
    
    headers = {"Authorization": f"Bearer {test_data['access_token']}"}
    
    # First, check if a default location already exists
    print_info("Checking for existing locations...")
    try:
        url = f"{BASE_URL}/organizations/{test_data['organization_id']}/locations/"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            locations = response.json()
            if isinstance(locations, dict) and 'results' in locations:
                locations = locations['results']
            
            if len(locations) > 0:
                # Use the existing default location
                test_data['location_id'] = locations[0]['id']
                print_success(f"Using existing location: {locations[0]['name']}")
                print_success(f"Location ID: {locations[0]['id']}")
                return True
        
        # If no locations exist, create one
        print_info("Creating new location...")
        location_data = {
            "name": "Main Branch",
            "address_line1": "123 Main St",
            "city": "New York",
            "state": "NY",
            "postal_code": "10001",
            "country": "USA",
            "timezone": "America/New_York",
            "is_primary": True
        }
        
        response = requests.post(url, json=location_data, headers=headers)
        if response.status_code == 201:
            location = response.json()
            test_data['location_id'] = location['id']
            print_success(f"Location created: {location['name']}")
            print_success(f"Location ID: {location['id']}")
            return True
        else:
            print_error(f"Location creation failed: {response.status_code}")
            print_error(f"Response: {response.text}")
            return False
    except Exception as e:
        print_error(f"Location error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_menu_categories():
    """Test menu category creation and listing"""
    print_section("6. MENU CATEGORIES")
    
    headers = {"Authorization": f"Bearer {test_data['access_token']}"}
    
    # Create category
    print_info("Creating menu category...")
    category_data = {
        "organization": test_data['organization_id'],
        "name": "Appetizers",
        "description": "Start your meal right",
        "display_order": 1,
        "is_active": True
    }
    
    try:
        response = requests.post(f"{BASE_URL}/restaurant/categories/", json=category_data, headers=headers)
        print_info(f"Response status: {response.status_code}")
        if response.status_code == 201:
            category = response.json()
            test_data['category_id'] = category.get('id')
            if test_data['category_id']:
                print_success(f"Category created: ID {test_data['category_id']}")
            else:
                print_error("No ID in response!")
                print_error(f"Response data: {category}")
                return False
        else:
            print_error(f"Category creation failed: {response.status_code}")
            print_error(f"Response: {response.text}")
            return False
    except Exception as e:
        print_error(f"Category creation error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    # List categories
    print_info("Listing menu categories...")
    try:
        url = f"{BASE_URL}/restaurant/categories/?organization={test_data['organization_id']}"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            categories = response.json()
            # Handle both list and paginated response
            if isinstance(categories, dict) and 'results' in categories:
                categories = categories['results']
            print_success(f"Found {len(categories)} category(ies)")
            for cat in categories:
                print_info(f"  - {cat['name']} ({cat.get('items_count', 0)} items)")
            return True
        else:
            print_error(f"List categories failed: {response.status_code}")
            print_error(f"Response: {response.text}")
            return False
    except Exception as e:
        print_error(f"List categories error: {str(e)}")
        return False

def test_menu_items():
    """Test menu item creation and listing"""
    print_section("7. MENU ITEMS")
    
    headers = {"Authorization": f"Bearer {test_data['access_token']}"}
    
    # Create item
    print_info("Creating menu item...")
    item_data = {
        "category": test_data['category_id'],
        "name": "Bruschetta",
        "description": "Toasted bread with fresh tomatoes and basil",
        "price": "9.99",
        "dietary_info": ["vegetarian"],
        "allergens": ["gluten"],
        "is_available": True,
        "is_featured": True,
        "display_order": 1
    }
    
    try:
        response = requests.post(f"{BASE_URL}/restaurant/items/", json=item_data, headers=headers)
        if response.status_code == 201:
            item = response.json()
            test_data['item_id'] = item['id']
            print_success(f"Item created: {item['name']}")
            print_success(f"Item ID: {item['id']}")
            print_success(f"Price: ${item['price']}")
        else:
            print_error(f"Item creation failed: {response.status_code}")
            print_error(f"Response: {response.text}")
            return False
    except Exception as e:
        print_error(f"Item creation error: {str(e)}")
        return False
    
    # List items
    print_info("Listing menu items...")
    try:
        url = f"{BASE_URL}/restaurant/items/?category={test_data['category_id']}"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            items = response.json()
            if isinstance(items, dict) and 'results' in items:
                items = items['results']
            print_success(f"Found {len(items)} item(s)")
            for item in items:
                print_info(f"  - {item['name']}: ${item['price']}")
            return True
        else:
            print_error(f"List items failed: {response.status_code}")
            print_error(f"Response: {response.text}")
            return False
    except Exception as e:
        print_error(f"List items error: {str(e)}")
        return False

def test_opening_hours():
    """Test opening hours configuration"""
    print_section("8. OPENING HOURS")
    
    headers = {"Authorization": f"Bearer {test_data['access_token']}"}
    
    print_info("Creating opening hours...")
    hours_data = {
        "location": test_data['location_id'],
        "hours": [
            {"day_of_week": 0, "open_time": "11:00", "close_time": "22:00"},
            {"day_of_week": 1, "open_time": "11:00", "close_time": "22:00"},
            {"day_of_week": 2, "open_time": "11:00", "close_time": "22:00"},
            {"day_of_week": 3, "open_time": "11:00", "close_time": "22:00"},
            {"day_of_week": 4, "open_time": "11:00", "close_time": "23:00"},
            {"day_of_week": 5, "open_time": "11:00", "close_time": "23:00"},
            {"day_of_week": 6, "open_time": "12:00", "close_time": "21:00"}
        ]
    }
    
    try:
        response = requests.post(f"{BASE_URL}/restaurant/hours/bulk_update/", json=hours_data, headers=headers)
        if response.status_code in [200, 201]:
            print_success(f"Created/updated opening hours")
            return True
        else:
            print_error(f"Opening hours creation failed: {response.status_code}")
            print_error(f"Response: {response.text}")
            return False
    except Exception as e:
        print_error(f"Opening hours error: {str(e)}")
        return False

def test_booking_settings():
    """Test booking settings creation"""
    print_section("9. BOOKING SETTINGS")
    
    headers = {"Authorization": f"Bearer {test_data['access_token']}"}
    
    print_info("Creating booking settings...")
    settings_data = {
        "location": test_data['location_id'],
        "max_party_size": 12,
        "min_party_size": 1,
        "slot_duration_minutes": 90,
        "advance_booking_days": 30,
        "min_advance_hours": 2,
        "auto_confirm": True,
        "require_phone": True,
        "cancellation_policy": "Please cancel 24 hours in advance."
    }
    
    try:
        response = requests.post(f"{BASE_URL}/restaurant/booking-settings/", json=settings_data, headers=headers)
        if response.status_code == 201:
            settings = response.json()
            print_success(f"Booking settings created for location {settings['location']}")
            print_success(f"Max party size: {settings['max_party_size']}")
            return True
        else:
            print_error(f"Booking settings creation failed: {response.status_code}")
            print_error(f"Response: {response.text}")
            return False
    except Exception as e:
        print_error(f"Booking settings error: {str(e)}")
        return False

def test_bookings():
    """Test booking creation and listing"""
    print_section("10. BOOKINGS")
    
    headers = {"Authorization": f"Bearer {test_data['access_token']}"}
    
    # Create booking
    print_info("Creating booking...")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    booking_data = {
        "organization": test_data['organization_id'],
        "location": test_data['location_id'],
        "booking_date": tomorrow,
        "booking_time": "19:00",
        "party_size": 4,
        "customer_name": "John Doe",
        "customer_email": "john@example.com",
        "customer_phone": "(555) 987-6543",
        "special_requests": "Window seat please",
        "source": "phone"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/restaurant/bookings/", json=booking_data, headers=headers)
        if response.status_code == 201:
            booking = response.json()
            test_data['booking_id'] = booking['id']
            print_success(f"Booking created: {booking['confirmation_code']}")
            print_success(f"Customer: {booking['customer_name']}")
            print_success(f"Date: {booking['booking_date']} at {booking['booking_time']}")
        else:
            print_error(f"Booking creation failed: {response.status_code}")
            print_error(f"Response: {response.text}")
            return False
    except Exception as e:
        print_error(f"Booking creation error: {str(e)}")
        return False
    
    # List bookings
    print_info("Listing bookings...")
    try:
        url = f"{BASE_URL}/restaurant/bookings/?organization={test_data['organization_id']}"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            bookings = response.json()
            if isinstance(bookings, dict) and 'results' in bookings:
                bookings = bookings['results']
            print_success(f"Found {len(bookings)} booking(s)")
            for booking in bookings:
                print_info(f"  - {booking['customer_name']}: {booking['booking_date']} at {booking['booking_time']}")
            return True
        else:
            print_error(f"List bookings failed: {response.status_code}")
            print_error(f"Response: {response.text}")
            return False
    except Exception as e:
        print_error(f"List bookings error: {str(e)}")
        return False

def test_booking_stats():
    """Test booking statistics"""
    print_section("11. BOOKING STATISTICS")
    
    headers = {"Authorization": f"Bearer {test_data['access_token']}"}
    
    print_info("Getting booking stats...")
    try:
        url = f"{BASE_URL}/restaurant/bookings/stats/?organization={test_data['organization_id']}"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            stats = response.json()
            print_success(f"Total bookings: {stats.get('total', 0)}")
            print_success(f"By status: {stats.get('by_status', {})}")
            print_success(f"Total guests: {stats.get('total_guests', 0)}")
            return True
        else:
            print_error(f"Get stats failed: {response.status_code}")
            print_error(f"Response: {response.text}")
            return False
    except Exception as e:
        print_error(f"Stats error: {str(e)}")
        return False

def print_summary():
    """Print test summary"""
    print_section("TEST SUMMARY")
    print_info("Created test data:")
    print(f"  User Email: {TEST_EMAIL}")
    print(f"  User ID: {test_data['user_id']}")
    print(f"  Organization ID: {test_data['organization_id']}")
    print(f"  Location ID: {test_data['location_id']}")
    print(f"  Category ID: {test_data['category_id']}")
    print(f"  Item ID: {test_data['item_id']}")
    print(f"  Booking ID: {test_data['booking_id']}")
    print(f"\n{Colors.OKGREEN}Access Token (for frontend testing):{Colors.ENDC}")
    print(f"{test_data['access_token']}")

def main():
    """Run all tests"""
    print(f"{Colors.BOLD}{Colors.HEADER}")
    print("="*60)
    print("  AI BUSINESS CHAT PLATFORM - API WORKFLOW TEST")
    print("="*60)
    print(f"{Colors.ENDC}")
    
    tests = [
        ("Health Check", test_health_check),
        ("Authentication", test_authentication),
        ("Current User", test_current_user),
        ("Organizations", test_organizations),
        ("Location", test_location),
        ("Menu Categories", test_menu_categories),
        ("Menu Items", test_menu_items),
        ("Opening Hours", test_opening_hours),
        ("Booking Settings", test_booking_settings),
        ("Bookings", test_bookings),
        ("Booking Stats", test_booking_stats),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
                print_error(f"{name} test failed - stopping here")
                break
        except Exception as e:
            failed += 1
            print_error(f"{name} test crashed: {str(e)}")
            break
    
    print_section("RESULTS")
    print(f"Passed: {Colors.OKGREEN}{passed}{Colors.ENDC}")
    print(f"Failed: {Colors.FAIL}{failed}{Colors.ENDC}")
    
    if failed == 0:
        print_summary()
        print(f"\n{Colors.OKGREEN}{Colors.BOLD}ALL TESTS PASSED!{Colors.ENDC}")
    else:
        print(f"\n{Colors.FAIL}{Colors.BOLD}SOME TESTS FAILED!{Colors.ENDC}")

if __name__ == "__main__":
    main()
