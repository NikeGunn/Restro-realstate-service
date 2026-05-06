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

### Phase 2 — NOT YET BUILT (deferred)
Models in spec but not yet implemented: `PurchaseOrder`, `PurchaseOrderItem`, `Recipe`, `RecipeIngredient`, `RecipeVersion`, `SalesImport`, `SupplierImport`. Services not yet built: `tolerance_engine.py`, `stock_engine.py` (mostly inlined into views.adjust for now — extract when receiving POs / recipes land), `recipe_engine.py`, `excel_parser.py`, `ai_engine.py` (Plane B's separate OpenAI engine), prompt files. Celery tasks not yet built (low-stock WhatsApp alert to owner, daily digest). Frontend pages not yet built: Purchase Orders, Recipes (with feasibility check), Excel import wizard with column mapping, Audit log viewer, Inventory AI chat panel.

### Phase 1 known limitations / debt
- StockEngine class not extracted; manual adjustments go through the view directly. When Phase 2 (POs, recipes) lands, refactor adjust + receive_po + consume_recipe into `services/stock_engine.py` with `_create_movement()` as the single creation point.
- ToleranceEngine is approximated inline in the InventoryItem serializer's `effective_stock` computation. Extract when recipe feasibility lands.
- No Celery tasks; signal does the alert creation synchronously. Move to Celery when WhatsApp owner alerts land.
- Audit log is created from views (`adjust` action only); other CRUD operations don't yet auto-log. Add a generic mixin or signals when adding more mutating endpoints.
- Pyright shows many warnings; this matches the rest of the codebase (no Django stubs). Don't chase them.
