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
from datetime import datetime, timedelta
from typing import Any, Dict, List

from django.conf import settings

from apps.messaging.models import MessageSender

from . import language as reply_lang
from . import memory as agent_memory
from . import actions as agent_actions
from . import capabilities
from . import dialogue
from . import tone
from .tools import RealEstateTools, format_money
from .verifier import preview_problems, salvage, verify_reply

logger = logging.getLogger(__name__)

PROMPT_DIR = Path(__file__).resolve().parent / 'prompts'
MAX_TOOL_ROUNDS = 6
CATALOG_LIMIT = 40          # full one-line catalog in the prompt up to this many active listings
CARRYOVER_TURNS = 3         # tool results from the last N turns stay usable as evidence
CARRYOVER_CHARS = 6000

# Context budget. A big window (up to 40 messages) so a long chat stays coherent, but every section
# has a hard cap so one huge message, knowledge base or tool result can never crowd out the rest.
# Older turns than the window are folded into AgentMemory.summary (see memory.py) - never dropped.
HISTORY_MESSAGES = 40
HISTORY_CHARS = 18000       # newest messages first until this budget is used
MESSAGE_CHARS = 1500        # one very long message is shortened in the middle
KNOWLEDGE_CHARS = 9000
TOOL_RESULT_CHARS = 8000    # what the model sees of one tool result (evidence keeps the full text)
TEAM_NOTES = 6
DISCUSSED_LISTINGS = 8      # listings named in the visible chat, with their LIVE status
RETURN_GAP_HOURS = 6        # customer back after this long → reconnect to where we left off

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


def _ago(delta) -> str:
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{max(minutes, 1)} min ago"
    if minutes < 48 * 60:
        return f"{minutes // 60} h ago"
    return f"{minutes // (24 * 60)} days ago"


def _clip(text: str, limit: int) -> str:
    """Keep the start and the end of an over-long text (both usually matter)."""
    if len(text) <= limit:
        return text
    head = int(limit * 0.7)
    return text[:head] + " [...shortened...] " + text[-(limit - head - 20):]


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
            customer_memory=self._customer_memory(),
            appointments=appt_text,
        )
        knowledge = _clip(self.svc._get_knowledge_context() or '', KNOWLEDGE_CHARS)
        channel_note = ""
        if self.conversation.customer_phone:
            channel_note = (f"\nThe customer's phone is already known ({self.conversation.customer_phone}); "
                            "never ask for it.\n")
        if self.conversation.customer_name and self.conversation.customer_name not in ('WhatsApp User', 'Website Visitor'):
            channel_note += (f"Profile name on the channel: {self.conversation.customer_name}. It is NOT a confirmed "
                             "booking name: before prepare_viewing, ask whose name the viewing should be under "
                             "unless the customer already wrote it.\n")

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
            "# TEAM REQUESTS FOR THIS CUSTOMER (staff notes are facts you may repeat)\n" + self._team_text(),
            "# LISTINGS ALREADY DISCUSSED IN THIS CHAT (newest first, LIVE status now; resolve 'tyo / yo wala / "
            "that one / the second one' with this, and say so if a price or status changed since)\n"
            + self._discussed_text(),
            channel_note,
        ])

    def _connect_dots(self, brief) -> None:
        """What a person would notice before answering: the message the customer pointed at, and how
        long they were away."""
        from django.utils import timezone as dj_tz

        quoted = ((getattr(self, 'current_msg', None) and self.current_msg.ai_metadata) or {}).get('reply_to')
        if quoted and quoted.get('found'):
            ago = dj_tz.now() - datetime.fromisoformat(quoted['at'])
            brief.lines.insert(0, (
                f"The customer long-pressed and REPLIED TO an earlier {quoted['sender']} message from "
                f"{_ago(ago)}: \"{_clip(quoted['content'], 400)}\". Their message is about THAT message, not "
                "about the latest topic. Start by tying your answer to it in a few words (e.g. \"About the New "
                "Road shutter you asked about earlier...\"), re-check anything that may have changed since "
                "(listing, price, appointment) with a tool, then answer."))
            brief.quoted = quoted
        elif quoted:
            brief.lines.insert(0, "The customer replied to an older message we cannot see any more. If their "
                                  "message is unclear without it, ask which listing or booking they mean.")
        prev = getattr(self, 'previous_at', None)
        if prev and dj_tz.now() - prev > timedelta(hours=RETURN_GAP_HOURS):
            brief.lines.append(f"The customer is back after {_ago(dj_tz.now() - prev)}. If it helps, connect to "
                               "where you left off in ONE short line (from LISTINGS ALREADY DISCUSSED, APPOINTMENTS, "
                               "TEAM REQUESTS), mention anything that changed since, then answer what they asked now.")

    def _discussed_text(self) -> str:
        """Every listing named in the visible chat, newest mention first, with what it was when we
        said it and what it is NOW - the dots a person would connect when the customer comes back."""
        import re as _re
        from apps.realestate.models import PropertyListing

        seen, order, numbered = {}, [], {}
        msgs = list(self.conversation.messages.order_by('-created_at')[:HISTORY_MESSAGES])
        for m in msgs:                                    # newest → oldest
            refs = _re.findall(r'PROP\d{6}', m.content or '', _re.I)
            for ref in refs:
                ref = ref.upper()
                if ref not in seen:
                    seen[ref] = m
                    order.append(ref)
            if not numbered and m.sender != MessageSender.CUSTOMER:
                for pos, ref in _re.findall(r'(?m)^\s*(\d+)\.\s*\*?(PROP\d{6})', m.content or ''):
                    numbered[ref.upper()] = int(pos)
        if not order:
            return "(none yet)"
        listings = {p.reference_number.upper(): p for p in PropertyListing.objects.filter(
            organization=self.organization, reference_number__in=order[:DISCUSSED_LISTINGS])}
        lines = []
        for ref in order[:DISCUSSED_LISTINGS]:
            p = listings.get(ref)
            when = seen[ref].created_at
            pos = f" (#{numbered[ref]} in your latest list)" if ref in numbered else ''
            if not p:
                lines.append(f"- {ref}{pos}: no longer in the system")
                continue
            live = 'available' if p.status == 'active' and p.is_published else f'NOT available now ({p.status})'
            rent = p.listing_type in ('rent', 'lease')
            price = format_money(p.price, self.tools.market) + ('/month' if rent else '')
            changed = ''
            if p.updated_at and p.updated_at > when:
                changed = ' [updated after it was last mentioned: re-check with get_property_details]'
            lines.append(f"- {ref}{pos}: {p.title}, {p.neighborhood or p.city} - {price} - {live}; last mentioned "
                         f"{when:%Y-%m-%d %H:%M} UTC by {'customer' if seen[ref].sender == MessageSender.CUSTOMER else 'us'}"
                         f"{changed}")
        text = "\n".join(lines)
        self.evidence.append(text)
        return text

    def _customer_memory(self) -> str:
        """Long-term memory, minus anything a stale or foreign past would poison the prompt with
        (old Hong Kong listings, restaurant bookings from before the org changed business)."""
        from apps.ai_engine.vertical_guard import clean_memory
        from apps.realestate.models import PropertyListing

        refs = PropertyListing.objects.filter(organization=self.organization).values_list('reference_number', flat=True)
        return clean_memory(agent_memory.customer_memory_text(self.conversation), 'real_estate', refs,
                            self.tools.market['currency'])

    def _team_text(self) -> str:
        """Open requests the agent passed to staff, and what staff wrote when they resolved one -
        so a later "did the team send the photos?" is answered from the record, not guessed."""
        from apps.handoff.models import HandoffAlert

        rows = (HandoffAlert.objects.filter(conversation=self.conversation)
                .order_by('-created_at')[:TEAM_NOTES])
        lines = []
        for a in rows:
            state = 'resolved' if a.is_resolved else 'open'
            line = f"- [{state}, {a.created_at:%Y-%m-%d}] {a.reason[:240]}"
            if a.is_resolved and a.resolution_notes:
                line += f" -> staff: {a.resolution_notes[:240]}"
            lines.append(line)
        text = "\n".join(lines) or "(none)"
        self.evidence.append(text)
        return text

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
        """Newest messages first, within HISTORY_MESSAGES and HISTORY_CHARS. Messages from staff and
        automatic notices (reminders, "our team cancelled your viewing") are labelled, so the model
        knows the customer was told them and does not contradict them."""
        msgs = list(self.conversation.messages.order_by('-created_at')[:HISTORY_MESSAGES + 1])
        # The channel saved the current inbound message before calling us - drop it
        # so the model doesn't see the same user turn twice.
        self.current_msg = None
        if msgs and msgs[0].sender == MessageSender.CUSTOMER and msgs[0].content.strip() == current.strip():
            self.current_msg = msgs[0]
            msgs = msgs[1:]
        self.previous_at = msgs[0].created_at if msgs else None
        msgs = msgs[:HISTORY_MESSAGES]
        out, used = [], 0
        for m in msgs:                       # newest → oldest
            text = (m.content or '').strip()
            if not text:
                continue
            text = _clip(text, MESSAGE_CHARS)
            quoted = (m.ai_metadata or {}).get('reply_to') if m.sender == MessageSender.CUSTOMER else None
            if quoted and quoted.get('found'):
                text = f"[replying to the {quoted['sender']} message \"{_clip(quoted['content'], 200)}\"] " + text
            if m.sender == MessageSender.HUMAN:
                text = "[Message from our staff to the customer] " + text
            elif m.sender == MessageSender.SYSTEM:
                text = "[Automatic notice sent to the customer] " + text
            if used + len(text) > HISTORY_CHARS and out:
                break
            used += len(text)
            out.append({'role': 'user' if m.sender == MessageSender.CUSTOMER else 'assistant', 'content': text,
                        '_at': m.created_at})
        out.reverse()
        self.history_oldest_at = out[0]['_at'] if out else None
        for o in out:
            o.pop('_at')
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
                messages.append({'role': 'tool', 'tool_call_id': c.id, 'content': _clip(payload, TOOL_RESULT_CHARS)})
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
        self.brief = dialogue.analyse(user_message, history,
                                      pending_preview=agent_actions.pending_preview(self.conversation) is not None)
        self._connect_dots(self.brief)
        # Last word before the customer's message, so it outweighs the language of older turns.
        messages.append({'role': 'system', 'content': (
            "REPLY LANGUAGE FOR THIS TURN: " + reply_lang.instruction_for(self.reply_style)
            + " Answer the customer's actual question with real data from PORTFOLIO/tools first; "
              "ask at most ONE follow-up question after that.\n"
            "TURN BRIEF (decided by the system from this conversation - binding):\n" + self.brief.text())})
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
            'metadata': {'source': 'realestate_agent', 'tools': self.tool_trace, 'reply_style': self.reply_style,
                         'vertical_checked': verified,
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
                           'brief': getattr(self, 'brief', None) and self.brief.lines,
                           'context_chars': sum(len(str(m.get('content') or '')) for m in messages),
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
            oldest_in_window = getattr(self, 'history_oldest_at', None)
            if oldest_in_window is None or not self.conversation.messages.filter(
                    created_at__lt=oldest_in_window).exists():
                return  # everything still fits in the window
            key = agent_memory.customer_key(self.conversation)
            mem = AgentMemory.objects.filter(organization=self.organization, subject_type='customer',
                                             subject_key=key).first()
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
        from apps.ai_engine.vertical_guard import off_vertical
        said = [m.content for m in self.conversation.messages.filter(sender=MessageSender.CUSTOMER)
                .order_by('-created_at')[:20]] + [getattr(self.tools, 'current_message', '')]
        leaked = off_vertical('real_estate', reply, said + self.evidence)  # listing facts may say 'restaurant'
        if leaked:
            gate.fail(f"OFF_VERTICAL: this is a property agency; never mention {', '.join(leaked)}. If the "
                      "customer asks about something else, say politely that you help with property only.", fatal=True)
        brief = getattr(self, 'brief', None)
        if brief is not None:
            for problem in dialogue.problems(reply, brief, [t['tool'] for t in self.tool_trace],
                                             [t['tool'] for t in self.tool_trace if t.get('ok')]):
                gate.fail(problem, fatal=True)
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
