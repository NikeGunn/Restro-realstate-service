"""
Quoted replies ("long-press → Reply" on WhatsApp, swipe-reply on Instagram).

The channel only sends the id of the message being answered. We resolve it to the stored message
(our text replies, the listing photos we sent, staff messages, reminders, or the customer's own
earlier message) so the agent reads "yes, this one" against the message the customer pointed at,
not against whatever was said last.
"""
from typing import Any, Dict, Optional

QUOTE_CHARS = 500


def resolve(conversation, external_id: str) -> Optional[Dict[str, Any]]:
    from .models import Message, MessageSender

    external_id = (external_id or '').strip()
    if not external_id or conversation is None:
        return None
    msgs = Message.objects.filter(conversation=conversation)
    m = msgs.filter(channel_message_id=external_id).first()
    photo_caption = ''
    if m is None:
        # A listing photo we sent: its id is stored on the AI text message that carried it.
        m = msgs.filter(ai_metadata__attachment_ids__has_key=external_id).first()
        if m is not None:
            photo_caption = (m.ai_metadata.get('attachment_ids') or {}).get(external_id, '')
    if m is None:
        return {'id': external_id, 'found': False}
    who = {MessageSender.CUSTOMER: 'customer', MessageSender.AI: 'assistant',
           MessageSender.HUMAN: 'staff', MessageSender.SYSTEM: 'automatic notice'}.get(m.sender, m.sender)
    return {
        'id': external_id, 'found': True, 'message': str(m.id), 'sender': who,
        'at': m.created_at.isoformat(),
        'kind': 'photo' if photo_caption else 'text',
        'content': (f"[photo: {photo_caption}]" if photo_caption else (m.content or ''))[:QUOTE_CHARS],
    }
