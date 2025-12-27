"""
Messaging views for unified inbox.
"""
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Q

from .models import Conversation, Message, ConversationState, MessageSender
from .serializers import (
    ConversationSerializer,
    ConversationDetailSerializer,
    ConversationUpdateSerializer,
    MessageSerializer,
    MessageCreateSerializer,
)
from apps.accounts.models import OrganizationMembership


class ConversationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing conversations (Unified Inbox).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Return conversations for user's organizations."""
        user = self.request.user
        org_ids = OrganizationMembership.objects.filter(
            user=user
        ).values_list('organization_id', flat=True)

        queryset = Conversation.objects.filter(organization_id__in=org_ids)

        # Filter by organization
        org_id = self.request.query_params.get('organization')
        if org_id:
            queryset = queryset.filter(organization_id=org_id)

        # Filter by location
        location_id = self.request.query_params.get('location')
        if location_id:
            queryset = queryset.filter(location_id=location_id)

        # Filter by state
        state = self.request.query_params.get('state')
        if state:
            queryset = queryset.filter(state=state)

        # Filter by channel
        channel = self.request.query_params.get('channel')
        if channel:
            queryset = queryset.filter(channel=channel)

        # Filter by assignment
        assigned = self.request.query_params.get('assigned')
        if assigned == 'me':
            queryset = queryset.filter(assigned_to=user)
        elif assigned == 'unassigned':
            queryset = queryset.filter(assigned_to__isnull=True)

        # Search
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(customer_name__icontains=search) |
                Q(customer_email__icontains=search) |
                Q(customer_phone__icontains=search)
            )

        return queryset.select_related('organization', 'location', 'assigned_to')

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ConversationDetailSerializer
        if self.action in ['update', 'partial_update']:
            return ConversationUpdateSerializer
        return ConversationSerializer

    @action(detail=True, methods=['post'])
    def lock(self, request, pk=None):
        """Lock conversation for human handling."""
        conversation = self.get_object()
        if conversation.is_locked and conversation.locked_by != request.user:
            return Response(
                {'error': 'Conversation is already locked by another agent.'},
                status=status.HTTP_409_CONFLICT
            )
        conversation.lock(request.user)
        return Response(ConversationDetailSerializer(conversation).data)

    @action(detail=True, methods=['post'])
    def unlock(self, request, pk=None):
        """Unlock conversation, return to AI handling."""
        conversation = self.get_object()
        if conversation.locked_by and conversation.locked_by != request.user:
            # Only owner or the locker can unlock
            membership = OrganizationMembership.objects.filter(
                user=request.user,
                organization=conversation.organization,
                role=OrganizationMembership.Role.OWNER
            ).exists()
            if not membership:
                return Response(
                    {'error': 'Only the locking agent or an owner can unlock.'},
                    status=status.HTTP_403_FORBIDDEN
                )
        conversation.unlock()
        conversation.transition_state(ConversationState.AI_HANDLING)
        return Response(ConversationDetailSerializer(conversation).data)

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """Mark conversation as resolved."""
        conversation = self.get_object()
        conversation.transition_state(ConversationState.RESOLVED)
        return Response(ConversationDetailSerializer(conversation).data)

    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        """Assign conversation to an agent."""
        conversation = self.get_object()
        user_id = request.data.get('user_id')

        if user_id:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                agent = User.objects.get(pk=user_id)
                # Verify agent is member of the org
                if not OrganizationMembership.objects.filter(
                    user=agent,
                    organization=conversation.organization
                ).exists():
                    return Response(
                        {'error': 'User is not a member of this organization.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                conversation.assigned_to = agent
            except User.DoesNotExist:
                return Response(
                    {'error': 'User not found.'},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            conversation.assigned_to = None

        conversation.save(update_fields=['assigned_to', 'updated_at'])
        return Response(ConversationDetailSerializer(conversation).data)


class MessageViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing messages within a conversation.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        conversation_id = self.kwargs.get('conversation_pk')
        return Message.objects.filter(conversation_id=conversation_id)

    def get_serializer_class(self):
        if self.action == 'create':
            return MessageCreateSerializer
        return MessageSerializer

    def perform_create(self, serializer):
        """Create a human message in the conversation."""
        conversation_id = self.kwargs.get('conversation_pk')
        conversation = Conversation.objects.get(pk=conversation_id)

        # Create message from human agent
        serializer.save(
            conversation=conversation,
            sender=MessageSender.HUMAN,
            sent_by=self.request.user
        )

        # Update conversation state
        if conversation.state != ConversationState.HUMAN_HANDOFF:
            conversation.lock(self.request.user)

    @action(detail=False, methods=['post'])
    def mark_read(self, request, conversation_pk=None):
        """Mark all customer messages in conversation as read."""
        Message.objects.filter(
            conversation_id=conversation_pk,
            sender=MessageSender.CUSTOMER,
            is_read=False
        ).update(is_read=True, read_at=timezone.now())
        return Response({'status': 'Messages marked as read.'})
