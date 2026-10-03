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

## Pending — product features (requested, not built)

1. **Landlord self-serve "rooms" product** (the subscription you described): landlord signs up,
   subscribes, adds rooms with photos, availability, rent, deposit, who-is-allowed (student /
   bachelor / family), water, parking, bathroom type. Needs explicit fields on `PropertyListing`
   (or a `Room` model), a landlord-friendly add-room form, and plan limits (rooms per tier).
2. **Edit an existing location in Settings** (name, country, timezone). Today only Django admin
   can change country/timezone, and the country drives the whole market.
3. **Country/market picker in Settings** (Nepal / Hong Kong / other) so the admin sets the market
   in the UI rather than per location.
4. **Nepali UI language** (`ne`) for the dashboard, plus Nepali in `LanguageService` so detection
   and fallback messages are Nepali.
5. **Property form fields for Nepal**: land area in ropani/aana/paisa/dam and bigha/kattha/dhur,
   road access (ft), lalpurja status. Today these live in features/description text.
6. **Notify the customer** when the dashboard confirms/cancels/reschedules an appointment
   (WhatsApp template), and owner WhatsApp alert when the AI books a viewing.
7. **Reschedule action** on the Appointments page (today it's cancel + create).
8. **Owner playbook editor** in the dashboard (AgentMemory owner facts); today set via shell/admin.
9. **Customer memory viewer** on the lead/inbox page (facts + summary).

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
