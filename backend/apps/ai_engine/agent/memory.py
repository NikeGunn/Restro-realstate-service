"""
Persistent agent memory: the owner's playbook + per-customer facts.
"""
import logging
from pathlib import Path
from typing import Optional

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.ai_engine.models import AgentMemory

logger = logging.getLogger(__name__)

MAX_FACT_CHARS = 240


def customer_key(conversation) -> str:
    """Stable identity for a customer across conversations."""
    phone = (conversation.customer_phone or '').strip()
    if phone:
        return ''.join(ch for ch in phone if ch.isdigit()) or phone
    email = (conversation.customer_email or '').strip().lower()
    if email:
        return email
    return f"conv:{conversation.id}"


def _get(organization, subject_type: str, key: str) -> Optional[AgentMemory]:
    return AgentMemory.objects.filter(
        organization=organization, subject_type=subject_type, subject_key=key,
    ).first()


def render_facts(memory: Optional[AgentMemory], empty: str) -> str:
    if not memory or not memory.facts:
        return empty
    lines = []
    if memory.display_name:
        lines.append(f"- Name: {memory.display_name}")
    for item in memory.facts[-AgentMemory.MAX_FACTS:]:
        fact = item.get('fact') if isinstance(item, dict) else str(item)
        if fact:
            lines.append(f"- {fact}")
    return "\n".join(lines) or empty


def owner_memory_text(organization) -> str:
    return render_facts(
        _get(organization, AgentMemory.SubjectType.OWNER, AgentMemory.OWNER_KEY),
        "(no special instructions from the owner)",
    )


def customer_memory_text(conversation) -> str:
    mem = _get(conversation.organization, AgentMemory.SubjectType.CUSTOMER, customer_key(conversation))
    facts = render_facts(mem, "(first conversation — nothing remembered yet)")
    if mem and mem.summary:
        until = f"{mem.summarized_until:%Y-%m-%d %H:%M} UTC" if mem.summarized_until else "latest"
        return (f"Key facts:\n{facts}\n\n"
                f"History summary (covers all chats up to {until}):\n{mem.summary[-SUMMARY_PROMPT_CHARS:]}")
    return facts


def remember(organization, subject_type: str, key: str, fact: str,
             display_name: str = '', source: str = 'agent') -> AgentMemory:
    """Append a fact (deduplicated, bounded). Safe under concurrent writers."""
    fact = (fact or '').strip()[:MAX_FACT_CHARS]
    if not fact:
        raise ValueError("fact is empty")
    with transaction.atomic():
        try:
            with transaction.atomic():  # savepoint: a lost create race must not poison the outer txn
                mem, _ = AgentMemory.objects.select_for_update().get_or_create(
                    organization=organization, subject_type=subject_type, subject_key=key,
                )
        except IntegrityError:
            mem = AgentMemory.objects.select_for_update().get(
                organization=organization, subject_type=subject_type, subject_key=key,
            )
        existing = {
            (f.get('fact') if isinstance(f, dict) else str(f)).strip().lower()
            for f in mem.facts
        }
        if fact.lower() not in existing:
            mem.facts = (mem.facts + [{
                'fact': fact, 'at': timezone.now().isoformat(), 'source': source,
            }])[-AgentMemory.MAX_FACTS:]
        if display_name and not mem.display_name:
            mem.display_name = display_name[:255]
        mem.save()
    return mem


# ----------------------------------------------------------------------------
# Rolling summaries: nothing a customer said is ever lost. Raw messages stay in
# messaging.Message forever; this folds them into the always-in-prompt summary.
# ----------------------------------------------------------------------------
SUMMARY_INPUT_CHARS = 30000   # one summarizer call never gets a runaway transcript
SUMMARY_PROMPT_CHARS = 3500   # what the agent prompt shows of the summary
SUMMARY_PROMPT = (Path(__file__).resolve().parent / 'prompts' / 'summarize.md')


def _conversations_for_key(organization, key: str):
    from apps.messaging.models import Conversation

    qs = Conversation.objects.filter(organization=organization)
    if key.startswith('conv:'):
        return qs.filter(id=key[5:])
    if '@' in key:
        return qs.filter(customer_email__iexact=key)
    return qs.filter(customer_phone__endswith=key[-8:])  # tolerate +852 / 852 / local formats


def summarize_customer(organization, key: str, client=None) -> Optional[AgentMemory]:
    """Fold every message since the last summary into the customer's memory."""
    from django.conf import settings
    from apps.messaging.models import Message, MessageSender

    mem = _get(organization, AgentMemory.SubjectType.CUSTOMER, key)
    since = mem.summarized_until if mem else None
    # Archived chats belong to a closed chapter (e.g. the org's restaurant days, or a portfolio that was
    # wiped): folding them in poisoned prod memory with "restaurant booking" and Hong Kong listings.
    convs = _conversations_for_key(organization, key).exclude(state='archived')
    msgs = Message.objects.filter(conversation__in=convs)
    if since:
        msgs = msgs.filter(created_at__gt=since)
    msgs = list(msgs.order_by('created_at')[:400])
    if not msgs:
        return mem
    lines, used, kept = [], 0, []
    for m in msgs:
        who = 'Customer' if m.sender == MessageSender.CUSTOMER else 'Agency'
        line = f"[{m.created_at:%Y-%m-%d %H:%M}] {who}: {(m.content or '')[:1000]}"
        if used + len(line) > SUMMARY_INPUT_CHARS and kept:
            break  # the rest is folded in by the next run (summarized_until only moves this far)
        used += len(line)
        lines.append(line)
        kept.append(m)
    msgs = kept
    period = f"{msgs[0].created_at:%Y-%m-%d} to {msgs[-1].created_at:%Y-%m-%d}"
    prompt = SUMMARY_PROMPT.read_text(encoding='utf-8').format(
        existing=(mem.summary if mem and mem.summary else '(none)'),
        period=period, transcript="\n".join(lines),
    )
    if client is None:
        from apps.ai_engine.llm import chat_client
        client = chat_client()
    resp = client.chat.completions.create(
        model=settings.OPENAI_MODEL, temperature=0.1, max_tokens=700,
        messages=[{'role': 'user', 'content': prompt}],
    )
    summary = (resp.choices[0].message.content or '').strip()
    if not summary:
        raise RuntimeError("summarizer returned empty text")
    with transaction.atomic():
        mem, _ = AgentMemory.objects.select_for_update().get_or_create(
            organization=organization, subject_type=AgentMemory.SubjectType.CUSTOMER, subject_key=key,
        )
        mem.summary = summary
        mem.summarized_until = msgs[-1].created_at
        mem.save(update_fields=['summary', 'summarized_until', 'updated_at'])
    return mem
