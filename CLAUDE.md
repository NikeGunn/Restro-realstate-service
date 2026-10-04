# CLAUDE.md

Guidance for Claude Code in this repo. Kept short on purpose: the code, tests and git history
hold the details. Last rewritten 2026-10-03.

## What this is

**Kribaat** (kribaat.com): multi-tenant AI chat platform for businesses, with two verticals on one
core: **Restaurant** and **Real Estate**. Customers chat on WhatsApp, Instagram or the website
widget; an AI answers from the business's own data and hands off to humans when unsure.

- `backend/`: Django 4.2 + DRF + Celery (Python 3.11), Postgres, Redis.
- `frontend/`: React 18 + Vite + TS + Tailwind + Shadcn admin dashboard.
- `backend/apps/widget/widget.js`: the embeddable widget (single vanilla JS file, no framework).
- Specs: `REQUIREMENTS.md` (phases 0-6, all built), `PRD-coffee.md` (Coffee Pass),
  `pending-work.md` (**the current to-do list; start there**). `agent.md` (gitignored) is the
  original scope lock: no POS/delivery unless the user authorizes it.

Current production customer: **Kribaat Realestate** (`business_type=real_estate`), a **Nepal**
room/flat/land agency (Kathmandu Office, NPR, Asia/Kathmandu). Customers write English, Romanized
Nepali ("malai kotha chaiyo") and Devanagari.

## Commands (always Docker, never host Python/Node)

```bash
docker compose up --build                              # db, redis, backend, celery, beat, frontend
docker compose run --rm backend pytest -q              # all backend tests (~850, ~7 min)
docker compose run --rm backend pytest apps/ai_engine  # one app
docker compose run --rm frontend npm run build         # prod build (skips tsc)
docker compose run --rm frontend npm run build:check   # tsc + build (older TS errors exist in
                                                       # realestate/settings/api.ts; add no new ones)
docker compose exec backend python manage.py makemigrations <app>
```
Backend http://localhost:18000 · Frontend http://localhost:13000 · Docs /api/docs/.
Host ports are shifted (DB 15432, Redis 16379) to coexist with sibling projects.
The repo path contains a space and `&`: quote it in shell commands.

## Deploy (GitOps, Tencent Cloud K3s)

`git push origin main` → GitHub Actions (`.github/workflows/deploy.yml`) builds images to Docker
Hub, rewrites image tags in `k8s/*` and commits "🚀 Deploy" → ArgoCD syncs (~3-10 min), running the
PreSync `migrate-job` first.
- CI backend tests are **blocking** (`pytest` + `makemigrations --check`): a red suite does not deploy.
- Never hand-edit image tags, never use `redeploy.ps1`/SSH to deploy.
- Non-secret config → `k8s/configmap.yaml`. Secrets → GitHub Secret + a `--from-literal` line in
  the `deploy-secrets` job.
- Migrations must be additive (old pod runs against the new schema during rollout).
- Backend is pinned to 1 replica (media on a RWO PVC) until object storage is enabled.
- Prod shell (diagnostics/data ops, not deploys): see memory `prod-cluster-access`
  (`ssh -i Kribaat.pem ubuntu@43.152.233.234 "sudo k3s kubectl exec -i deployment/backend -n chatplatform -- python manage.py shell"`).

## Architecture rules that span files

1. **One channel-agnostic conversation model** (`messaging.Conversation`/`Message`). New channels
   add a service + webhook in `apps/channels`, never a new message model.
2. **AI is grounded, never creative.** It answers only from tools / knowledge / vertical data;
   unsure → ask or hand off. Every AI turn is logged to `AILog`.
3. **Human handoff silences the AI** for that conversation.
4. **Location overrides organization** for knowledge.
5. **Reply in the customer's language and script.**
6. **Plan gating is enforced on the API**; the UI only mirrors it. Vertical gating is currently
   UI + route guard only (data is still org-scoped on the API).
7. **Verticals plug into the core**, never duplicate auth/messaging/AI.
8. **Admin-configurable, not code-configured:** market/currency, listings, knowledge, FAQs, agent
   playbook and channels are all edited in the dashboard; the agent reads them live.

## Backend apps (`backend/apps/`)

| App | Mount | Notes |
|---|---|---|
| `accounts` | `/api/auth/`, `/api/organizations/` | Custom `User` (email login), `Organization` (`business_type`, `plan`), `Location` (**`country` = the market**), memberships with roles `owner` / `manager` (owner writes). |
| `messaging`, `channels`, `widget`, `handoff`, `knowledge`, `analytics` | various | Core chat pipeline. Webhooks under `/api/webhooks/` are signature-verified. |
| `ai_engine` | `/api/v1/ai/` | `AIService` (restaurant path: JSON prompting). **Real-estate orgs use the tool-calling agent** in `ai_engine/agent/` (below). `AgentMemory` = owner playbook + per-customer memory. |
| `realestate` | `/api/realestate/` | Listings (`country` per listing), leads, appointments. `manage.py seed_nepal_portfolio --org NAME [--wipe]` seeds a Nepal demo portfolio. |
| `restaurant` | `/api/restaurant/` | Menu (item types, promo rules), bookings. |
| `inventory` | `/api/v1/inventory/` | Restaurant back office (stock ledger, recipes, POs, AI). Isolated from customer AI by `inventory/firewall.py`. |
| `common` | (no URLs) | Shared `OrgScopeMixin`, `IsOrgMember`/`IsOrgOwner`, throttles, Redis idempotency, storage switch. Use these for new apps. |
| `crm`, `lucky_draw`, `content_studio`, `billing`, `payments`, `coffee_pass`, `coupons` | `/api/v1/...` | CRM Lite, QR lucky draw, AI image studio (Power plan), credit wallet + spend cap, Stripe credit packs (test mode), cafe membership pass, plan-tier coupons. Each has its own `tests/`. |

## The real-estate agent (`backend/apps/ai_engine/agent/`)

Loop per message: build prompt → model calls tools → real results → draft → **verification gate**
→ (one corrective retry → trim unverifiable sentences → honest fallback).
- `prompts/`: `soul.md` (identity + hard rules), `intent.md` (routing; *give value first, then ask
  one question*), `skills/real_estate[_nepal].md` (market skill chosen by location country),
  `memory.md`, `summarize.md`. Prompts live in files, never inline.
- `tools.py`: strict search (hard budget/area; near matches labelled with what differs, never
  silently widened), `list_locations`, portfolio overview, details (`not_recorded` topics), compare,
  `send_property_photos`, viewing slots, appointments, leads, memory, handoff.
  `MARKETS` maps country → currency/timezone (Nepal Rs + lakh/crore, India ₹, Hong Kong HK$, USA $).
- **Writes are preview → customer yes → locked execution → receipt** (`actions.py`, `AgentAction`
  ledger): `prepare_viewing/cancellation/reschedule` create a preview; `confirm_pending_action`
  runs it only if the preview is from an earlier turn AND the customer's latest message is a plain
  yes. Listing row lock + slot/price re-check; a duplicate yes returns the stored receipt. The
  reply always quotes the receipt (deterministic template in `language.receipt_line`).
- `capabilities.py`: the ONE place tool access is decided (owner `AgentSettings` today; subscription
  plan tomorrow) + the CAN/CANNOT list in the prompt. `AgentSettings` (Settings → AI agent):
  bookings on/off, staff-approval mode, viewing hours, daily AI reply cap.
- Every agent reply is metered (`billing.meter.record_usage`, module `chatbot_ai`) for future plans.
- Staff takeover during a run → reply `suppressed`; every channel stays silent.
- Restaurant path: `ai_engine/booking_guard.py` blocks "table booked" claims without complete data
  and quotes the real booking code (fixes the 2026-06 false-confirmation screenshot).
- `dialogue.py`: deterministic turn state (a "hunxa" answers WHICH offer, photo request, "check again",
  long-press quote, customer back after hours) → binding TURN BRIEF + post-draft checks (repeated question,
  team promise without `request_team_followup`, photo claims without the photo tool).
- `ai_engine/vertical_guard.py`: restaurant and real-estate never leak into each other (output guard,
  memory cleaning); `ai_engine/signals.py` clears customer memory when an org changes business type.
- Staff actions in the dashboard are messaged to the customer and land in the agent's history
  (`realestate/appointment_notifications.notify_staff_change`).
- `vocab.py`: customer words → enums (jagga→land, kotha→room, ghar→house, shutter→retail, ktm→Kathmandu).
- `language.py`: deterministic reply language (Devanagari / Romanized Nepali / English / Chinese),
  sticky across neutral replies like "10000".
- `verifier.py`: every reference, confirmation code, money amount (any currency sign, lakh/crore/
  hajar, "/month") and any 4+ digit figure must appear in evidence (tool results, PORTFOLIO,
  knowledge, the customer's words). Tool *arguments* are not evidence. Booking/cancel claims need
  a successful tool call this turn.
- The live PORTFOLIO (all active listings, ≤40) is injected into the prompt every turn; tool
  results from the last 3 turns are carried in `AILog.context['tool_facts']`.
- Model: `AI_AGENT_MODEL` / `OPENAI_MODEL` = `deepseek-chat` via `OPENAI_BASE_URL=https://api.deepseek.com`
  (since 2026-10-04). Every chat call goes through `ai_engine/llm.py` (failover to OpenAI
  `LLM_FALLBACK_*`). Use `deepseek-chat`, not the thinking model: tool loops would need reasoning_content.
- `agent/tone.py` + `prompts/tone.md`: honorific register gate (one rewrite pass) and no em/en dashes
  in any chat reply (`AIService.process_message` sanitizes every vertical).
- Viewing reminders / missed-viewing follow-ups: `realestate/appointment_notifications.py` (beat, 5 min).
- If every reply fails: check DeepSeek balance (`GET https://api.deepseek.com/user/balance`) and the
  OpenAI fallback credits (a zero-credit key returns 402/429 on every call).
- **Live eval:** `python manage.py run_agent_evals [--cases RE-043 --repeat 5] [--report f.md]` runs
  the spec scenarios (`ai_engine/evals/scenarios.py`, from `kribaat_agent_harness_130_conversations.md`)
  against the real model on a throwaway tenant. Run it after any prompt/tool change.
- **Public site:** `realestate/public_site.py` serves `/realestate/properties` (+ sitemap.xml, robots.txt)
  server-rendered for SEO; ingress routes those paths to Django. Dashboard manager: `/realestate/listings`.
- **Listing photos:** `realestate/photo_storage.py` → Cloudflare R2 bucket `kribaat-media`, served at
  `media.kribaat.com` by `realestate/media_proxy.py` (old `pub-296eb79cd8404023a4b91caa9c0e6bd0.r2.dev` URLs still work), re-encoded JPEG ≤1600px, EXIF/GPS stripped.
  Falls back to the media-pvc if any `R2_*` setting is missing. WhatsApp sends them as image messages.
  r2.dev blocks Python's default user-agent (error 1010) — test with a browser/`facebookexternalua` UA.

**Brand:** `brand-memory.md` (repo root) is the source of truth for colours, fonts, voice and video style;
Tailwind tokens `kb-*`, `font-display` (Fraunces), `font-brand` (Hanken Grotesk).
**Showcase videos:** `apps/showcase` (Django admin, superusers only) → `/api/public/showcase/` →
kribaat.com "Watch the demo" + property site; files served from `media.kribaat.com/showcase/` (ranges).

## Frontend (`frontend/src/`)

- Routes in `App.tsx` under `OrganizationRequiredRoute`. HTTP only via `services/api.ts` (axios +
  JWT refresh). State: zustand (`store/auth.ts`) + react-query. i18n en / zh-CN / zh-TW.
- **Vertical gating:** `lib/verticals.ts` is the single source for which paths belong to which
  vertical; the sidebar (`layouts/DashboardLayout.tsx`) and the route guard both use it. A
  real-estate org never sees menu/bookings/inventory/coffee pass/lucky draw, and vice versa.
- **Money:** always `lib/money.ts` (`formatMoney(amount, listing.country || orgCountry)`), never a
  hard-coded `$`. Settings → *Market & currency* sets the primary location country; Settings →
  *AI agent playbook* edits the owner rules the agent follows.
- New sidebar features go inside an existing group, not as new top-level items.

## Conventions

- AHA + vertical slices: build a feature end to end (model → API → UI → tests); don't abstract
  until the third repeat. Validate at the boundary; never swallow errors silently.
- Every bug fix gets a regression test in the app's `tests/` package (the repo `.gitignore`
  ignores `test_*.py` outside `apps/*/tests/`).
- Never commit secrets, `.env*`, `*.pem`, `k8s/secrets.yaml`, `*.ps1`, `agent.md`.
- Pyright "objects/DoesNotExist unknown" warnings are expected (no Django stubs); ignore them.
- Known debt and pending features: `pending-work.md`.
