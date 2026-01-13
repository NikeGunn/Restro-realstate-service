"""
Handoff services for creating and managing alerts.
"""
import logging
from typing import Optional
from .models import HandoffAlert

logger = logging.getLogger(__name__)


def create_handoff_alert(
    conversation,
    alert_type: str = HandoffAlert.AlertType.OTHER,
    priority: str = HandoffAlert.Priority.MEDIUM,
    reason: str = "",
    trigger_message: str = ""
) -> Optional[HandoffAlert]:
    """
    Create a handoff alert for a conversation.
    
    Args:
        conversation: The conversation requiring handoff
        alert_type: Type of alert (low_confidence, escalation_request, etc.)
        priority: Priority level (low, medium, high, urgent)
        reason: Reason for the handoff
        trigger_message: The message that triggered the handoff
    
    Returns:
        HandoffAlert instance or None if creation failed
    """
    try:
        # Check if there's already an unresolved alert for this conversation
        existing_alert = HandoffAlert.objects.filter(
            conversation=conversation,
            is_resolved=False
        ).first()
        
        if existing_alert:
            logger.info(f"Alert already exists for conversation {conversation.id}")
            # Update priority if new one is higher
            priority_order = ['low', 'medium', 'high', 'urgent']
            if priority_order.index(priority) > priority_order.index(existing_alert.priority):
                existing_alert.priority = priority
                existing_alert.save(update_fields=['priority'])
                logger.info(f"Updated alert priority to {priority}")
            return existing_alert
        
        # Construct the reason message
        full_reason = reason
        if trigger_message:
            full_reason = f"{reason}\n\nTriggering message: \"{trigger_message[:200]}...\""
        
        alert = HandoffAlert.objects.create(
            conversation=conversation,
            alert_type=alert_type,
            priority=priority,
            reason=full_reason or f"Conversation requires human attention ({alert_type})"
        )
        
        logger.info(f"🚨 Created handoff alert for conversation {conversation.id}: {alert_type} - {priority}")
        return alert
        
    except Exception as e:
        logger.exception(f"Failed to create handoff alert: {e}")
        return None


def create_alert_from_ai_response(conversation, ai_response: dict, user_message: str = "") -> Optional[HandoffAlert]:
    """
    Create a handoff alert based on AI response.
    
    Args:
        conversation: The conversation
        ai_response: Response dict from AI service with needs_handoff, handoff_reason, confidence
        user_message: The user's message that triggered the handoff
    
    Returns:
        HandoffAlert instance or None
    """
    if not ai_response.get('needs_handoff', False):
        return None
    
    handoff_reason = ai_response.get('handoff_reason', 'unknown')
    confidence = ai_response.get('confidence', 0)
    intent = ai_response.get('intent', 'unknown')
    
    # Determine alert type based on handoff reason
    alert_type_map = {
        'low_confidence': HandoffAlert.AlertType.LOW_CONFIDENCE,
        'ai_requested': HandoffAlert.AlertType.ESCALATION_REQUEST,
        'ai_error': HandoffAlert.AlertType.OTHER,
        'no_api_key': HandoffAlert.AlertType.OTHER,
        'explicit_request': HandoffAlert.AlertType.ESCALATION_REQUEST,
        'complaint': HandoffAlert.AlertType.COMPLAINT,
    }
    
    alert_type = alert_type_map.get(handoff_reason, HandoffAlert.AlertType.OTHER)
    
    # Determine priority based on confidence and intent
    if confidence < 0.3 or handoff_reason in ['ai_error', 'complaint']:
        priority = HandoffAlert.Priority.HIGH
    elif confidence < 0.5:
        priority = HandoffAlert.Priority.MEDIUM
    elif intent in ['booking', 'lead_capture', 'complaint']:
        priority = HandoffAlert.Priority.HIGH
    else:
        priority = HandoffAlert.Priority.MEDIUM
    
    # Build reason message
    reason_parts = [f"AI flagged for handoff: {handoff_reason}"]
    if confidence < 0.7:
        reason_parts.append(f"Low confidence score: {confidence:.1%}")
    if intent:
        reason_parts.append(f"Intent detected: {intent}")
    
    reason = ". ".join(reason_parts)
    
    return create_handoff_alert(
        conversation=conversation,
        alert_type=alert_type,
        priority=priority,
        reason=reason,
        trigger_message=user_message
    )


def create_alert_for_manual_handoff(conversation, locked_by_user=None) -> Optional[HandoffAlert]:
    """
    Create an alert when a conversation is manually locked by a human agent.
    
    Args:
        conversation: The conversation being locked
        locked_by_user: The user who locked the conversation
    
    Returns:
        HandoffAlert instance or None
    """
    reason = "Conversation manually taken over by human agent"
    if locked_by_user:
        user_name = f"{locked_by_user.first_name} {locked_by_user.last_name}".strip() or locked_by_user.email
        reason = f"Conversation manually taken over by {user_name}"
    
    # Get the last customer message as trigger
    from apps.messaging.models import MessageSender
    last_customer_msg = conversation.messages.filter(
        sender=MessageSender.CUSTOMER
    ).order_by('-created_at').first()
    
    trigger_message = last_customer_msg.content if last_customer_msg else ""
    
    return create_handoff_alert(
        conversation=conversation,
        alert_type=HandoffAlert.AlertType.ESCALATION_REQUEST,
        priority=HandoffAlert.Priority.MEDIUM,
        reason=reason,
        trigger_message=trigger_message
    )
