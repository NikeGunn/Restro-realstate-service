"""
Real-estate agent loop: plan → call tools → observe → answer → verify.

Design (borrowed from HisabKitab / MigAlpha and tool-using agent harnesses):
  * The model never "declares" side-effects in JSON for someone else to maybe
    execute later. It calls tools, sees the real result, and only then writes
    the reply — so it can't confirm a viewing that failed to save.
  * Identity (soul), routing (intent), domain skill and persistent memory are
    separate prompt files, composed per turn.
  * Every draft passes a deterministic verification gate. One corrective retry,
    then a safe hand-off message. Unverified facts never reach the customer.
"""
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List

from django.conf import settings

from apps.messaging.models import MessageSender

from . import memory as agent_memory
from .tools import TOOL_SCHEMAS, RealEstateTools, hk_now
from .verifier import salvage, verify_reply

logger = logging.getLogger(__name__)

PROMPT_DIR = Path(__file__).resolve().parent / 'prompts'
MAX_TOOL_ROUNDS = 6
HISTORY_MESSAGES = 16

SAFE_FALLBACK = {
    'en': "I want to be sure I give you accurate information on that. Could you rephrase it, or would you like me to connect you with one of our agents?",
    'zh-CN': "我想确保给您准确的信息。您可以换个方式再说一次吗？或者需要我为您联系我们的经纪人吗？",
    'zh-TW': "我想確保俾你準確嘅資料。你可唔可以換個講法再講一次？定係需要我幫你聯絡我哋嘅經紀？",
}


def _load(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding='utf-8')


class RealEstateAgent:
    def __init__(self, ai_service):
        self.svc = ai_service
        self.conversation = ai_service.conversation
        self.organization = ai_service.organization
        self.tools = RealEstateTools(self.conversation)
        self.evidence: List[str] = []
        self.tool_trace: List[Dict[str, Any]] = []

    # ------------------------------------------------------------- prompt
    def _system_prompt(self, language: str) -> str:
        from apps.ai_engine.language_service import LanguageService

        now = hk_now()
        appts = self.tools.get_my_appointments()
        self.has_appointments = bool(appts.get('appointments'))
        appt_text = "\n".join(
            f"- {a['confirmation_code']}: {a['type']} on {a['weekday']} {a['date']} {a['time']}"
            f"{' — ' + a['property'] + ' (' + a['property_reference'] + ')' if a['property'] else ''}"
            for a in appts.get('appointments', [])
        ) or "(none)"
        overrides = self.svc._get_temporary_override_context() or "(none active)"

        soul = _load('soul.md').format(
            business_name=self.organization.name,
            channel=str(self.conversation.channel or 'website'),
            language_name=LanguageService.get_language_display_name(language),
            now_local=now.strftime('%Y-%m-%d %H:%M'), weekday=now.strftime('%A'),
            today=now.strftime('%Y-%m-%d'),
        )
        mem = _load('memory.md').format(
            owner_memory=agent_memory.owner_memory_text(self.organization),
            overrides=overrides,
            customer_memory=agent_memory.customer_memory_text(self.conversation),
            appointments=appt_text,
        )
        knowledge = self.svc._get_knowledge_context()
        channel_note = ""
        if self.conversation.customer_phone:
            channel_note = (f"\nThe customer's phone is already known ({self.conversation.customer_phone}); "
                            "never ask for it.\n")
        if self.conversation.customer_name and self.conversation.customer_name not in ('WhatsApp User', 'Website Visitor'):
            channel_note += f"Profile name on the channel: {self.conversation.customer_name} (confirm before using as booking name).\n"

        from datetime import timedelta
        calendar = "\n".join(
            f"- {(now + timedelta(days=i)):%A %Y-%m-%d}" + (" (today)" if i == 0 else " (tomorrow)" if i == 1 else "")
            for i in range(15)
        )
        self.evidence.extend([knowledge, appt_text, overrides])
        return "\n\n".join([
            soul, _load('intent.md'), _load('skills/real_estate.md'), mem,
            "# CALENDAR (use this, never compute dates yourself; \"next Saturday\" = the first Saturday after today)\n"
            + calendar,
            f"# KNOWLEDGE (agency facts — the only non-tool source of truth)\n{knowledge}",
            channel_note,
        ])

    def _history(self, current: str) -> List[Dict[str, str]]:
        msgs = list(self.conversation.messages.order_by('-created_at')[:HISTORY_MESSAGES])
        msgs.reverse()
        # The channel saved the current inbound message before calling us — drop it
        # so the model doesn't see the same user turn twice.
        if msgs and msgs[-1].sender == MessageSender.CUSTOMER and msgs[-1].content.strip() == current.strip():
            msgs = msgs[:-1]
        out = []
        for m in msgs:
            if not (m.content or '').strip():
                continue
            role = 'user' if m.sender == MessageSender.CUSTOMER else 'assistant'
            out.append({'role': role, 'content': m.content})
        return out

    # ---------------------------------------------------------------- loop
    def _complete(self, messages):
        return self.svc.client.chat.completions.create(
            model=getattr(settings, 'AI_AGENT_MODEL', '') or settings.OPENAI_MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice='auto',
            temperature=0.2,
            max_tokens=700,
        )

    def _run_tools(self, messages) -> str:
        registry = self.tools.registry()
        tokens = 0
        for _ in range(MAX_TOOL_ROUNDS):
            resp = self._complete(messages)
            tokens += getattr(resp.usage, 'total_tokens', 0) or 0
            msg = resp.choices[0].message
            calls = getattr(msg, 'tool_calls', None) or []
            if not calls:
                self.tokens = tokens
                return (msg.content or '').strip()
            messages.append({
                'role': 'assistant', 'content': msg.content or '',
                'tool_calls': [{'id': c.id, 'type': 'function',
                                'function': {'name': c.function.name, 'arguments': c.function.arguments}}
                               for c in calls],
            })
            for c in calls:
                name = c.function.name
                try:
                    args = json.loads(c.function.arguments or '{}')
                    fn = registry.get(name)
                    result = fn(**args) if fn else {'ok': False, 'error': f'unknown tool {name}'}
                except TypeError as e:
                    result = {'ok': False, 'error': f'bad arguments: {e}'}
                except Exception as e:  # tool bug must not kill the turn — surface it to the model + logs
                    logger.exception("Agent tool %s failed", name)
                    result = {'ok': False, 'error': 'internal error while running the tool'}
                payload = json.dumps(result, default=str, ensure_ascii=False)
                self.evidence.append(payload)
                # Criteria the agent searched with (e.g. max_price) are not claims about listings.
                self.evidence.append(c.function.arguments or '')
                self.tool_trace.append({'tool': name, 'args': c.function.arguments[:500], 'ok': result.get('ok')})
                messages.append({'role': 'tool', 'tool_call_id': c.id, 'content': payload})
        self.tokens = tokens
        return ''

    def run(self, user_message: str, language: str) -> Dict[str, Any]:
        started = time.time()
        self.tokens = 0
        messages = [{'role': 'system', 'content': self._system_prompt(language)}]
        history = self._history(user_message)
        messages += history
        messages.append({'role': 'user', 'content': user_message})
        # What the customer said is legitimate evidence (e.g. echoing their own budget).
        self.evidence.extend([m['content'] for m in history if m['role'] == 'user'] + [user_message])

        reply = self._run_tools(messages)
        gate = self._verify(reply)
        if reply and not gate.ok:
            logger.warning("Agent gate rejected draft: %s | %s", gate.problems, reply[:300])
            messages.append({'role': 'assistant', 'content': reply})
            messages.append({'role': 'system', 'content': (
                "VERIFICATION FAILED — your last reply was NOT sent. Problems: " + "; ".join(gate.problems)
                + ". Rewrite it. Only state figures/references that appear in tool results, KNOWLEDGE, or the "
                  "customer's own words. If the customer was vague (e.g. 'cheap'), describe it in words or ask "
                  "their budget — never invent a number. Never claim an action a tool did not confirm. "
                  "Keep being helpful: give the real options you have and one next step.")})
            first_draft, first_gate = reply, gate
            reply = self._run_tools(messages)
            gate = self._verify(reply)
            if reply and not gate.ok:
                logger.warning("Agent gate rejected retry: %s | %s", gate.problems, reply[:300])
                # Salvage: drop only the unverifiable sentences rather than dead-ending the chat.
                for draft, g in ((reply, gate), (first_draft, first_gate)):
                    trimmed = salvage(draft, g)
                    if trimmed and self._verify(trimmed).ok:
                        logger.info("Agent reply salvaged by trimming unverifiable sentences")
                        reply, gate = trimmed, self._verify(trimmed)
                        break

        verified = bool(reply) and gate is not None and gate.ok
        escalation = self.tools.escalation
        if not verified:
            # Never send an unverified draft. We don't silently hand off either: the
            # fallback asks the customer, and the failure is recorded on the AILog.
            reply = SAFE_FALLBACK.get(language, SAFE_FALLBACK['en'])

        intent = self._intent()
        result = {
            'content': reply,
            'confidence': 0.95 if verified and not escalation else 0.5,
            'intent': intent,
            'metadata': {'source': 'realestate_agent', 'tools': self.tool_trace,
                         'actions': self.tools.actions, 'verified': verified},
            'needs_handoff': bool(escalation),
            'handoff_reason': (escalation or {}).get('reason', ''),
            'language': language,
            'extracted_data': {},  # actions already executed by tools — channels must not re-create them
        }
        self._schedule_memory_consolidation()
        self.svc._log_interaction(
            prompt=user_message, response=reply, confidence=result['confidence'], intent=intent,
            model=getattr(settings, 'AI_AGENT_MODEL', '') or settings.OPENAI_MODEL, tokens=self.tokens,
            latency_ms=int((time.time() - started) * 1000),
            error='' if verified else 'gate:' + '; '.join(gate.problems if gate else ['empty']),
            language=language,
        )
        return result

    def _schedule_memory_consolidation(self):
        """Fold older turns into long-term memory before they slide out of the context window."""
        from django.db import transaction
        from apps.ai_engine.models import AgentMemory

        try:
            total = self.conversation.messages.count()
            if total <= HISTORY_MESSAGES:
                return
            key = agent_memory.customer_key(self.conversation)
            mem = AgentMemory.objects.filter(organization=self.organization, subject_type='customer',
                                             subject_key=key).first()
            oldest_in_window = (self.conversation.messages.order_by('-created_at')
                                .values_list('created_at', flat=True)[HISTORY_MESSAGES - 1])
            if mem and mem.summarized_until and mem.summarized_until >= oldest_in_window:
                return
            from apps.ai_engine.tasks import summarize_customer_memory_task
            org_id = str(self.organization.id)
            transaction.on_commit(lambda: summarize_customer_memory_task.delay(org_id, key))
        except Exception:
            logger.exception("Could not schedule memory consolidation")

    def _verify(self, reply: str):
        return verify_reply(reply, self.evidence, self.tools.actions, self._has_appts()) if reply else None

    def _has_appts(self) -> bool:
        return getattr(self, 'has_appointments', False) or any(
            t['tool'] == 'get_my_appointments' and t['ok'] for t in self.tool_trace)

    def _intent(self) -> str:
        used = [t['tool'] for t in self.tool_trace]
        for tool, intent in (('book_viewing', 'appointment'), ('cancel_appointment', 'appointment_cancel'),
                             ('escalate_to_human', 'handoff'), ('save_lead', 'lead_capture'),
                             ('get_property_details', 'property'), ('search_properties', 'property'),
                             ('get_my_appointments', 'appointment')):
            if tool in used:
                return intent
        return 'general'
