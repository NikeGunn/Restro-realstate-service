import requests
import sys
from datetime import datetime

BASE_URL = "http://localhost:8000/api"

# Register new user
timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
user_data = {
    "email": f"realtor_{timestamp}@example.com",
    "username": f"realtor_{timestamp}",
    "first_name": "Real",
    "last_name": "Estate",
    "password": "testpass123",
    "password_confirm": "testpass123"
}

print("Registering user...")
r = requests.post(f"{BASE_URL}/auth/register/", json=user_data)
if r.status_code != 201:
    print(f"Registration failed: {r.status_code} - {r.text}")
    sys.exit(1)

print(f"✅ User registered: {user_data['email']}")

# Login
login_data = {
    "email": user_data['email'],
    "password": "testpass123"
}

r = requests.post(f"{BASE_URL}/auth/login/", json=login_data)
if r.status_code != 200:
    print(f"Login failed: {r.status_code} - {r.text}")
    sys.exit(1)

token = r.json()['access']
headers = {"Authorization": f"Bearer {token}"}
print("✅ Logged in")

# Create real estate organization
org_data = {
    "name": "Sunset Realty",
    "business_type": "real_estate"
}

print("\nCreating real estate organization...")
r = requests.post(f"{BASE_URL}/organizations/", json=org_data, headers=headers)
if r.status_code != 201:
    print(f"Org creation failed: {r.status_code} - {r.text}")
    sys.exit(1)

org = r.json()
print(f"✅ Organization created: {org['name']}")
print(f"   ID: {org['id']}")
print(f"   Type: {org['business_type']}")

# Create a property listing
print("\nCreating sample property...")
property_data = {
    "organization": org['id'],
    "title": "Beautiful 3BR Family Home",
    "description": "Spacious home with modern amenities in great neighborhood",
    "listing_type": "sale",
    "property_type": "house",
    "price": "450000",
    "bedrooms": 3,
    "bathrooms": "2.5",
    "square_feet": 2100,
    "address_line1": "123 Main Street",
    "city": "Springfield",
    "state": "IL",
    "postal_code": "62701",
    "status": "active",
    "is_featured": True
}

r = requests.post(f"{BASE_URL}/realestate/properties/", json=property_data, headers=headers)
if r.status_code == 201:
    prop = r.json()
    print(f"✅ Property created: {prop['title']}")
    print(f"   ID: {prop['id']}")
    print(f"   Price: ${prop['price']}")
else:
    print(f"Property creation failed: {r.status_code} - {r.text[:200]}")

# Create a lead
print("\nCreating sample lead...")
lead_data = {
    "organization": org['id'],
    "name": "Jane Smith",
    "email": "jane.smith@example.com",
    "phone": "(555) 123-4567",
    "intent": "buy",
    "budget_min": 300000,
    "budget_max": 500000,
    "bedrooms_min": 2,
    "bedrooms_max": 4,
    "preferred_areas": ["Downtown", "Suburbs"],
    "notes": "Looking for move-in ready home",
    "source": "website"
}

r = requests.post(f"{BASE_URL}/realestate/leads/", json=lead_data, headers=headers)
if r.status_code == 201:
    lead = r.json()
    print(f"✅ Lead created: {lead['name']}")
    print(f"   ID: {lead['id']}")
    print(f"   Email: {lead['email']}")
else:
    print(f"Lead creation failed: {r.status_code} - {r.text[:200]}")

print("\n" + "="*60)
print("REAL ESTATE TEST DATA CREATED!")
print("="*60)
print(f"\nLogin Credentials for Frontend:")
print(f"  Email: {user_data['email']}")
print(f"  Password: testpass123")
print(f"\nOrganization ID: {org['id']}")
