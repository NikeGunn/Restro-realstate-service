"""
Seed a Nepal demo portfolio (rooms, flats, houses, land, shops) priced in NPR.

    python manage.py seed_nepal_portfolio --org "Kribaat Realestate"            # add / refresh listings
    python manage.py seed_nepal_portfolio --org "Kribaat Realestate" --wipe     # demo reset (see below)

--wipe is a DEMO reset for one org: deletes its listings, leads and appointments, clears
customer agent-memory (owner playbook is kept), and archives open conversations so the
next WhatsApp message starts a clean chat. It never touches other organizations.
Prices are plain NPR numbers; the dashboard and agent format them as Rs + lakh/crore.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

AANA_SQFT = 342.25
KATTHA_SQFT = 3645

# (title, property_type, listing_type, price NPR, city, neighborhood, state, extra)
LISTINGS = [
    # ---- Rooms for rent
    ('Single Room near Tribhuvan University, Kirtipur', 'room', 'rent', 6000, 'Kirtipur', 'Kirtipur', 'Bagmati',
     dict(features=['Students welcome', 'Common bathroom', '24h water (boring)', 'Bike parking', '5 min walk to TU gate'])),
    ('Room with Balcony near Chabahil Chowk', 'room', 'rent', 8000, 'Kathmandu', 'Chabahil', 'Bagmati',
     dict(features=['Bachelor allowed', 'Balcony', 'Common bathroom', 'Near bus stop'])),
    ('Room near Balaju Bypass', 'room', 'rent', 7000, 'Kathmandu', 'Balaju', 'Bagmati',
     dict(features=['Bachelor allowed', 'Melamchi water', 'Common bathroom'])),
    ('Room + Kitchen in Koteshwor', 'room', 'rent', 9500, 'Kathmandu', 'Koteshwor', 'Bagmati',
     dict(features=['Room + kitchen', 'Couple / small family', 'Attached bathroom', 'Bike parking'])),
    ('Furnished Single Room with Wifi, New Baneshwor', 'room', 'rent', 12000, 'Kathmandu', 'New Baneshwor', 'Bagmati',
     dict(features=['Furnished (bed, table, wardrobe)', 'Wifi included', 'Attached bathroom', 'Bachelor allowed'])),
    ('2 Rooms + Kitchen for Small Family, Kalanki', 'room', 'rent', 15000, 'Kathmandu', 'Kalanki', 'Bagmati',
     dict(features=['2 rooms + kitchen', 'Family only', 'Attached bathroom', 'Car parking'])),
    ('Lakeside Studio Room, Pokhara', 'room', 'rent', 18000, 'Pokhara', 'Lakeside', 'Gandaki',
     dict(features=['Studio with kitchenette', 'Lake view', 'Furnished', 'Wifi included'])),
    ('Room near Butwal Buspark', 'room', 'rent', 5500, 'Butwal', 'Traffic Chowk', 'Lumbini',
     dict(features=['Bachelor allowed', 'Common bathroom', 'Near buspark'])),
    ('Room near BPKIHS, Dharan', 'room', 'rent', 6500, 'Dharan', 'Ghopa', 'Koshi',
     dict(features=['Students welcome', 'Attached bathroom', 'Near BPKIHS'])),
    # ---- Flats for rent
    ('1BHK Flat in Sanepa, Lalitpur', 'apartment', 'rent', 25000, 'Lalitpur', 'Sanepa', 'Bagmati',
     dict(bedrooms=1, bathrooms=1, square_feet=550, features=['1 bedroom + hall + kitchen', 'Semi-furnished', 'Car parking'])),
    ('2BHK Flat near Imadol Chowk, Lalitpur', 'apartment', 'rent', 30000, 'Lalitpur', 'Imadol', 'Bagmati',
     dict(bedrooms=2, bathrooms=2, square_feet=850, features=['2 bedrooms + hall + kitchen', 'Family only', 'Car parking'])),
    ('2BHK Flat, Suryabinayak Bhaktapur', 'apartment', 'rent', 22000, 'Bhaktapur', 'Suryabinayak', 'Bagmati',
     dict(bedrooms=2, bathrooms=1, square_feet=800, features=['2 bedrooms + hall + kitchen', 'Quiet area', 'Bike parking'])),
    ('3BHK Furnished Flat, Maharajgunj', 'apartment', 'rent', 55000, 'Kathmandu', 'Maharajgunj', 'Bagmati',
     dict(bedrooms=3, bathrooms=2, square_feet=1400, features=['Fully furnished', 'Near embassies', 'Lift', 'Car parking'])),
    ('2BHK Flat, Chipledhunga Pokhara', 'apartment', 'rent', 28000, 'Pokhara', 'Chipledhunga', 'Gandaki',
     dict(bedrooms=2, bathrooms=1, square_feet=780, features=['City centre', 'Mountain view', 'Bike parking'])),
    # ---- Land (jagga) for sale
    ('Residential Land 5 Aana, Bhaisepati', 'land', 'sale', 21000000, 'Lalitpur', 'Bhaisepati', 'Bagmati',
     dict(aana=5, features=['Land area: 5 aana', 'Road access: 13 ft blacktopped', 'Lalpurja clear', 'East facing'])),
    ('Plot 8 Aana, Budhanilkantha', 'land', 'sale', 24000000, 'Kathmandu', 'Budhanilkantha', 'Bagmati',
     dict(aana=8, features=['Land area: 8 aana', 'Road access: 16 ft', 'Lalpurja clear', 'Mountain view'])),
    ('Land 4 Aana, Tokha', 'land', 'sale', 12000000, 'Kathmandu', 'Tokha', 'Bagmati',
     dict(aana=4, features=['Land area: 4 aana', 'Road access: 12 ft', 'Lalpurja clear', 'Residential area'])),
    ('Land 6 Aana, Sallaghari Bhaktapur', 'land', 'sale', 15000000, 'Bhaktapur', 'Sallaghari', 'Bagmati',
     dict(aana=6, features=['Land area: 6 aana', 'Road access: 14 ft', 'Lalpurja clear', 'Bank loan possible'])),
    ('Affordable Land 5 Aana, Lubhu Lalitpur', 'land', 'sale', 9000000, 'Lalitpur', 'Lubhu', 'Bagmati',
     dict(aana=5, features=['Land area: 5 aana', 'Road access: 10 ft', 'Lalpurja clear', 'Good for first home'])),
    ('Land 6 Aana near Bagar, Pokhara', 'land', 'sale', 10500000, 'Pokhara', 'Bagar', 'Gandaki',
     dict(aana=6, features=['Land area: 6 aana', 'Road access: 13 ft', 'Lalpurja clear', 'Near Pokhara University road'])),
    ('Land 5 Kattha, Bharatpur Chitwan', 'land', 'sale', 12500000, 'Chitwan', 'Bharatpur', 'Bagmati',
     dict(kattha=5, features=['Land area: 5 kattha', 'Road access: 20 ft', 'Lalpurja clear', 'Flat terrain'])),
    ('Land 4 Kattha, Butwal', 'land', 'sale', 8000000, 'Butwal', 'Kalikanagar', 'Lumbini',
     dict(kattha=4, features=['Land area: 4 kattha', 'Road access: 16 ft', 'Lalpurja clear'])),
    ('Land 3 Kattha, Biratnagar', 'land', 'sale', 6000000, 'Biratnagar', 'Tinpaini', 'Koshi',
     dict(kattha=3, features=['Land area: 3 kattha', 'Road access: 14 ft', 'Lalpurja clear'])),
    # ---- Houses (ghar) for sale
    ('4-Bedroom House on 4 Aana, Budhanilkantha', 'house', 'sale', 38500000, 'Kathmandu', 'Budhanilkantha', 'Bagmati',
     dict(aana=4, bedrooms=4, bathrooms=3, square_feet=2400, parking_spaces=2,
          features=['Land area: 4 aana', '2.5 storey', 'Road access: 16 ft', 'Lalpurja clear'])),
    ('2.5 Storey House on 3 Aana, Imadol', 'house', 'sale', 22500000, 'Lalitpur', 'Imadol', 'Bagmati',
     dict(aana=3, bedrooms=5, bathrooms=3, square_feet=2000, parking_spaces=1,
          features=['Land area: 3 aana', '2.5 storey', 'Road access: 13 ft', 'Rental income possible'])),
    ('House on 5 Aana, Pokhara Hemja', 'house', 'sale', 16000000, 'Pokhara', 'Hemja', 'Gandaki',
     dict(aana=5, bedrooms=3, bathrooms=2, square_feet=1600, parking_spaces=1,
          features=['Land area: 5 aana', 'Annapurna view', 'Garden'])),
    # ---- Shops / offices for rent
    ('Shutter for Shop on Main Road, Bharatpur Chitwan', 'retail', 'rent', 22000, 'Chitwan', 'Bharatpur', 'Bagmati',
     dict(square_feet=250, features=['Main road frontage', 'Good for retail'])),
    ('Shutter on New Road, Kathmandu', 'retail', 'rent', 65000, 'Kathmandu', 'New Road', 'Bagmati',
     dict(square_feet=200, features=['Prime market', 'High footfall'])),
    ('Office Space 1,200 sq ft, Putalisadak', 'office', 'rent', 45000, 'Kathmandu', 'Putalisadak', 'Bagmati',
     dict(square_feet=1200, parking_spaces=2, features=['Open-plan office', 'Lift', 'Backup power'])),
]


class Command(BaseCommand):
    help = 'Seed a Nepal (NPR) demo portfolio for one real-estate organization.'

    def add_arguments(self, parser):
        parser.add_argument('--org', required=True, help='Organization name (exact)')
        parser.add_argument('--wipe', action='store_true', help='Demo reset: delete listings/leads/appointments first')

    @transaction.atomic
    def handle(self, *args, **opts):
        from apps.accounts.models import Location, Organization
        from apps.ai_engine.models import AgentMemory
        from apps.messaging.models import Conversation, ConversationState
        from apps.realestate.models import Appointment, Lead, PropertyListing

        try:
            org = Organization.objects.get(name=opts['org'])
        except Organization.DoesNotExist:
            raise CommandError(f"No organization named {opts['org']!r}")
        location = Location.objects.filter(organization=org, is_active=True).order_by('-is_primary').first()
        if not location or (location.country or '').strip().lower() != 'nepal':
            raise CommandError("The org's primary location must have country 'Nepal' (sets currency + timezone).")

        if opts['wipe']:
            counts = {
                'appointments': Appointment.objects.filter(organization=org).delete()[0],
                'leads': Lead.objects.filter(organization=org).delete()[0],
                'listings': PropertyListing.objects.filter(organization=org).delete()[0],
                'customer memories': AgentMemory.objects.filter(
                    organization=org, subject_type=AgentMemory.SubjectType.CUSTOMER).delete()[0],
                'conversations archived': Conversation.objects.filter(organization=org).exclude(
                    state=ConversationState.ARCHIVED).update(state=ConversationState.ARCHIVED),
            }
            self.stdout.write('Wiped: ' + ', '.join(f'{v} {k}' for k, v in counts.items()))

        created = updated = 0
        for title, ptype, ltype, price, city, hood, state, extra in LISTINGS:
            extra = dict(extra)
            aana, kattha = extra.pop('aana', None), extra.pop('kattha', None)
            lot = round(aana * AANA_SQFT) if aana else (kattha * KATTHA_SQFT if kattha else None)
            features = extra.pop('features', [])
            description = (f"{title}. " + '. '.join(features) + '.'
                           + (' Contact Kribaat to arrange a site visit.' if ltype == 'sale' else ''))
            _, was_created = PropertyListing.objects.update_or_create(
                organization=org, title=title,
                defaults=dict(
                    location=location, description=description, property_type=ptype, listing_type=ltype,
                    price=Decimal(price), rent_period='monthly' if ltype == 'rent' else '',
                    address_line1=f'{hood}, {city}', city=city, neighborhood=hood, state=state,
                    postal_code='', country='Nepal', lot_size=lot, features=features,
                    status=PropertyListing.Status.ACTIVE, is_published=True,
                    is_featured=title.startswith(('Furnished Single Room', 'Residential Land 5 Aana')), **extra,
                ),
            )
            created += was_created
            updated += not was_created
        self.stdout.write(self.style.SUCCESS(f'{created} listings created, {updated} updated for {org.name}.'))
