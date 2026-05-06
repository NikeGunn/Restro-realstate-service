# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-tenant AI business chatbot platform ("Kribaat" / chatplatform) with two verticals — **Restaurant** and **Real Estate** — sharing one core. Production lives at `kribaat.com` and is deployed to a K3s cluster via ArgoCD GitOps. The repository contains three deployable artifacts: a Django backend, a React/Vite admin dashboard, and an embeddable vanilla-JS widget served by the backend at `backend/apps/widget/widget.js`.

The product spec is `agent.md` (gitignored locally but authoritative for scope decisions). It is strict about NOT building POS/CRM/payments/delivery features — keep changes inside the documented scope unless the user explicitly overrides.

## Common Commands

> **Always run this app via Docker.** Never use `python manage.py runserver` or `npm run dev` against the host directly — host Python / Node versions can drift from the container (Python 3.11 in the backend image vs. whatever is on the host) and silently mask bugs that production will hit. **Always run tests inside Docker too** (`docker-compose run --rm backend pytest ...`, `docker-compose run --rm frontend npm test`). A "host green / Docker red" gap has burned us before.

### Local development (docker-compose)
```bash
docker-compose up --build                                    # All services (db, redis, backend, celery, celery-beat, frontend)
docker-compose exec backend python manage.py migrate
docker-compose exec backend python manage.py createsuperuser
docker-compose exec backend python manage.py makemigrations <app>
```
Backend → http://localhost:18000 · Frontend → http://localhost:13000 · API docs → http://localhost:18000/api/docs/

**Host ports are deliberately shifted off the defaults** so this stack can run alongside sibling projects (e.g. `migalpha` on 5432/6379/8000). Container-internal ports stay at the standard values; only the host side moves. Override via env vars if needed: `HOST_DB_PORT` (default 15432), `HOST_REDIS_PORT` (16379), `HOST_BACKEND_PORT` (18000), `HOST_FRONTEND_PORT` (13000).

### Tests (run inside Docker)
```bash
docker-compose run --rm backend pytest                       # all backend tests (pytest-django)
docker-compose run --rm backend pytest apps/coupons -v       # single app
docker-compose run --rm frontend npm test                    # frontend (vitest)
```

### Backend (run inside `backend/` or via `docker-compose exec backend ...`)
```bash
python manage.py runserver 0.0.0.0:8000
python manage.py test                                        # Django test runner
python manage.py test apps.messaging.tests.TestClass.test_x  # Single test
pytest                                                       # pytest-django is also installed
celery -A config worker -l info
celery -A config beat -l info
```

### Frontend (`frontend/`)
```bash
npm run dev          # Vite dev server on :3000 with @ → ./src alias
npm run build        # Production build (no tsc — see note below)
npm run build:check  # tsc + vite build (use this to catch type errors)
npm run lint         # eslint, --max-warnings 0
```
Note: `npm run build` deliberately skips `tsc`. CI also doesn't gate on TypeScript errors. Run `npm run build:check` locally before pushing if you've touched types.

### Production / deployment
- **CI is the deploy mechanism.** Pushing to `main` triggers `.github/workflows/deploy.yml`, which builds Docker images, tags them with the short SHA, rewrites `image:` lines in `k8s/*/deployment.yaml`, commits the manifest update back to `main` ("🚀 Deploy: ..."), and ArgoCD auto-syncs within ~3 minutes. Do not manually edit image tags in `k8s/`.
- `redeploy.ps1` and `toggle-maintenance.ps1` are legacy SSH-based deploy tools for the pre-K8s VM at `43.152.233.234`. Do not use them for the production cluster — they bypass GitOps. They are gitignored (see `.gitignore`: `*.ps1`).
- Secrets are *not* in `k8s/secrets.yaml` (gitignored). They are pushed by the `deploy-secrets` job in CI via SSH from GitHub Secrets.

## Architecture

### Backend layout (`backend/`, Django 4.2 + DRF + Celery)
`config/` holds Django settings, `apps/` holds the domain. Apps are split into **core** and **vertical**:

- **Core**: `accounts` (User/Organization/Location/Role, JWT auth), `messaging` (unified `Conversation`/`Message` model + FSM, channel-agnostic), `ai_engine` (OpenAI integration, language detection, confidence scoring), `knowledge` (KnowledgeBase + FAQ), `handoff` (human takeover, AI-disable), `analytics`, `widget` (serves `widget.js` and the `/api/v1/widget/` public endpoints), `channels` (WhatsApp + Instagram via Meta Graph API + webhook handlers).
- **Verticals**: `restaurant` (menu, bookings), `realestate` (listings, leads, appointments). Verticals plug into core — they must NOT duplicate auth, messaging, or AI logic.

**Key cross-cutting invariants** (these are the "big picture" rules that span multiple files):

1. **One conversation model, many channels.** `apps.messaging.models.Conversation` is channel-agnostic. `Channel` enum is `website|whatsapp|instagram`. New channels add a row to `apps.channels` services + a webhook handler; they never fork the messaging model. State machine values: `new → ai_handling → awaiting_user → human_handoff | resolved | archived`.

2. **AI is grounded, not generative.** `apps.ai_engine.services.AIService` answers ONLY from `KnowledgeBase`/`FAQ`/vertical data. Below `AI_CONFIDENCE_THRESHOLD` (0.7, in settings) it must escalate to human handoff. Every AI response is logged to `AILog` with confidence + intent. When AI is uncertain, prefer handoff over a creative answer — this is a product rule, not a stylistic one.

3. **Human handoff disables AI.** When a conversation is in `HUMAN_HANDOFF`, the AI engine must NOT respond. The handoff app owns the conversation lock; respect it from any new code that produces messages.

4. **Knowledge resolution: location overrides organization.** Location-level data wins over org-level data when both exist. Anywhere you read knowledge for a conversation, scope by `(organization, location)` and apply that precedence.

5. **Multilingual.** AI replies in the user's detected language (English / Simplified Chinese / Traditional Chinese — see `LanguageChoice` in `apps/messaging/models.py` and `apps/ai_engine/language_service.py`). The detected language is persisted on `Conversation.detected_language`. Don't hard-code English in prompts.

6. **Plan gating** (`Organization.plan = basic|power`) is enforced at the API layer (DRF permission classes in `apps/accounts/permissions.py` and per-view checks). New gated features must add a check there, not in the frontend.

7. **Auth.** Custom user model `accounts.User` (UUID PK, email is `USERNAME_FIELD`). JWT via `rest_framework_simplejwt` with rotation + blacklist. Frontend stores tokens in zustand (`frontend/src/store/auth.ts`); `frontend/src/services/api.ts` axios interceptor handles 401 → refresh → retry transparently.

### URL surface
Routes are mounted in `backend/config/urls.py`. The two non-obvious ones:
- `/api/v1/widget/` — public, used by `widget.js` from any embedding site. CORS-permissive in dev; in prod CORS is restricted via `CORS_ALLOWED_ORIGINS`.
- `/api/webhooks/` — public Meta webhooks (WhatsApp/Instagram), no auth, signature-verified using `META_APP_SECRET`.

### Frontend layout (`frontend/`, React 18 + Vite + TS + Tailwind + Shadcn)
- `src/pages/` mirrors product surface (auth, dashboard, inbox, knowledge, alerts, analytics, settings, plus `restaurant/` and `realestate/` vertical pages). Routing is in `src/App.tsx` with three guards: `PublicRoute`, `ProtectedRoute`, `OrganizationRequiredRoute`. New authenticated pages should sit under `OrganizationRequiredRoute` so users without an org get redirected to `/setup-organization`.
- State: `zustand` for auth/org context (`src/store/auth.ts`), `@tanstack/react-query` for server state. Don't introduce Redux.
- HTTP: always go through `src/services/api.ts` (the axios instance with the refresh interceptor). Don't `fetch` directly.
- i18n: `react-i18next`, language files under `src/i18n/`. Mirror the backend's en / zh-CN / zh-TW.
- Path alias `@/` → `src/` (configured in `vite.config.ts` and `tsconfig.json`).

### Embeddable widget
The widget is **not** a separate npm package. It's a single static file at `backend/apps/widget/widget.js` served by Django's static pipeline. `apps/widget/views.py` handles its API (`/api/v1/widget/init/`, `/api/v1/widget/message/`). When changing the widget, you're editing one JS file — keep it framework-free.

### Infra (`k8s/`, ArgoCD)
- `k8s/argocd/application.yaml` is the ArgoCD `Application` pointing at this repo's `k8s/` directory.
- One Deployment per component: `backend`, `frontend`, `celery-worker`, `celery-beat`, plus StatefulSets for `postgres` and `redis`. Do NOT add `volumeClaimTemplates` status fields manually — recent commits show ArgoCD's `ignoreDifferences` is configured to skip those (see commits `3c9a932`, `b260df5`).
- `k8s/secrets.yaml` is gitignored. The CI `deploy-secrets` job creates the `chatplatform-secrets` Secret directly via `kubectl` over SSH.
- Image tags are rewritten by CI; do not edit them by hand.

## Conventions specific to this repo

- **`agent.md` scope lock is overridden for the inventory feature** (user authorized 2026-05-06). Inventory work proceeds; other off-scope features still require fresh authorization.
- **Don't hardcode prompts** — AI prompt templates live as files (referenced from `apps/ai_engine/`), not inline strings.
- **Don't commit secrets, `.env*`, `.pem`, or `k8s/secrets.yaml`** — `.gitignore` blocks the common cases but be deliberate.
- **`*.ps1` scripts are gitignored** (except `config.ps1.example`). Local-only deployment helpers; don't rely on them in CI or docs.
- **`agent.md`, `QUICK_REFERENCE.txt`, `SECURITY*.md`, `*-diagnostic.ps1`, `check_*.py` and similar debug scripts are gitignored** — when investigating, you may find such files locally; don't commit them.
- The repo path contains a space (`Restro & real estate`). Quote paths in shell commands.

## Inventory app — Plane B (resume notes)

The inventory module is the "sealed vault" admin counterpart to the public chatbot. The full design lives in `INVENTORY_CLAUDE_CODE_PROMPT_V2.md` (gitignored, ~1.5k lines, FAANG-grade spec). Read it before extending phase 2+.

### Dual-engine principle (memorize this)
- **Plane A (public)**: existing `apps/ai_engine/services.AIService`. Customer-facing on widget / WhatsApp / Instagram. Knows menus, hours, bookings, listings.
- **Plane B (admin)**: `apps/inventory/`. Owner-only. Knows stock, suppliers, costs, recipes.
- The ONLY bridge is `apps/inventory/firewall.InventoryContextFirewall`. Stateless, no DB, no inventory imports at module level. AIService.process_message calls `firewall.check()` immediately after language detection — if it returns True, deflect with a localized message and skip OpenAI entirely. Firewall must be import-safe; never add DB calls to it.

### Phase 1 — DONE (2026-05-06, all 80 backend tests pass, frontend build clean)
- `backend/apps/inventory/` scaffolded and registered in `INSTALLED_APPS` and `config/urls.py` at `/api/v1/inventory/`.
- Models (`models.py`): `InventoryCategory`, `Supplier`, `InventoryItem` (auto-SKU `INV-{4char}-{YYYYMMDD}-{seq}`, unit + sku immutable after create), `StockMovement` (append-only ledger; `clean()` enforces sign-by-type; `save()` raises on update), `StockAlert`, `InventoryAuditLog` (delete blocked). All tables prefixed `inv_`.
- Signals (`signals.py`): on StockMovement create → recompute `InventoryItem.current_stock` via `update()` (bypasses item save guard), then auto-create LOW_STOCK / NEGATIVE_STOCK alerts (no spam: only one open alert per item+type).
- Permissions: roles in this codebase are `owner` / `manager` only (no `admin`). Inventory **write** = `owner`; **read** = owner or manager. Checked via `apps/accounts/OrganizationMembership`.
- ViewSets (`views.py`): items (full CRUD + `/adjust/` action + `/dashboard/`), suppliers, categories, movements (read-only), alerts (read-only + resolve action), audit-log (read-only).
- Migration: `apps/inventory/migrations/0001_initial.py`.
- Tests (`apps/inventory/tests/`): `test_firewall.py` (26 cases en/zh-CN/zh-TW), `test_models.py` (10 cases), `test_security.py` (5 cases). Run: `pytest apps/inventory/tests/`.
- Surgical AIService patch: 1 import + 14-line firewall block at the top of `process_message`. Returns same shape as other code paths. Pre-existing `apps/ai_engine` tests still pass.

### Phase 1 frontend — DONE
- `frontend/src/services/inventory.ts` — typed axios wrapper for all inventory endpoints.
- Pages under `frontend/src/pages/inventory/`: `ItemsPage` (polished — dashboard cards, filters, create/edit dialog with unit-locked-after-create, stock adjustment dialog), `SuppliersPage`, `MovementsPage` (ledger with reversal styling), `InventoryAlertsPage`.
- Sidebar entries added in `DashboardLayout.tsx` after vertical nav: items, suppliers, movements, alerts.
- Routes wired in `App.tsx` under `OrganizationRequiredRoute` at `/inventory*`.
- i18n keys added to all three locale files under `inventory.*` and `nav.inventory*`.

### Phases 2 & 3 — DONE (2026-05-07, 133/133 backend tests pass, frontend production build clean)

**Models added** (`models.py`, migration `0002_purchaseorder_recipe_…`):
`PurchaseOrder` (auto `PO-{YYYYMMDD}-{org4}-{seq:04d}`, supplier locked once status leaves draft, order_number immutable), `PurchaseOrderItem`, `Recipe` (auto-bumped `version` field), `RecipeIngredient` (item + unit immutable after creation; unit must match item.unit), `RecipeVersion` (JSON snapshot per change), `SalesImport`, `SupplierImport` (file upload + status FSM).

**Services** (`apps/inventory/services/`):
- `tolerance_engine.py` — pure-arithmetic, dataclass-based; `effective_stock()` and `check_recipe_feasibility()`. Zero Django imports at module level.
- `stock_engine.py` — single creation point for all StockMovements via `_create_movement()`. Methods: `manual_adjustment`, `reverse_movement` (atomic, marks original via `update()` to bypass append-only guard), `receive_purchase_order_item` (auto-flips PO status to partial/received, queries siblings via fresh queryset to bypass any prefetch cache), `consume_recipe`, `apply_sales_import`, `apply_purchase_import`.
- `recipe_engine.py` — `calculate_batch` (yield_percent inflates required: required = qty × batches / (yield/100)), `suggest_batches`, `cost_of_batch`, `version_diff`.
- `excel_parser.py` — `.xlsx` (openpyxl) / `.xls` (xlrd) / `.csv` (csv). Fuzzy column detection via `COLUMN_SYNONYMS` + difflib cutoff 0.75. 30% error-row threshold causes import to abort with status=failed. Two-phase: `parse()` (no DB writes) and `resolve_item()` (SKU exact → fuzzy name).
- `ai_engine.py` — Plane B `InventoryAIEngine`. Loads prompts from `prompts/*.txt` (never inline). Pre-flight skips OpenAI when org has zero items. Confidence floor 0.70 → safe deflection. Every query writes an `InventoryAuditLog` row with action='ai_query'. Degrades gracefully when `OPENAI_API_KEY` empty.
- 3 prompt files: `prompts/inventory_query.txt`, `prompts/stock_alert.txt`, `prompts/daily_summary.txt`.

**Celery tasks** (`tasks.py`):
- `process_excel_import_task` — parses + applies via StockEngine, marks failed on >30% errors.
- `check_low_stock_task` — async low-stock check with `LOW_STOCK_ALERT_COOLDOWN_HOURS` cooldown; queues WhatsApp.
- `send_stock_alert_whatsapp_task` — sends alert to OWNER's phone via `apps.channels.whatsapp_service.WhatsAppService` (never to a customer conversation).
- `generate_daily_inventory_summary_task` — beat-scheduled 08:00 UTC daily, per org.
- `check_expiry_task` — beat-scheduled 07:00 UTC daily, creates EXPIRY alerts on perishables past their threshold.
- Beat schedule entries added to `config/settings.CELERY_BEAT_SCHEDULE`.

**API** (`views.py`, `serializers.py`, `urls.py`):
- `AuditLoggedMixin` — auto-logs create/update/destroy on every mutating ViewSet with before/after JSON snapshot + computed diff. Drop-in via class inheritance.
- New ViewSets: `PurchaseOrderViewSet` (+`receive`, +`cancel`), `RecipeViewSet` (+`calculate`, +`consume`, +`suggest_batches`, +`versions`, +`version-diff`), `SalesImportViewSet` & `SupplierImportViewSet` (+`preview`, +`commit`, +`status`), `InventoryAIViewSet` (+`query`, gated to `org.plan == 'power'`), `InventoryReportViewSet` (+`stock-health`, +`movement-timeline`, +`top-consumed`, +`variance`).
- New item actions: `effective-stock`, `movements`. New movement action: `reverse` (owner-only, requires reason ≥5 chars).
- Item `adjust` and movement `reverse` now route through StockEngine (the inline view-level logic from Phase 1 was migrated).
- All ViewSets enforce `InventoryOrgScopeMixin`. Cross-org access returns 404 (does not leak existence).
- Serializers expose `locked_fields: string[]` on Item, Supplier, PurchaseOrder, RecipeIngredient so the frontend can render `<LockedField>` correctly.

**Settings + deps**:
- `INVENTORY_SETTINGS` block in `config/settings.py` (tolerance defaults, file size, error threshold, alert cooldown, AI model, alert channels).
- `requirements.txt` adds `openpyxl>=3.1`, `xlrd>=2.0`, `python-dateutil>=2.8`.

**Tests** (`apps/inventory/tests/`):
- New: `test_tolerance_engine.py` (7 cases), `test_stock_engine.py` (9), `test_recipe_engine.py` (6), `test_excel_parser.py` (10), `test_api.py` (16 — covers PO create/receive/cancel, Recipe create/calc/consume/versions, imports upload + extension reject, reports, AI graceful degradation, cross-org isolation, audit log writes).
- Shared `conftest.py` with org/owner/manager/outsider/supplier/item/recipe/purchase_order fixtures.
- **94 inventory tests, 133 total backend tests, all green in Docker** (`docker compose exec backend pytest -v`).

**Frontend**:
- `recharts` added to `package.json`. Used for dashboard pie + line + horizontal-bar charts and report stack chart.
- Reusable components: `components/inventory/StockDisplay.tsx` (used everywhere stock surfaces; tolerance band in tooltip), `components/inventory/LockedField.tsx` (read-only display for immutable fields with reason).
- Service layer `services/inventory.ts` extended with all Phase 2/3 types and endpoints.
- Pages added under `pages/inventory/`: `InventoryDashboardPage` (KPIs + recharts), `PurchaseOrdersPage` (list/create/receive/cancel with multi-line dialog), `RecipesPage` (card grid + create/edit + real-time calculator with live feasibility + version history), `SalesImportPage` & `PurchaseImportPage` (3-step wizard: upload → preview with column-map and valid-% indicator → processing with progress poll → done with summary + error CSV), `InventoryReportsPage` (tabbed: stock by category, in/out timeline, variance table), `AuditLogPage` (filterable, expandable before/after diff, CSV export), `InventoryAIPage` (chat with confidence badges, suggestion chips, graceful 403 on non-power plan).
- All new routes wired in `App.tsx` under `OrganizationRequiredRoute`. Sidebar (`layouts/DashboardLayout.tsx`) has 11 inventory entries.
- Full i18n coverage in en/zh-CN/zh-TW under `inventory.*` (dashboard, po, recipes, import, reports, audit, ai sub-blocks) and `nav.inventory*`.
- `npm run build:check` — zero new inventory TS errors. `npm run build` — production bundle compiles clean.

### Phase 2/3 known limitations / debt
- WhatsApp owner-alert task uses a defensive lookup chain (`user.phone` → `user.whatsapp_number` → `org.phone`). If your `User` model uses a different field name, `tasks.py:send_stock_alert_whatsapp_task` will log and skip silently — adjust the lookup if you store phones elsewhere.
- The InventoryAI endpoint requires `org.plan == 'power'` AND a valid `OPENAI_API_KEY`. With an empty org (no items) the engine short-circuits before calling OpenAI and returns a clear "inventory is empty" message — confidence 0% in that case is correct, not a bug.
- Pyright shows many warnings (`Cannot access attribute "objects"` etc.); this matches the rest of the codebase (no Django stubs). Don't chase them.

### Future phases (4, 5, 6) — PROPOSALS ONLY, NOT SPEC

> **STOP. Read this before writing any code for Phase 4+.**
>
> `INVENTORY_CLAUDE_CODE_PROMPT_V2.md` ends at Part 7. **Everything in that file has been delivered through Phase 3.** The V2 spec defines no Phase 4, Phase 5, or Phase 6.
>
> The bullets below are **candidate scope** — possible directions the inventory module could grow. They are NOT authorised, NOT designed in detail, and NOT a build queue. Treat each phase as a fresh feature that requires:
> 1. Explicit user authorization (the same way `agent.md` scope was overridden for inventory on 2026-05-06).
> 2. A written design discussion before any model/migration/UI work begins — confirm fields, FSM, permissions, and acceptance tests with the user.
> 3. A new entry in `agent.md` if the proposed feature crosses into POS / CRM / payments / delivery territory (which is currently scope-locked).
>
> **DO NOT**: read this section and start implementing. **DO**: when the user says "start Phase 4", first ask which sub-items they actually want, in what order, and whether anything that smells like POS/CRM/payments/delivery is in or out.

#### Phase 4 candidates — Operations polish (low risk, in current scope)

These extend existing Phase 1-3 surfaces; no new domain concepts.

- **Multi-location stock split.** Today, `InventoryItem.location` is a single optional FK and `current_stock` aggregates across all movements regardless of location. Real chains need per-location stock per item. Proposal: introduce `LocationStock(item, location, current_stock, reorder_level_override)` as the per-location ledger projection, change the signal to `update_or_create` per `(item, location)`, surface a location selector on every Inventory page. Touches: models, signals, all serializers, all reports, frontend filters.
- **Barcode scanning UI.** Use the device camera (`navigator.mediaDevices` + a scanner library like `@zxing/browser`) to scan into the adjustment dialog and PO receive dialog. Frontend-only.
- **Stock-take / cycle-count workflow.** New `StockTake` model (org, location, started_at, completed_at, owner) with `StockTakeLine(item, system_count, counted, variance, notes)`. On commit → emit `adjustment` movements via StockEngine for each variance. Adds a guided "physical count" page.
- **Movement export.** Server-side CSV/XLSX export of `StockMovement` filtered by item / type / date range. Pair with the existing audit-log CSV download pattern.
- **Bulk item edit.** Multi-select in the Items list → bulk update reorder_level / supplier / category / is_active. Backend: a `bulk-update` action on `InventoryItemViewSet` that accepts `{ids: [], patch: {}}` and writes one audit-log row per item.
- **Tighter PO lifecycle.** `draft → sent` action that emails the supplier (PDF attached). PO PDF generation (server-side via `weasyprint` or similar). Currently POs are created and immediately receivable; many shops want to "send" first.
- **Per-location pricing.** Allow `unit_cost` and `selling_price` to vary by location. Either via a `LocationItemPricing` table or a JSON field on `InventoryItem`.

#### Phase 5 candidates — Forecasting & cost analytics (mid risk)

Read-only analytics on top of the existing ledger. No new mutating surfaces.

- **Reorder forecast.** For each item, compute average daily consumption over the last N days (excluding reversed movements), project days-of-cover, surface a "Items to reorder this week" page. Recharts area chart per item.
- **Supplier scorecards.** Per-supplier stats: average lead time (PO created → received), receive accuracy (% of PO lines where `quantity_received == quantity_ordered`), price-trend volatility. Powers a Supplier detail page.
- **Recipe profitability.** For recipes whose `output_item.selling_price` is set, compute margin = selling_price − cost_of_batch (per output unit). Rank recipes by margin and by volume. Surfaces the "drop these dishes / push these dishes" insight.
- **Waste analysis.** Slice `StockMovement.movement_type='waste'` by item, time bucket, location. Highlight outlier weeks.
- **AI-powered weekly insights.** New Plane B prompt + Celery task that runs every Monday and produces a one-paragraph "what to pay attention to this week" summary delivered via the existing WhatsApp owner channel. Extends `InventoryAIEngine` with an `insights()` method; no new external dependencies.

#### Phase 6 candidates — Plane A integration & multi-tenant ops (higher risk, must check scope-lock)

These touch the firewall or cross into POS/CRM/payments territory. Most require fresh `agent.md` authorization.

- **Bookings → recipe consumption.** When a restaurant booking is fulfilled, optionally auto-consume the recipe(s) for the dishes ordered. Touches Plane A (`apps.restaurant.bookings`) ↔ Plane B (`apps.inventory.services.stock_engine`). The bridge must remain one-directional (Plane A reads its own data, calls a narrow method on StockEngine; StockEngine must NOT call back into Plane A).
- **POS imports.** Pull sales rows from a third-party POS (Square, Toast, etc.) via webhook or polling and feed them through the existing `apply_sales_import` path. **THIS IS POS TERRITORY** — `agent.md` scope-locks POS by default. Get explicit user override before starting.
- **Supplier marketplace / e-procurement.** Catalog of items the supplier offers, online quoting, e-signature on POs. **CROSSES INTO PROCUREMENT/PAYMENTS**. Likely scope-locked. Confirm.
- **Per-org isolated AI fine-tuning.** Hourly job that distils each org's inventory + Q&A history into a JSON profile fed into the prompt. Improves answer quality for big orgs without leaking cross-org data. Stays inside Plane B; no scope concern, but adds OpenAI cost.
- **Mobile (PWA) shell** — install-to-homescreen, offline-tolerant Items + adjust pages for inventory clerks doing physical counts on the warehouse floor. Touches PWA manifest, service worker, IndexedDB queueing.

#### How to start any of the above

1. User says: *"Phase 4: do bulk item edit and movement export"* (or whatever subset).
2. Claude responds with a brief plan (models touched, migrations needed, test plan, frontend touchpoints) and asks the user to confirm.
3. Only after confirmation, Claude implements in slices using the same pattern as Phase 2/3 (TaskCreate per slice, Docker pytest after each, frontend `npm run build:check` at the end).
4. CLAUDE.md gets updated to move the implemented bullets out of "Future phases" and into a new dated `### Phase 4 — DONE` block.

If the user asks for "Phase 4" without specifying scope, Claude must NOT pick from this list arbitrarily. Ask which bullets, in which order. The list is unordered on purpose.
