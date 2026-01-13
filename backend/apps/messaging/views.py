"""
Messaging views for unified inbox.
"""
import logging
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Q

from .models import Conversation, Message, ConversationState, MessageSender, Channel
from .serializers import (
    ConversationSerializer,
    ConversationDetailSerializer,
    ConversationUpdateSerializer,
    MessageSerializer,
    MessageCreateSerializer,
)
from apps.accounts.models import OrganizationMembership

logger = logging.getLogger(__name__)


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
        
        # Create a handoff alert for this conversation
        from apps.handoff.services import create_alert_for_manual_handoff
        create_alert_for_manual_handoff(conversation, locked_by_user=request.user)
        
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
        """Create a human message in the conversation and send it to the channel."""
        conversation_id = self.kwargs.get('conversation_pk')
        conversation = Conversation.objects.get(pk=conversation_id)

        # Create message from human agent
        message = serializer.save(
            conversation=conversation,
            sender=MessageSender.HUMAN,
            sent_by=self.request.user
        )

        # Update conversation state
        if conversation.state != ConversationState.HUMAN_HANDOFF:
            conversation.lock(self.request.user)
        
        # Send message to the appropriate channel
        self._send_to_channel(conversation, message)
    
    def _send_to_channel(self, conversation: Conversation, message: Message):
        """Send the human agent's message to the customer via the appropriate channel."""
        try:
            if conversation.channel == Channel.WHATSAPP:
                self._send_whatsapp_message(conversation, message)
            elif conversation.channel == Channel.INSTAGRAM:
                self._send_instagram_message(conversation, message)
            # Website widget messages are shown in real-time via polling, no push needed
        except Exception as e:
            logger.exception(f"Failed to send message to channel {conversation.channel}: {e}")
    
    def _send_whatsapp_message(self, conversation: Conversation, message: Message):
        """Send message via WhatsApp."""
        from apps.channels.whatsapp_service import WhatsAppService
        
        if not conversation.customer_phone:
            logger.warning(f"No phone number for conversation {conversation.id}, cannot send WhatsApp message")
            return
        
        whatsapp_service = WhatsAppService.get_for_organization(conversation.organization)
        if not whatsapp_service:
            logger.warning(f"WhatsApp not configured for organization {conversation.organization.name}")
            return
        
        # Send the message
        sent_message_id = whatsapp_service.send_message(
            to=conversation.customer_phone,
            text=message.content
        )
        
        if sent_message_id:
            # Update message with channel message ID
            message.channel_message_id = sent_message_id
            message.save(update_fields=['channel_message_id'])
            logger.info(f"✅ Human agent message sent to WhatsApp: {sent_message_id}")
        else:
            logger.error(f"❌ Failed to send human agent message to WhatsApp for conversation {conversation.id}")
    
    def _send_instagram_message(self, conversation: Conversation, message: Message):
        """Send message via Instagram."""
        from apps.channels.instagram_service import InstagramService
        
        # Instagram uses channel_conversation_id to identify the thread
        if not conversation.channel_conversation_id:
            logger.warning(f"No Instagram thread ID for conversation {conversation.id}")
            return
        
        instagram_service = InstagramService.get_for_organization(conversation.organization)
        if not instagram_service:
            logger.warning(f"Instagram not configured for organization {conversation.organization.name}")
            return
        
        # Send the message
        sent_message_id = instagram_service.send_message(
            recipient_id=conversation.channel_conversation_id,
            text=message.content
        )
        
        if sent_message_id:
            message.channel_message_id = sent_message_id
            message.save(update_fields=['channel_message_id'])
            logger.info(f"✅ Human agent message sent to Instagram: {sent_message_id}")

    @action(detail=False, methods=['post'])
    def mark_read(self, request, conversation_pk=None):
        """Mark all customer messages in conversation as read."""
        Message.objects.filter(
            conversation_id=conversation_pk,
            sender=MessageSender.CUSTOMER,
            is_read=False
        ).update(is_read=True, read_at=timezone.now())
        return Response({'status': 'Messages marked as read.'})
