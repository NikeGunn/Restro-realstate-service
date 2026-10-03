import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Organization, OrganizationMembership, User
from apps.ai_engine.agent import memory as agent_memory
from apps.ai_engine.models import AgentMemory
from apps.messaging.models import Channel, Conversation

pytestmark = pytest.mark.django_db
URL = '/api/v1/ai/playbook/'


@pytest.fixture
def org():
    return Organization.objects.create(name='Agency', business_type='real_estate')


def _client(org, role):
    u = User.objects.create_user(username=role, email=f'{role}@x.com', password='pw-12345678')
    if role != 'outsider':
        OrganizationMembership.objects.create(user=u, organization=org, role=role)
    c = APIClient()
    c.force_authenticate(u)
    return c


def test_owner_edits_playbook_and_agent_reads_it(org):
    c = _client(org, 'owner')
    r = c.put(URL, {'organization': str(org.id), 'instructions': ['  Always offer two viewing slots ', 'Never discount rent',
                                                                  'never discount rent', '']}, format='json')
    assert r.status_code == 200
    assert r.data['instructions'] == ['Always offer two viewing slots', 'Never discount rent']
    assert c.get(URL, {'organization': str(org.id)}).data['instructions'] == r.data['instructions']
    assert 'Never discount rent' in agent_memory.owner_memory_text(org)


def test_manager_reads_but_cannot_edit(org):
    AgentMemory.objects.create(organization=org, subject_type='owner', subject_key='owner',
                               facts=[{'fact': 'Be warm', 'source': 'owner'}])
    c = _client(org, 'manager')
    r = c.get(URL, {'organization': str(org.id)})
    assert r.data == {**r.data, 'instructions': ['Be warm'], 'can_edit': False}
    assert c.put(URL, {'organization': str(org.id), 'instructions': ['x']}, format='json').status_code == 403


def test_outsider_and_bad_input(org):
    assert _client(org, 'outsider').get(URL, {'organization': str(org.id)}).status_code == 404
    owner = _client(org, 'owner')
    assert owner.get(URL, {'organization': 'not-a-uuid'}).status_code == 404
    assert owner.put(URL, {'organization': str(org.id), 'instructions': 'text'}, format='json').status_code == 400
    assert owner.put(URL, {'organization': str(org.id), 'instructions': ['x' * 500]}, format='json').status_code == 400


def test_customer_memories_untouched(org):
    Conversation.objects.create(organization=org, channel=Channel.WHATSAPP, customer_phone='9779800000000')
    AgentMemory.objects.create(organization=org, subject_type='customer', subject_key='9779800000000')
    _client(org, 'owner').put(URL, {'organization': str(org.id), 'instructions': ['Hi']}, format='json')
    assert AgentMemory.objects.filter(organization=org, subject_type='customer').count() == 1
