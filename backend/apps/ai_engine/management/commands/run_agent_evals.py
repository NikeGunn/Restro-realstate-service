"""
Run the real-estate agent against the spec scenarios with the REAL configured model.

    python manage.py run_agent_evals                       # all cases once
    python manage.py run_agent_evals --cases RE-003 RE-043 --repeat 5
    python manage.py run_agent_evals --report /tmp/agent_eval.md

Creates a throwaway synthetic tenant, runs every case in its own conversation, applies
deterministic checks (tools, DB deltas, required/forbidden facts, reply language), prints
a report and deletes the tenant. Never touches real customers. Costs real API tokens.
"""
import re
import time
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.ai_engine.agent import language as reply_lang
from apps.ai_engine.evals.scenarios import CASES, FIXTURE


HEDGE = re.compile(r"guarantee|sakdina|sakinna|bhanna|record|chhaina|chaina|haina|hoina|cannot|can't|\bnot\b|"
                   r"verify|confirm|thaha", re.I)


def _style_ok(reply: str, style: str) -> bool:
    if style == 'zh':
        return bool(re.search(r'[一-鿿]', reply))
    if style == 'ne-deva':
        return len(re.findall(r'[ऀ-ॿ]', reply)) > len(re.findall(r'[A-Za-z]', reply)) * 0.5
    detected = reply_lang.detect_reply_style(reply, fallback='en')
    return detected == style


class Command(BaseCommand):
    help = 'Live-model behavioural evaluation of the real-estate agent (synthetic tenant).'

    def add_arguments(self, parser):
        parser.add_argument('--cases', nargs='*', default=None)
        parser.add_argument('--repeat', type=int, default=1)
        parser.add_argument('--report', default='')
        parser.add_argument('--verbose', action='store_true')

    def handle(self, *args, **opts):
        from apps.accounts.models import Location, Organization
        from apps.realestate.models import Appointment, Lead, PropertyListing

        org = Organization.objects.create(name=f'EVAL agent {uuid.uuid4().hex[:6]}', business_type='real_estate')
        try:
            Location.objects.create(organization=org, name='Eval Office', is_primary=True, is_active=True,
                                    country='Nepal', timezone='Asia/Kathmandu')
            refs = {}
            for key, title, ptype, ltype, price, city, hood, extra in FIXTURE:
                extra = dict(extra)
                status = extra.pop('status', 'active')
                p = PropertyListing.objects.create(
                    organization=org, title=title, description=title, property_type=ptype, listing_type=ltype,
                    price=Decimal(price), rent_period='monthly' if ltype == 'rent' else '', address_line1=hood,
                    city=city, neighborhood=hood, state='Koshi', postal_code='', country='Nepal', status=status,
                    **extra)
                refs[key] = p.reference_number
            cases = [c for c in CASES if not opts['cases'] or c['id'] in opts['cases']]
            rows, started = [], time.time()
            for case in cases:
                for attempt in range(opts['repeat']):
                    rows.append(self._run_case(org, case, refs, attempt, opts['verbose'], Appointment, Lead))
            self._report(rows, time.time() - started, opts['report'])
        finally:
            org.delete()

    def _run_case(self, org, case, refs, attempt, verbose, Appointment, Lead):
        from apps.ai_engine.services import AIService
        from apps.messaging.models import Channel, Conversation, Message, MessageSender

        Appointment.objects.filter(organization=org).delete()  # every case starts with free slots
        conv = Conversation.objects.create(
            organization=org, channel=Channel.WHATSAPP, customer_name='Eval Customer',
            customer_phone=f'97798{uuid.uuid4().int % 10**8:08d}')
        failures, transcript, latencies = [], [], []
        turns = [t.format(**{k: v for k, v in refs.items()}) for t in case['turns']]
        for i, text in enumerate(turns):
            Message.objects.create(conversation=conv, sender=MessageSender.CUSTOMER, content=text)
            t0 = time.time()
            out = AIService(conv).process_message(text)
            latencies.append(time.time() - t0)
            reply = out.get('content') or ''
            Message.objects.create(conversation=conv, sender=MessageSender.AI, content=reply)
            tools = [t['tool'] for t in out.get('metadata', {}).get('tools', [])]
            transcript.append((text, reply, tools))
            checks = case.get('per_turn', {}).get(i, {})
            if i == len(turns) - 1:
                checks = {**{k: v for k, v in case.items() if k not in ('id', 'turns', 'per_turn')}, **checks}
            failures += [f"turn {i + 1}: {f}" for f in self._check(checks, reply, tools, conv, org, Appointment, Lead)]
        if verbose:
            for text, reply, tools in transcript:
                self.stdout.write(f"  > {text}\n  < [{', '.join(tools) or '-'}] {reply}\n")
        status = 'PASS' if not failures else 'FAIL'
        self.stdout.write(f"{status} {case['id']}#{attempt + 1} ({sum(latencies):.1f}s) {'; '.join(failures)}")
        return {'id': case['id'], 'attempt': attempt + 1, 'ok': not failures, 'failures': failures,
                'transcript': transcript, 'latency': latencies}

    @staticmethod
    def _check(c, reply, tools, conv, org, Appointment, Lead):
        low = reply.lower()
        out = []
        if c.get('tools_any') and not set(c['tools_any']) & set(tools):
            out.append(f"expected one of tools {c['tools_any']}, got {tools}")
        for t in c.get('tools_none', []):
            if t in tools:
                out.append(f"forbidden tool {t} called")
        for s in c.get('contains', []):
            if s.lower() not in low:
                out.append(f"missing '{s}'")
        if c.get('contains_any') and not any(s.lower() in low for s in c['contains_any']):
            out.append(f"none of {c['contains_any']}")
        for pattern in c.get('absent', []):
            m = re.search(pattern, reply, re.I)
            if m:
                out.append(f"forbidden text '{m.group(0)}'")
        for pattern in c.get('unhedged', []):
            for m in re.finditer(pattern, reply, re.I):
                start = max(reply.rfind('.', 0, m.start()), reply.rfind('\n', 0, m.start())) + 1
                sentence = re.split(r'(?<=[.!?।])\s', reply[start:])[0]
                if not HEDGE.search(sentence):
                    out.append(f"unhedged claim '{m.group(0)}'")
        if c.get('style') and not _style_ok(reply, c['style']):
            out.append(f"reply language is not {c['style']}")
        if 'appts' in c and Appointment.objects.filter(organization=org, conversation=conv).count() != c['appts']:
            out.append(f"appointments for this chat != {c['appts']}")
        if 'leads' in c and Lead.objects.filter(organization=org, conversation=conv).count() != c['leads']:
            out.append(f"leads for this chat != {c['leads']}")
        return out

    def _report(self, rows, seconds, path):
        passed = sum(r['ok'] for r in rows)
        lat = sorted(x for r in rows for x in r['latency'])
        p95 = lat[int(len(lat) * 0.95) - 1] if lat else 0
        model = getattr(settings, 'AI_AGENT_MODEL', '') or settings.OPENAI_MODEL
        summary = (f"\n{passed}/{len(rows)} passed · model {model} · {seconds:.0f}s total · "
                   f"turn latency p50 {lat[len(lat) // 2] if lat else 0:.1f}s p95 {p95:.1f}s")
        self.stdout.write(self.style.SUCCESS(summary) if passed == len(rows) else self.style.WARNING(summary))
        if path:
            lines = [f"# Agent eval — {model}", summary.strip(), '']
            for r in rows:
                lines.append(f"## {'✅' if r['ok'] else '❌'} {r['id']} #{r['attempt']}")
                lines += [f"- {f}" for f in r['failures']]
                for text, reply, tools in r['transcript']:
                    lines.append(f"> **User:** {text}\n>\n> **Agent** _[{', '.join(tools) or '-'}]_: "
                                 + reply.replace('\n', '\n> '))
                lines.append('')
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write('\n'.join(lines))
            self.stdout.write(f"Report written to {path}")
