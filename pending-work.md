# Pending work — Kribaat real-estate / Nepal room rentals

Last updated: 2026-10-03. Everything listed under **Shipped** is live on kribaat.com.
Everything under **Pending** was requested but is not built yet. Start from the top.

## Shipped (2026-10-03)

**Agent (real-estate orgs only, `backend/apps/ai_engine/agent/`)**
- Tool-calling agent: search, property details, save lead, book/cancel viewing, my appointments,
  remember fact, escalate. Listing facts and actions come only from tools.
- Verification gate: every PROP reference, APT code and money amount must appear in tool results,
  knowledge, or the customer's own words. Booking/cancel claims need a successful tool this turn.
  One corrective retry, then trims unverifiable sentences, then an honest fallback (never a dead end).
- Prompt files: `soul.md`, `intent.md` (incl. "ask one warm question when unsure"),
  `skills/real_estate.md`, `skills/real_estate_nepal.md` (room rentals), `memory.md`, `summarize.md`.
- Market is data-driven from the org's primary location **country**: Nepal → Rs, lakh/crore,
  Asia/Kathmandu, Nepal skill; Hong Kong → HK$, Asia/Hong_Kong. 14-day calendar in the prompt;
  `book_viewing` rejects a date/weekday mismatch.
- Persistent memory (`AgentMemory`): owner playbook + per-customer facts + rolling summary
  (nightly Celery beat 15:30 UTC, and early when a chat exceeds 16 messages).
- Replies in the customer's language and script (Devanagari Nepali, Romanized Nepali, English).
- WhatsApp duplicate-delivery dedupe; cheap/student requests sort by price instead of inventing budgets.

**Dashboard**
- New Appointments page (`/realestate/appointments`): stats, Upcoming/Today/Past/All, search,
  status filter, confirm/complete/no-show/cancel dialogs, create dialog with validation, en/zh-CN/zh-TW.
- Properties and Leads show money per market (Rs with lakh/crore for Nepal).
- Settings: greeting now actually saves (was `greeting_message` vs `widget_greeting`), location
  address/timezone fields fixed, delete-location confirmation, primary location protected, real
  server errors shown, org validation.
- App refreshes the cached organization on load (stale business_type/name after a change).

**Security / data safety**
- Only owners can edit the org; org deletion removed from the API.
- Location delete is a soft delete; primary or last location cannot be removed (CASCADE used to
  wipe listings, leads and appointments).
- Channel credentials (WhatsApp/Instagram/Twilio) are owner-only; config cannot move orgs.
- Webhooks: unsigned WhatsApp/Instagram/Twilio posts are rejected when a secret is configured.
- Appointment create rejects another org's lead/property; state guards return 409.

**Prod data**: org "Kribaat Realestate" (`03b40fb0-…`) is real_estate, location Kathmandu Office
(Nepal, Asia/Kathmandu), 11 Nepal listings (rooms, flats, shutter, house, land), Nepal KB + 8 FAQs,
owner playbook memory. Restaurant data was replaced for this org. New OpenAI key in GitHub Secret +
cluster secret (the old key had zero credits).

## Shipped (2026-10-03, round 2) — agent grounding + admin control

Root causes fixed (prod chats: "jagga" → English "could you clarify?" loop; invented rooms at
"HK₨7,500"; `$` on Properties):
- Properties list API omitted `country` → dashboard fell back to USD. Edit dialog filled from that
  lightweight row (no description/address) → saving an edit would blank them. Both fixed.
- Agent: no view of the whole stock → added live PORTFOLIO in the prompt + `get_portfolio_overview`;
  search maps jagga/kotha/ghar/shutter (+ Devanagari, area aliases) and relaxes criteria instead of
  returning nothing; prompt rule "give value first, then one question".
- Language: shared detector labelled Romanized Nepali as English → deterministic Nepali detector,
  binding per-turn instruction, sticky for neutral replies ("10000").
- Gate: `₨`, `₹`, NRs, hajar, "/month" and bare 4+ digit figures now checked; tool arguments no
  longer count as evidence (a made-up max_price used to verify itself).
- Old Hong Kong summary in customer memory poisoned Nepal chats → `seed_nepal_portfolio --wipe`
  clears customer memory and archives old chats.
- Model: `AI_AGENT_MODEL=gpt-4.1-mini` (eval: gpt-4o-mini invented a listing feature and put a
  1.25-crore plot under "below 1 crore").
- Sidebar showed Inventory / Lucky Draw to real-estate orgs → `lib/verticals.ts` drives sidebar +
  route guard.
- Admin control without code: Settings → *Market & currency* (country → currency + timezone for
  dashboard AND agent; Nepal / India / Hong Kong / USA), property form market selector + live
  formatted price, Settings → *AI agent playbook* editor (`/api/v1/ai/playbook/`, owner-only).
- Prod data reseeded: 29 Nepal listings (rooms, flats, 9 land plots across 7 districts, houses,
  shops, office), NPR.

## Shipped (2026-10-03, round 3) — agent harness (kribaat_agent_harness spec) + photos

- Preview → confirm → receipt for bookings/cancellations/reschedules (`AgentAction` ledger, listing
  lock, slot + price re-check, idempotent duplicate "yes", one pending decision at a time).
- Viewing slots from owner settings; ownership check for cancel/reschedule (a code is not identity).
- Strict search with labelled near matches; `list_locations`; compare; `not_recorded` facts;
  photos; forget-my-preferences; capabilities list (no deposits/offers/leases/alerts/guarantees).
- Staff takeover mid-run suppresses the AI on every channel; restaurant false "booked" guard.
- Owner `AgentSettings` (bookings on/off, staff approval, hours, daily cap) + usage metering.
- Live eval: 45/45 scenarios, 57/57 on 3× critical repeats (gpt-4.1-mini). CI tests now blocking.
- Listing photos on Cloudflare R2 + agent sends them on WhatsApp.

## Shipped (2026-10-04, round 4): DeepSeek, respect gate, public site, reminders

- **LLM provider: DeepSeek** (`deepseek-chat`, OpenAI-compatible) with automatic failover to OpenAI
  (`apps/ai_engine/llm.py`): any provider error (no balance 402, 429, 5xx, timeout) retries the same
  request on the fallback; a provider down for credit/auth is skipped for 2 min. Keys: GitHub Secrets
  `OPENAI_API_KEY` (DeepSeek) + `LLM_FALLBACK_API_KEY` (OpenAI). Live eval on DeepSeek: 41/46.
- **Respect / tone gate** (`agent/tone.py` + `prompts/tone.md`): honorific register in Romanized and
  Devanagari Nepali (hajur/tapai, -nuhunchha/-nuhola), courteous English, 您 in Chinese. A low-register
  draft ("Aru sodhna cha?") gets one tool-less rewrite pass; safe phrase upgrades always applied.
  No em/en dashes in any chat message (house style, enforced for every AI reply).
- **Property save bug**: Nepal listings have no postal code and the API required one, so every edit
  failed ("Failed to save property"). state/postal_code optional; dashboard statuses match the API;
  field errors shown. Photos: drag & drop upload, drag to reorder / set cover, queued photos on create.
- **Public SEO site** `kribaat.com/realestate/properties` (Django SSR: JSON-LD, canonical, sitemap.xml,
  robots.txt, category + city landing pages, OG image). Every page funnels to WhatsApp with a
  pre-filled message naming the listing (or the visitor's needs). Views/WhatsApp clicks counted.
  Dashboard listing manager moved to `/realestate/listings`.
- **Django admin** listing manager: thumbnails, drag & drop photo manager, bulk publish/rented/sold.
- **Viewing reminders + missed-viewing follow-ups** (Celery beat every 5 min,
  `realestate/appointment_notifications.py`): ~1 h before, and 30 min after the slot if staff did not
  close it. WhatsApp only inside Meta's 24 h window, else email, else recorded honestly. The agent now
  sees each appointment's timing (a passed 11:00 slot is never "confirmed for today").
- **media.kribaat.com**: photos served by our ingress → `media_proxy` (authenticated R2 S3 API).

## Pending — product features (requested, not built)

1. **Landlord self-serve "rooms" product** (the subscription you described): landlord signs up,
   subscribes, adds rooms with photos, availability, rent, deposit, who-is-allowed (student /
   bachelor / family), water, parking, bathroom type. Needs explicit fields on `PropertyListing`
   (or a `Room` model), a landlord-friendly add-room form, and plan limits (rooms per tier).
2. **Edit an existing location's name/address in Settings** (market/country is now editable via
   *Market & currency*; other location fields still need an edit dialog).
3. **More markets**: add a country to `MARKET_OPTIONS` (frontend `lib/money.ts`) and `MARKETS`
   (`ai_engine/agent/tools.py`) — keep them in sync; optionally a market skill file.
4. **Nepali UI language** (`ne`) for the dashboard, plus Nepali in `LanguageService` so detection
   and fallback messages are Nepali.
5. **Property form fields for Nepal**: land area in ropani/aana/paisa/dam and bigha/kattha/dhur,
   road access (ft), lalpurja status. Today these live in features/description text.
6. **Notify the customer** when the dashboard confirms/cancels/reschedules an appointment
   (WhatsApp template), and owner WhatsApp alert when the AI books a viewing.
7. **Reschedule action** on the Appointments page (today it's cancel + create).
8. **Vertical gating on the API** (today the UI hides other-vertical modules; the APIs are still
   reachable by a member of the org, though data stays org-scoped).
9. **Customer memory viewer** on the lead/inbox page (facts + summary).
10. **Settings UI for AgentSettings** (bookings on/off, staff-approval mode, viewing hours, daily cap).
    The model + API-side reads exist; today it is edited in Django admin.
11. **Remaining spec scenarios**: 45 of 130 are executable live evals; add the rest (journeys
    RE-101–110, restaurant RT-111–130) and a restaurant tool-calling agent like the real-estate one.
12. **Optional CDN for media.kribaat.com**: the zone is in another Cloudflare account; turning the
    record to Proxied (orange cloud, SSL Full strict) adds Cloudflare caching in front of the cluster.
13. **WhatsApp template for reminders** outside the 24 h window (needs a Meta-approved UTILITY template);
    today those fall back to email or are recorded as not delivered.

## Pending — MCP server + website crawler (design only, needs your go/no-go)

Requested: MCP server (client + server architecture), crawler/scanner of the top property
websites, an autonomous 24/7 agent that brings leads back with the source URL so the user can
verify, plus deep crawling skills with terminal commands.

Constraints to decide first:
- **Terms of service**: most portals forbid automated scraping. Prefer official APIs, partner
  feeds, or listings the owners submit themselves.
- **Privacy**: harvesting people's phone numbers/names as "leads" for marketing falls under
  Nepal's Privacy Act 2075 (and Hong Kong's PDPO for HK). Collect public listing data (price, area,
  type, URL), not personal contact data, unless the person opted in.
- Respect robots.txt, rate-limit, identify the crawler, cache, and always store the source URL
  and fetch time so each result is verifiable ("found on <site>, checked <time>, please confirm").

Proposed design (to write as a REQUIREMENTS.md phase before coding):
- `mcp-crawler` service (Python, MCP SDK, HTTP/SSE transport): tools `search_market(area, type,
  budget)`, `get_listing(url)`, `watch(query)`; per-site adapters behind an allowlist; Redis queue;
  Postgres `market_listings` table with source_url, fetched_at, content hash (dedupe).
- Celery beat job for 24/7 watches; matches go to the landlord/agent as "market insights" in the
  dashboard and optionally WhatsApp, each with its source link.
- The chat agent gets a read-only `market_compare` tool (clearly labelled "from <site>, verify").
- Skill doc for crawling: robots.txt check, polite fetching, pagination, change detection, parser
  tests per site, failure alerts.

## Pending — housekeeping

- Pre-existing TypeScript errors in `PropertiesPage.tsx`, `services/api.ts`, and the `import.meta.env`
  typing (CI doesn't gate on tsc).
- Instagram webhook: 40 of the last 50 deliveries errored before today's change; check the
  Instagram app secret matches `META_APP_SECRET`.
- Rotate the OpenAI key that was pasted in chat once the demo is over.
