"""
Real-estate agent loop: plan → call tools → observe → answer → verify.

Design (borrowed from HisabKitab / MigAlpha and tool-using agent harnesses):
  * The model never "declares" side-effects in JSON for someone else to maybe
    execute later. It calls tools, sees the real result, and only then writes
    the reply - so it can't confirm a viewing that failed to save.
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

from . import language as reply_lang
from . import memory as agent_memory
from . import actions as agent_actions
from . import capabilities
from . import tone
from .tools import RealEstateTools, format_money
from .verifier import preview_problems, salvage, verify_reply

logger = logging.getLogger(__name__)

PROMPT_DIR = Path(__file__).resolve().parent / 'prompts'
MAX_TOOL_ROUNDS = 6
HISTORY_MESSAGES = 16
CATALOG_LIMIT = 40          # full one-line catalog in the prompt up to this many active listings
CARRYOVER_TURNS = 3         # tool results from the last N turns stay usable as evidence
CARRYOVER_CHARS = 6000

SAFE_FALLBACK = {
    'en': "I want to be sure I give you accurate information on that. Could you rephrase it, or would you like me to connect you with one of our agents?",
    'zh-CN': "我想确保给您准确的信息。您可以换个方式再说一次吗？或者需要我为您联系我们的经纪人吗？",
    'zh-TW': "我想確保俾你準確嘅資料。你可唔可以換個講法再講一次？定係需要我幫你聯絡我哋嘅經紀？",
    reply_lang.NEPALI_ROMAN: "Hajur, ma tapai lai sahi jankari dina chahanchu. Ek choti feri bhannu huncha, ki hamro team ko manche sanga kura garaidiu?",
    reply_lang.NEPALI_DEVANAGARI: "हजुर, म तपाईंलाई सही जानकारी दिन चाहन्छु। एक पटक फेरि भन्नुहुन्छ कि, वा हाम्रो टिमको मान्छेसँग कुरा गराइदिऊँ?",
}


def _timing_label(t: Dict[str, Any]) -> str:
    """Appointments are compared with NOW, not just today's date (a 11:00 slot at 13:51 is over)."""
    if t['state'] == 'upcoming':
        m = t['minutes_until_start']
        return f"UPCOMING, starts in {m // 60}h {m % 60}m" if m >= 60 else f"UPCOMING, starts in {m} min"
    if t['state'] == 'in_progress':
        return "IN PROGRESS NOW"
    m = t['minutes_since_end']
    return (f"TIME PASSED, ended {m // 60}h {m % 60}m ago: never describe it as upcoming or 'confirmed for "
            "today'; ask kindly whether the viewing happened and offer a new time if they missed it")


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
        self.tool_facts: List[str] = []

    # ------------------------------------------------------------- prompt
    def _system_prompt(self, language: str) -> str:
        from apps.ai_engine.language_service import LanguageService

        style = getattr(self, 'reply_style', language)
        now = self.tools.now()
        market = self.tools.market
        appts = self.tools.get_my_appointments()
        self.has_appointments = bool(appts.get('appointments'))
        appt_text = "\n".join(
            f"- {a['confirmation_code']}: {a['type']} on {a['weekday']} {a['date']} {a['time']}"
            f"{' - ' + a['property'] + ' (' + a['property_reference'] + ')' if a['property'] else ''}"
            f" [{a['status']}; {_timing_label(a['timing'])}]"
            for a in appts.get('appointments', [])
        ) or "(none)"
        overrides = self.svc._get_temporary_override_context() or "(none active)"

        soul = _load('soul.md').format(
            business_name=self.organization.name,
            channel=str(self.conversation.channel or 'website'),
            language_name=reply_lang.DISPLAY.get(style) or LanguageService.get_language_display_name(language),
            market=market['name'] or 'the local market', currency=market['currency'], timezone=market['tz'],
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
        skill = _load(self._skill_file(market))
        portfolio = self._portfolio_text()
        earlier = self._earlier_tool_facts()
        self.evidence.extend([knowledge, appt_text, overrides, calendar, portfolio, earlier,
                              self.conversation.customer_phone or ''])
        return "\n\n".join([
            soul, _load('tone.md'), _load('intent.md'), skill, mem,
            "# CALENDAR (use this, never compute dates yourself; \"next Saturday\" = the first Saturday after today)\n"
            + calendar,
            "# PORTFOLIO (live from the database right now - this IS what the agency offers; use it to answer "
            "broad questions immediately, and call tools for details/filters)\n" + portfolio,
            f"# KNOWLEDGE (agency facts - the only non-tool source of truth)\n{knowledge}",
            "# FACTS FROM EARLIER TOOL CALLS IN THIS CHAT (re-check with a tool before booking)\n" + (earlier or "(none)"),
            "# CAPABILITIES (set by the agency owner - never offer anything outside this)\n"
            + capabilities.describe(self.organization, self.tools.settings),
            "# PENDING DECISION\n" + self._pending_text(),
            channel_note,
        ])

    def _pending_text(self) -> str:
        action = agent_actions.pending_preview(self.conversation)
        if not action:
            return "(none)"
        self.evidence.append(json.dumps(action.payload, ensure_ascii=False, default=str))
        return (f"preview_id {action.id} - {action.get_kind_display()}: "
                f"{json.dumps(action.payload, ensure_ascii=False, default=str)}\n"
                "If the customer's latest message is a plain yes to THIS, call confirm_pending_action. "
                "If they said no/keep it, call decline_pending_action. If they changed details, prepare a new "
                "preview. If they asked something else, answer it and remind them this is still waiting.")

    def _portfolio_text(self) -> str:
        overview = self.tools.get_portfolio_overview()
        lines = [f"Active listings: {overview['total_active_listings']}"]
        for c in overview['categories']:
            lines.append(f"- {c['category']}: {c['listings']} listing(s) in {', '.join(c['districts'])}; "
                         f"{c['price_range']}")
        listings = list(self.tools._active_listings().order_by('property_type', 'price')[:CATALOG_LIMIT + 1])
        if len(listings) <= CATALOG_LIMIT:
            lines.append("Catalog (reference | type | title | price | area):")
            for p in listings:
                rent = p.listing_type in ('rent', 'lease')
                price = format_money(p.price, self.tools.market) + ('/month' if rent else '')
                lines.append(f"- {p.reference_number} | {p.get_property_type_display()} for "
                             f"{'rent' if rent else 'sale'} | {p.title} | {price} | {p.neighborhood or p.city}, {p.city}")
        else:
            lines.append("(Too many to list here - use search_properties with filters.)")
        return "\n".join(lines)

    def _earlier_tool_facts(self) -> str:
        """Tool results from recent turns, so follow-ups ("kati ho esko?") stay grounded."""
        from apps.ai_engine.models import AILog

        logs = (AILog.objects.filter(conversation=self.conversation, context__has_key='tool_facts')
                .order_by('-created_at').values_list('context', flat=True)[:CARRYOVER_TURNS])
        facts = [f for ctx in reversed(list(logs)) for f in (ctx or {}).get('tool_facts', [])]
        return "\n".join(facts)[-CARRYOVER_CHARS:]

    @staticmethod
    def _skill_file(market) -> str:
        specific = PROMPT_DIR / 'skills' / f"real_estate_{market['name'].lower().replace(' ', '_')}.md"
        return f"skills/{specific.name}" if market['name'] and specific.exists() else 'skills/real_estate.md'

    def _history(self, current: str) -> List[Dict[str, str]]:
        msgs = list(self.conversation.messages.order_by('-created_at')[:HISTORY_MESSAGES])
        msgs.reverse()
        # The channel saved the current inbound message before calling us - drop it
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
    @staticmethod
    def _model() -> str:
        return getattr(settings, 'AI_AGENT_MODEL', '') or settings.OPENAI_MODEL

    def _complete(self, messages):
        model = self._model()
        kwargs = dict(model=model, messages=messages, tools=self.tools.schemas(), tool_choice='auto')
        kwargs.update(self._sampling())
        return self.svc.client.chat.completions.create(**kwargs)

    def _sampling(self) -> Dict[str, Any]:
        if self._model().startswith(('gpt-5', 'o3', 'o4')):
            # Reasoning models: no temperature; the output budget includes reasoning tokens.
            return dict(max_completion_tokens=4000, reasoning_effort='low')
        return dict(temperature=0.2, max_tokens=900)

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
                except Exception as e:  # tool bug must not kill the turn - surface it to the model + logs
                    logger.exception("Agent tool %s failed", name)
                    result = {'ok': False, 'error': 'internal error while running the tool'}
                payload = json.dumps(result, default=str, ensure_ascii=False)
                self.evidence.append(payload)
                # Tool ARGUMENTS are deliberately not evidence: a made-up max_price must not be
                # able to "verify" itself. Customer-stated budgets are already in evidence.
                if name in ('search_properties', 'get_property_details', 'get_portfolio_overview') and result.get('ok'):
                    self.tool_facts.append(f"{name}: {payload[:1500]}")
                entry = {'tool': name, 'args': c.function.arguments[:500], 'ok': result.get('ok')}
                if name == 'confirm_pending_action' and result.get('ok') and not result.get('already_done'):
                    entry['receipt'] = result.get('receipt')
                self.tool_trace.append(entry)
                messages.append({'role': 'tool', 'tool_call_id': c.id, 'content': payload})
        self.tokens = tokens
        return ''

    def run(self, user_message: str, language: str) -> Dict[str, Any]:
        from django.utils import timezone as dj_tz

        started = time.time()
        self.tokens = 0
        # The confirmation gate needs the customer's own words and the turn boundary.
        self.tools.current_message = user_message
        self.tools.turn_started_at = dj_tz.now()
        capped = self._daily_cap_reached()
        if capped:
            return capped
        history = self._history(user_message)
        self.reply_style = reply_lang.sticky_reply_style(
            user_message, [m['content'] for m in history if m['role'] == 'user'], fallback=language)
        messages = [{'role': 'system', 'content': self._system_prompt(language)}]
        messages += history
        # Last word before the customer's message, so it outweighs the language of older turns.
        messages.append({'role': 'system', 'content': (
            "REPLY LANGUAGE FOR THIS TURN: " + reply_lang.instruction_for(self.reply_style)
            + " Answer the customer's actual question with real data from PORTFOLIO/tools first; "
              "ask at most ONE follow-up question after that.")})
        messages.append({'role': 'user', 'content': user_message})
        # What the customer said is legitimate evidence (e.g. echoing their own budget).
        self.evidence.extend([m['content'] for m in history if m['role'] == 'user'] + [user_message])

        reply = self._run_tools(messages)
        gate = self._verify(reply)
        if reply and not gate.ok:
            logger.warning("Agent gate rejected draft: %s | %s", gate.problems, reply[:300])
            messages.append({'role': 'assistant', 'content': reply})
            messages.append({'role': 'system', 'content': (
                "VERIFICATION FAILED - your last reply was NOT sent. Problems: " + "; ".join(gate.problems)
                + ". Fix it (call the tool the problem names if needed), then rewrite. Only state "
                  "figures/references that appear in tool results, KNOWLEDGE, or the "
                  "customer's own words. If the customer was vague (e.g. 'cheap'), describe it in words or ask "
                  "their budget - never invent a number. Never claim an action a tool did not confirm. "
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
        if verified:
            reply = self._respectful(messages, reply)
        escalation = self.tools.escalation
        if not verified:
            # Never send an unverified draft. We don't silently hand off either: the
            # fallback asks the customer, and the failure is recorded on the AILog.
            reply = SAFE_FALLBACK.get(self.reply_style) or SAFE_FALLBACK.get(language, SAFE_FALLBACK['en'])
        # A completed action is reported from its stored receipt, whatever the model wrote.
        receipts = self._receipts()
        if receipts and not verified:
            reply = "\n".join(reply_lang.receipt_line(r, self.reply_style) for r in receipts)
        for receipt in receipts:
            if receipt.get('code') and receipt['code'] not in reply:
                reply = (reply + "\n\n" + reply_lang.receipt_line(receipt, self.reply_style)).strip()

        reply = tone.no_dashes(tone.polish(reply, self.reply_style))

        # Staff may have taken the chat over while we were thinking: then the AI must stay silent.
        self.conversation.refresh_from_db(fields=['state'])
        suppressed = self.conversation.state == 'human_handoff'

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
            'extracted_data': {},  # actions already executed by tools - channels must not re-create them
            'suppressed': suppressed,
        }
        attachments = self.tools.attachments if verified else []
        if attachments and str(self.conversation.channel) != 'whatsapp':
            # Channels without native images get the links; WhatsApp sends real image messages.
            result['content'] += "\n\n" + "\n".join(a['url'] for a in attachments)
        result['attachments'] = attachments
        result['metadata']['attachments'] = len(attachments)
        if suppressed:
            result.update(content='', needs_handoff=False, attachments=[])
        self._schedule_memory_consolidation()
        self.svc._log_interaction(
            prompt=user_message, response=reply, confidence=result['confidence'], intent=intent,
            model=self._model(), tokens=self.tokens,
            latency_ms=int((time.time() - started) * 1000),
            error='' if verified else 'gate:' + '; '.join(gate.problems if gate else ['empty']),
            language=language,
            context_extra={'reply_style': self.reply_style, 'tools': self.tool_trace,
                           'tone_problems': getattr(self, 'tone_problems', []),
                           'tool_facts': self.tool_facts[-4:], 'suppressed': suppressed},
        )
        self._meter()
        return result

    def _respectful(self, messages, reply: str) -> str:
        """Tone gate: a low-register draft gets one rewrite pass (no tools → no side effects).

        The rewrite must still pass the verification gate; otherwise the original verified
        draft is kept and only the deterministic polish() upgrades it.
        """
        problems = tone.register_problems(reply, self.reply_style)
        if not problems:
            return reply
        logger.info("Agent tone gate: %s | %s", problems, reply[:200])
        self.tone_problems = problems
        try:
            kwargs = self._sampling()
            resp = self.svc.client.chat.completions.create(
                model=self._model(),
                messages=messages + [{'role': 'assistant', 'content': reply},
                                     {'role': 'system', 'content': tone.rewrite_instruction(problems)}],
                **kwargs)
            self.tokens += getattr(resp.usage, 'total_tokens', 0) or 0
            rewritten = (resp.choices[0].message.content or '').strip()
        except Exception:
            logger.exception("Tone rewrite failed; sending the verified draft with polish only")
            return reply
        if rewritten and self._verify(rewritten).ok and not tone.register_problems(rewritten, self.reply_style):
            return rewritten
        return reply

    def _receipts(self) -> List[Dict[str, Any]]:
        out = []
        for t in self.tool_trace:
            if t['tool'] == 'confirm_pending_action' and t.get('receipt'):
                out.append(t['receipt'])
        return out

    def _daily_cap_reached(self):
        """Owner-set daily AI reply cap (cost control; the seam for paid-plan quotas)."""
        from django.utils import timezone as dj_tz
        from apps.ai_engine.models import AILog

        cap = self.tools.settings.daily_ai_reply_cap
        if not cap:
            return None
        start = dj_tz.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if AILog.objects.filter(organization=self.organization, created_at__gte=start).count() < cap:
            return None
        logger.warning("Daily AI reply cap (%s) reached for org %s", cap, self.organization.id)
        return {'content': reply_lang.busy_message(self.reply_style if hasattr(self, 'reply_style') else 'en'),
                'confidence': 0.0, 'intent': 'capped', 'metadata': {'source': 'realestate_agent', 'capped': True},
                'needs_handoff': True, 'handoff_reason': 'daily_ai_cap', 'language': 'en', 'extracted_data': {},
                'suppressed': False}

    def _meter(self):
        """Best-effort usage record per AI reply - the data a future subscription bills from."""
        try:
            from decimal import Decimal
            from apps.billing.services.meter import record_usage
            per_1k = Decimal(str(getattr(settings, 'AGENT_COST_PER_1K_TOKENS_USD', '0.0008')))
            record_usage(organization=self.organization, module='chatbot_ai', event_type='agent_reply',
                         provider='openai', model=self._model(),
                         cost_usd=(per_1k * Decimal(self.tokens) / 1000).quantize(Decimal('0.000001')),
                         metadata={'tokens': self.tokens, 'tools': [t['tool'] for t in self.tool_trace],
                                   'conversation': str(self.conversation.id)})
        except Exception:
            logger.exception("Agent usage metering failed")

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
        if not reply:
            return None
        gate = verify_reply(reply, self.evidence, self.tools.actions, self._has_appts())
        # What the customer is asked to confirm must be the stored preview (see verifier.preview_problems).
        confirmed = any(t['tool'] == 'confirm_pending_action' and t.get('ok') for t in self.tool_trace)
        pending = agent_actions.pending_preview(self.conversation)
        for problem, span in preview_problems(reply, pending.payload if pending else None, confirmed):
            gate.fail(problem, span)
        return gate

    def _has_appts(self) -> bool:
        return getattr(self, 'has_appointments', False) or any(
            t['tool'] == 'get_my_appointments' and t['ok'] for t in self.tool_trace)

    def _intent(self) -> str:
        used = [t['tool'] for t in self.tool_trace]
        for tool, intent in (('confirm_pending_action', 'appointment'), ('prepare_viewing', 'appointment'),
                             ('prepare_cancellation', 'appointment_cancel'), ('prepare_reschedule', 'appointment'),
                             ('escalate_to_human', 'handoff'), ('save_lead', 'lead_capture'),
                             ('get_property_details', 'property'), ('compare_properties', 'property'),
                             ('search_properties', 'property'), ('list_locations', 'property'),
                             ('get_my_appointments', 'appointment')):
            if tool in used:
                return intent
        return 'general'
