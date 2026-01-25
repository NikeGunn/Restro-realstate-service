import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.utils import timezone
from apps.accounts.models import Organization
from apps.channels.models import WhatsAppConfig, ManagerNumber, TemporaryOverride
from apps.messaging.models import Conversation, ConversationState, Channel
from apps.channels.manager_service import ManagerService
from apps.ai_engine.services import AIService

# Get the correct organization (Nikhil Test Restro with WhatsApp)
org = Organization.objects.get(name="Nikhil Test Restro")
print(f"Organization: {org.name}")
print(f"ID: {org.id}")

# Check WhatsApp config
wa_config = WhatsAppConfig.objects.get(organization=org)
print(f"\nWhatsApp Config:")
print(f"  Phone ID: {wa_config.phone_number_id}")
print(f"  Active: {wa_config.is_active}")
print(f"  Token: {'SET' if wa_config.access_token else 'NOT SET'}")

# Check manager
managers = ManagerNumber.objects.filter(organization=org)
print(f"\nManagers ({managers.count()}):")
for m in managers:
    print(f"  - {m.name}: {m.phone_number} (Active: {m.is_active})")
    print(f"    Can Update Hours: {m.can_update_hours}")
    print(f"    Last Message: {m.last_message_at}")

# Check existing overrides
overrides = TemporaryOverride.objects.filter(organization=org, is_active=True, expires_at__gt=timezone.now())
print(f"\nActive Overrides ({overrides.count()}):")
for o in overrides:
    print(f"  - Type: {o.override_type}")
    print(f"    Original: {o.original_message}")
    print(f"    Processed: {o.processed_content}")
    print(f"    Keywords: {o.trigger_keywords}")
    print(f"    Expires: {o.expires_at}")

# Test simulating manager message
if managers.exists():
    manager = managers.first()
    print(f"\n{'='*60}")
    print(f"SIMULATING MANAGER MESSAGE: 'we are closed today'")
    print('='*60)
    
    service = ManagerService(org)
    result = service.process_manager_message(manager, "we are closed today")
    
    print(f"Response: {result.get('response_text', 'N/A')}")
    print(f"Actions: {result.get('actions_taken', [])}")
    
    # Check override was created
    new_overrides = TemporaryOverride.objects.filter(
        organization=org,
        is_active=True,
        expires_at__gt=timezone.now()
    ).order_by('-created_at')
    
    print(f"\nOverrides after simulation ({new_overrides.count()}):")
    for o in new_overrides:
        print(f"  - {o.override_type}: {o.processed_content}")
        print(f"    Keywords: {o.trigger_keywords}")
    
    # Test AI response
    print(f"\n{'='*60}")
    print("TESTING AI RESPONSE TO: 'are you open today?'")
    print('='*60)
    
    # Create test conversation
    test_conv = Conversation.objects.create(
        organization=org,
        channel=Channel.WHATSAPP,
        customer_name="Test",
        customer_phone="0000000000",
        state=ConversationState.NEW
    )
    
    ai_service = AIService(test_conv)
    
    # Check override context
    override_context = ai_service._get_temporary_override_context()
    print(f"Override Context in AI:")
    print(f"  '{override_context}'")
    
    # Get AI response
    response = ai_service.process_message("are you open today?")
    print(f"\nAI Response:")
    print(f"  Content: {response.get('content', 'N/A')}")
    print(f"  Confidence: {response.get('confidence', 0)}")
    
    # Cleanup
    test_conv.delete()
    
    # Check if override content appears
    if override_context:
        print("\n✅ Override IS being loaded into AI context")
        if 'closed' in response.get('content', '').lower():
            print("✅ AI response mentions 'closed' - WORKING!")
        else:
            print("⚠️ AI response doesn't mention 'closed' - AI might be ignoring override")
            print("   Check if keywords match: 'hours', 'open', 'closed', etc.")
    else:
        print("\n❌ No override context - the override was not loaded into AI!")
