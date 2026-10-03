"""
Owner-editable AI agent playbook: standing instructions the customer-facing agent must
follow (tone, policies, what to push). Stored in AgentMemory(owner) — the same row the
agent reads every turn — so an edit in the dashboard changes behaviour on the next message.
"""
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import user_role_in_org

from .agent.memory import MAX_FACT_CHARS
from .models import AgentMemory

MAX_INSTRUCTIONS = 30


class AgentPlaybookView(APIView):
    permission_classes = [IsAuthenticated]

    def _org_and_role(self, request):
        org_id = request.query_params.get('organization') or request.data.get('organization')
        try:
            role = user_role_in_org(request.user, org_id)
        except Exception:  # malformed UUID
            role = None
        return org_id, role

    def get(self, request):
        org_id, role = self._org_and_role(request)
        if not role:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        mem = AgentMemory.objects.filter(organization_id=org_id, subject_type=AgentMemory.SubjectType.OWNER,
                                         subject_key=AgentMemory.OWNER_KEY).first()
        facts = [f.get('fact') if isinstance(f, dict) else str(f) for f in (mem.facts if mem else [])]
        return Response({'instructions': [f for f in facts if f], 'can_edit': role == 'owner',
                         'updated_at': mem.updated_at if mem else None})

    def put(self, request):
        org_id, role = self._org_and_role(request)
        if not role:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if role != 'owner':
            return Response({'detail': 'Only the owner can change the AI playbook.'}, status=status.HTTP_403_FORBIDDEN)
        raw = request.data.get('instructions')
        if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
            return Response({'instructions': ['Send a list of text instructions.']}, status=status.HTTP_400_BAD_REQUEST)
        cleaned, seen = [], set()
        for text in raw:
            text = ' '.join(text.split())
            if text and text.lower() not in seen:
                seen.add(text.lower())
                cleaned.append(text)
        if any(len(t) > MAX_FACT_CHARS for t in cleaned):
            return Response({'instructions': [f'Each instruction must be at most {MAX_FACT_CHARS} characters.']},
                            status=status.HTTP_400_BAD_REQUEST)
        if len(cleaned) > MAX_INSTRUCTIONS:
            return Response({'instructions': [f'At most {MAX_INSTRUCTIONS} instructions.']},
                            status=status.HTTP_400_BAD_REQUEST)
        now = timezone.now().isoformat()
        with transaction.atomic():
            mem, _ = AgentMemory.objects.select_for_update().get_or_create(
                organization_id=org_id, subject_type=AgentMemory.SubjectType.OWNER, subject_key=AgentMemory.OWNER_KEY,
                defaults={'display_name': 'Owner'},
            )
            mem.facts = [{'fact': t, 'at': now, 'source': 'owner'} for t in cleaned]
            mem.save(update_fields=['facts', 'updated_at'])
        return Response({'instructions': cleaned, 'can_edit': True, 'updated_at': mem.updated_at})
