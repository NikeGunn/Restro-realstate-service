# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-tenant AI business chatbot platform ("Kribaat" / chatplatform) with two verticals — **Restaurant** and **Real Estate** — sharing one core. Production lives at `kribaat.com` and is deployed to a K3s cluster via ArgoCD GitOps. The repository contains three deployable artifacts: a Django backend, a React/Vite admin dashboard, and an embeddable vanilla-JS widget served by the backend at `backend/apps/widget/widget.js`.

The product spec is `agent.md` (gitignored locally but authoritative for scope decisions). It is strict about NOT building POS/CRM/payments/delivery features — keep changes inside the documented scope unless the user explicitly overrides.

**`REQUIREMENTS.md`** (repo root, committed) is the authoritative **design spec for the next 6 authorized phases** — CRM Lite, Lucky Draw, Menu updates, Drink/Cocktail formulas, AI Content Studio, and Credit/Usage Billing (plus a prerequisite `common` infra phase). It is hardened against the real codebase and the Tencent/ArgoCD pipeline. **It is design only — do not start coding any of those phases until the user explicitly says "start Phase N".** The CRM phase is an authorized scope override of `agent.md`'s no-CRM rule (user-authorized 2026-05-31).

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

**Dependency auto-sync.** The frontend container has an entrypoint (`frontend/docker-entrypoint.sh`) that hashes `package.json` + `package-lock.json` on every start and reruns `npm install` if the hash differs from the marker stored in `node_modules/.deps.hash`. So the workflow for adding a library is:

1. Edit `frontend/package.json` on the host (add the dep + version), OR run `docker compose exec frontend npm install <pkg>` (writes both files).
2. Restart the frontend container: `docker compose restart frontend` (or just stop+start the stack).
3. The entrypoint detects the hash change, runs `npm install`, updates the marker, and starts Vite. No manual `exec` step needed.

The `node_modules` lives in a **named volume** (`frontend_node_modules`), not anonymous, so it survives `docker compose down`. Only `docker compose down -v` (which `kribaat-down.ps1 -Wipe` runs) drops it — and even then the entrypoint rehydrates on next start.

### Production / deployment (Tencent Cloud K3s + GitHub Actions → ArgoCD)
The cluster runs on **Tencent Cloud**. The deploy contract is: **you `git push` to `main`, ArgoCD does the rest.** Never `kubectl`, SSH the bastion, or edit image tags by hand for a routine deploy.

- **CI is the deploy mechanism** (`.github/workflows/deploy.yml`, 5 jobs in order):
  1. `test` — backend `manage.py test` + frontend `npm run build` on GitHub runners. **⚠️ Runs with `|| true` / `continue-on-error` → failing tests do NOT block the deploy.** Treat "tests green" as a discipline you enforce **locally in Docker before pushing** — CI will not catch a regression for you.
  2. `build` — builds `*/Dockerfile.prod`, pushes to **Docker Hub** (`${DOCKER_USERNAME}/chatplatform-backend` + `-frontend`), tagged short-SHA + `latest`, with registry build cache.
  3. `update-manifests` — `sed`-rewrites `image:` lines in `k8s/{backend,frontend,celery-worker,celery-beat}/deployment.yaml` + `k8s/backend/migrate-job.yaml` to the new SHA and commits back to `main` ("🚀 Deploy: ..."). **Do not hand-edit those tags — the bot owns them.**
  4. `deploy-secrets` — SSHes the Tencent bastion (`K8S_SERVER_IP`/`K8S_SERVER_USER`/`K8S_SSH_KEY`), recreates the `chatplatform-secrets` Secret from GitHub Secrets, `kubectl rollout restart backend celery-worker celery-beat`, then re-applies `k8s/argocd/application.yaml` (drift guard). **This is the only path for secrets into the cluster.**
  5. `security-scan` — Trivy (non-blocking).
- **ArgoCD** runs in-cluster, watches the repo's `k8s/` path (`recurse: true`, excludes `argocd/*` + `kustomization.yaml` → **plain manifests, not Kustomize**), auto-syncs ~3 min (`prune`, `selfHeal`, `ServerSideApply`), runs the **PreSync `migrate-job`** before Deployments roll, and **ignores `/spec/replicas` drift** (so `kubectl scale` survives a sync).
- **Where new config goes:** non-secret env → `k8s/configmap.yaml` (`chatplatform-config`, committed → ArgoCD applies). Secret env → a GitHub Secret **and** a new `--from-literal=` line in the `deploy-secrets` job. (`OPENAI_MODEL: gpt-4o-mini` lives in the configmap and is read by chatbot Plane A — don't repurpose it; add new keys for new features.)
- **Images come from Docker Hub** (not Tencent TCR). Mirroring to TCR is a possible future infra change if Docker Hub pull limits/latency ever bite — out of scope unless raised.
- `redeploy.ps1` / `toggle-maintenance.ps1` are legacy SSH tools for the pre-K8s VM (`43.152.233.234`). **Do not use them** — they bypass GitOps and are gitignored (`*.ps1`).
- Secrets are **not** in `k8s/secrets.yaml` (gitignored) — only the `deploy-secrets` job creates `chatplatform-secrets`.
- **Migrations must be forward-only/additive** (new tables, nullable/defaulted columns, new enum *values*). The PreSync migrate-job runs before a `RollingUpdate maxUnavailable:0` rollout, so the still-running old pod must be able to query the post-migration schema — no drops/renames in the same release as code that reads them.

## Architecture

### Backend layout (`backend/`, Django 4.2 + DRF + Celery)
`config/` holds Django settings, `apps/` holds the domain. Apps are split into **core** and **vertical**:

- **Core**: `accounts` (User/Organization/Location/Role, JWT auth), `messaging` (unified `Conversation`/`Message` model + FSM, channel-agnostic), `ai_engine` (OpenAI integration, language detection, confidence scoring), `knowledge` (KnowledgeBase + FAQ), `handoff` (human takeover, AI-disable), `analytics`, `widget` (serves `widget.js` and the `/api/v1/widget/` public endpoints), `channels` (WhatsApp + Instagram via Meta Graph API + webhook handlers), `coupons` (admin-managed promo codes that grant an **org plan tier** for N days — **not** customer discounts; see `apps/coupons/models.py`).
- **Verticals**: `restaurant` (menu, bookings), `realestate` (listings, leads, appointments). Verticals plug into core — they must NOT duplicate auth, messaging, or AI logic.
- **Admin module**: `inventory` (Plane B — owner-only stock/suppliers/recipes/POs; full design history in the `### Inventory app` / `### Phase N — DONE` blocks below).
- **Shared infra: `common` (Phase 0 — DONE).** `apps/common/` holds the cross-cutting machinery promoted from inventory: `OrgScopeMixin` + `AuditLoggedMixin` (`mixins.py`), `IsOrgMember`/`IsOrgOwner` (`permissions.py`), public throttle classes (`throttling.py`), the Redis idempotency helper (`idempotency.py`), shared audit helpers (`utils.py`), and the opt-in object-storage hook (`storage.py`). No tables, no URL mount. See the `### Phase 0 — DONE` block below.
- **Planned expansion (design only — see `REQUIREMENTS.md` at repo root):** `crm`, `lucky_draw`, `content_studio`, `billing`. **`REQUIREMENTS.md` is the authoritative spec for these phases. Do not start building them until the user says "start Phase N".**

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

### Infra (`k8s/`, ArgoCD on Tencent Cloud)
- `k8s/argocd/application.yaml` is the ArgoCD `Application` pointing at this repo's `k8s/` directory (`recurse: true`, excludes `argocd/*` + `kustomization.yaml` → **plain manifests, not Kustomize**; new manifests are just valid YAML dropped under `k8s/`).
- One Deployment per component: `backend`, `frontend`, `celery-worker`, `celery-beat`, plus StatefulSets for `postgres` and `redis`. Do NOT add `volumeClaimTemplates` status fields manually — ArgoCD's `ignoreDifferences` is configured to skip those (commits `3c9a932`, `b260df5`).
- ArgoCD `ignoreDifferences` also covers Deployment `/spec/replicas` — so `kubectl scale` is honored and not reverted on the next sync.
- **Media storage is a 5Gi `ReadWriteOnce` `media-pvc` and the backend is pinned to `replicas: 1` *because of it*** (`k8s/backend/pvc.yaml`, `deployment.yaml`). User uploads / generated images write to `/app/media`. **To scale the backend past 1 replica you must first move media to object storage** (Tencent COS `ap-hongkong` or R2 via `django-storages` + `USE_OBJECT_STORAGE=true`) — see `REQUIREMENTS.md` § Phase 0 / Cross-Cutting › Media & Storage. Don't bump replicas while media is on the RWO PVC.
- `k8s/secrets.yaml` is gitignored. The CI `deploy-secrets` job creates the `chatplatform-secrets` Secret directly via `kubectl` over SSH from the Tencent bastion.
- Image tags are rewritten by CI; do not edit them by hand. Images live on **Docker Hub** (`${DOCKER_USERNAME}/chatplatform-*`).
- `k8s/tests/` holds the cluster test suite (commit `dfe56c5`); `k8s/cert-manager/` + `ingress.yaml` front TLS via Traefik.

## Conventions specific to this repo

- **`agent.md` scope lock is overridden for the inventory feature** (user authorized 2026-05-06). Inventory work proceeds; other off-scope features still require fresh authorization.
- **Don't hardcode prompts** — AI prompt templates live as files (referenced from `apps/ai_engine/`), not inline strings.
- **Don't commit secrets, `.env*`, `.pem`, or `k8s/secrets.yaml`** — `.gitignore` blocks the common cases but be deliberate.
- **`*.ps1` scripts are gitignored** (except `config.ps1.example`). Local-only deployment helpers; don't rely on them in CI or docs.
- **`agent.md`, `QUICK_REFERENCE.txt`, `SECURITY*.md`, `*-diagnostic.ps1`, `check_*.py` and similar debug scripts are gitignored** — when investigating, you may find such files locally; don't commit them.
- The repo path contains a space (`Restro & real estate`). Quote paths in shell commands.

## `common` app — Phase 0 shared infrastructure

### Phase 0 — DONE (2026-06-01, 214/214 backend tests pass, frontend prod build clean)

The prerequisite `common` library app (REQUIREMENTS.md § Phase 0). Pure cross-cutting machinery, **promoted from the proven inventory patterns** — no new mechanisms invented. **No models/tables, no migrations, no URL mount** → ArgoCD PreSync migrate-job is unaffected.

**`backend/apps/common/`** (registered first in `INSTALLED_APPS`):
- `mixins.py` — **`OrgScopeMixin`** (generalized from `inventory/mixins.py`: queryset scoped to membership orgs; optional `?organization=`/`?location=` narrowing with membership check; cross-org object lookup → 404; `perform_create` requires owner of the payload's org; `_save_with_creator` passes `created_by` only if the model has that field). **`AuditLoggedMixin`** (generalized from `inventory/views.py`: create/update/destroy → before/after JSON + diff; **audit sink is pluggable via `audit_log_model` / `get_audit_log_model()`**; org resolved via a fallback chain item→stock_take→recipe→customer→campaign→job; audit failures swallowed).
- `permissions.py` — **`IsOrgMember`** (read = owner|manager, write = owner) and **`IsOrgOwner`** (owner-only, all methods). Plus exported helpers `user_role_in_org` / `user_has_any_owner_membership` / `user_has_any_membership`.
- `throttling.py` — `PublicBurstThrottle` (`public_burst`), `PublicSustainedThrottle` (`public_sustained`), `PublicFormThrottle` (`public_form`). Rates added to `settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']` (60/min, 600/hour, 10/min). **No global default throttle class → authenticated views unaffected.**
- `idempotency.py` — `claim(key, ttl)` / `idempotent(key, ttl)` (atomic Redis `cache.add()` SET-NX; returns False on replay) + `release(key)`. **Fails OPEN on cache outage** (returns True, never 500s the public path; DB uniqueness is the real backstop).
- `storage.py` + settings — opt-in object storage. `settings.USE_OBJECT_STORAGE` (env, **default False**) gates a `STORAGES` block pointing at `storages.backends.s3.S3Storage` (Tencent COS `ap-hongkong` / Cloudflare R2). **OFF by default → dev + current prod keep `FileSystemStorage` + media-pvc, zero cluster change.** Non-secret S3 keys (`S3_BUCKET/ENDPOINT_URL/REGION/CDN_DOMAIN`) → configmap; secret keys (`S3_ACCESS_KEY_ID/SECRET_ACCESS_KEY`) are GitHub Secrets created with dummy values but **NOT yet wired into `deploy.yml`** (the two-edit wiring is deferred until a bucket is provisioned — see REQUIREMENTS.md § Credentials).
- `utils.py` — `client_ip` / `model_to_dict` / `diff` (the audit helpers, promoted verbatim).

**Backward-compat (the key safety property):** inventory's `InventoryOrgScopeMixin` is now a thin subclass of `OrgScopeMixin`; `IsInventoryAdmin` subclasses `IsOrgMember`; inventory's `AuditLoggedMixin` subclasses the common one with `audit_log_model = InventoryAuditLog`; the old private helper names (`_client_ip`/`_model_to_dict`/`_diff`) are aliases to `common.utils`. **All 151 inventory tests still pass unchanged.**

**Deps** (`requirements.txt`): `django-storages[s3]>=1.14`, `boto3>=1.34`, `phonenumbers>=8.13`, `qrcode[pil]>=7.4` (the last two are pre-installed for Phase 1/2; storage code is import-safe without storages/boto3).

**Tests** (`apps/common/tests/`, **24 — spec minimum was 8**): `test_org_scope.py` (member/outsider/manager visibility, cross-org `?organization=` → 403, cross-org retrieve → 404, owner-only create), `test_throttling.py` (11th `public_form` request → 429; distinct IPs independent), `test_idempotency.py` (claim/replay, alias, fail-open on cache error, release-then-reclaim), `test_permissions.py` (`IsOrgMember`/`IsOrgOwner` matrix + inventory-alias subclass assertions). `conftest.py` mirrors inventory's fixtures and reuses the real `InventoryItem`/`InventoryAuditLog` (no throwaway test model). **Full suite: 214 passed in Docker.**

### Phase 0 known limitations / debt
- The object-storage path is settings-gated and **never exercised in tests** (tests run with `USE_OBJECT_STORAGE=false`). Before enabling it in prod, provision the COS/R2 bucket, set the configmap keys, swap the dummy `S3_ACCESS_KEY_ID`/`S3_SECRET_ACCESS_KEY` GitHub Secrets for real values, **and** add their `--from-literal=` lines to the `deploy-secrets` job in `deploy.yml` (the one manual repo edit object storage needs). Only then is raising backend `replicas` past 1 safe.
- A pre-existing `STATICFILES_STORAGE` deprecation warning surfaces in test output — it's from the legacy `STATICFILES_STORAGE` setting line (not Phase 0); left untouched to avoid scope creep.

## `crm` app — Phase 1 CRM Lite

### Phase 1a (backend) — DONE (2026-06-01, 267/267 backend tests pass)

Consent-compliant customer database mounted at **`/api/v1/crm/`**. Authorized scope override of `agent.md`'s no-CRM rule (2026-05-31). Builds on Phase 0 `common`. **Frontend is Phase 1b (not yet built).**

**Models** (`models.py`, migration `0001` + data migration `0002`, all tables `crm_*`, UUID PKs):
- `CRMCustomer` — partial unique constraints `uniq_crm_org_phone` / `uniq_crm_org_email` (only when non-null/non-empty). Denormalized **`birthday_month`** (indexed) + **`visit_count`** for cheap segments. `save()` normalizes phone→E.164 (HK default, via `customer_service.normalize_phone`), lowercases email, derives `birthday_month`, defaults `whatsapp_number`. Indexes on `(org, consent_status)`, `(org, source)`, `(org, birthday_month)`, `(org, last_visit_date)`.
- `CRMTag` (+ 7 seeded system tags) · `CRMCustomerTag` (M2M through, unique `(customer,tag)`) · `CRMInteraction` (append-only, `save()` blocks updates) · `CRMConsent` (append-only & immutable; withdrawal = new row) · `CRMSegment` (JSON `filter_rules`).

**Services** (`services/`):
- `customer_service.py` — `get_or_create_customer` (merge-by-identity: phone then email, `select_for_update` + IntegrityError fallback for concurrency), `normalize_phone` (E.164/HK, never raises), `merge_customers` (re-points interactions/consent/tags/lucky-draw, **releases the duplicate's unique phone/email before backfilling** the primary to avoid constraint collision with the soft-deleted row, then `is_active=False`).
- `interaction_service.py` — `log_interaction` (append row, bump `visit_count` for booking/walk_in via `F()`, auto-apply `frequent_customer` at `CRM_FREQUENT_THRESHOLD`=5).
- `consent_service.py` — `record_consent` (append + recompute status: given→GIVEN, first refusal→REFUSED, refusal-after-given→WITHDRAWN, sets `opt_out_timestamp`), **`has_marketing_consent(customer, channel)` — THE gate every WhatsApp push must call.**
- `segment_service.py` — **DSL→Q compiler. Whitelisted field/op maps, NEVER eval/raw SQL** (unknown field/op → `ValidationError`). Relative dates (`-90d`) resolved server-side. `evaluate_segment` / `preview_count` / `refresh_counts`.

**API** (`views.py`, `OrgScopeMixin` + `IsOrgMember` read / `IsOrgOwner` write): `CRMCustomerViewSet` (CRUD + `tags`/`interactions`/`consents`/`merge` actions), `CRMTagViewSet` (system tags block delete/rename), `CRMInteractionViewSet` (RO), `CRMConsentViewSet` (RO + `record`), `CRMSegmentViewSet` (CRUD + `preview`/`customers`/`ready-to-engage` — the last filters to `consent_status='given'`). Querysets prefetch tags (`Prefetch('customer_tags'→select_related('tag'))`) to kill N+1. Cross-org → 404.

**Signals** (`signals.py`, lazy-connected in `apps.py::ready()`, one-directional, failure-safe): Org `post_save` (created) → seed 7 system tags + default "All consenting customers" segment. `restaurant.Booking` `post_save` (CONFIRMED/COMPLETED) → upsert customer + log booking interaction (COMPLETED sets `last_visit_date`); gated `CRM_AUTO_SYNC_BOOKINGS`. `messaging.Conversation` `post_save` (created, whatsapp/instagram) → upsert + log message; gated `CRM_AUTO_SYNC_CONVERSATIONS`. **Every receiver wraps work in try/except — never blocks the originating save.** No module-level imports of restaurant/messaging.

**Celery** (`tasks.py`, 3 beat entries appended to settings): `refresh_segment_counts_task` (02:00), `refresh_birthday_tag_task` (00:30 — syncs `birthday_this_month` off the indexed column), `refresh_inactive_tag_task` (01:00 — `CRM_INACTIVE_DAYS`=90).

**Settings**: `CRM_AUTO_SYNC_BOOKINGS`/`CRM_AUTO_SYNC_CONVERSATIONS` (default True), `CRM_FREQUENT_THRESHOLD` (5), `CRM_INACTIVE_DAYS` (90). Admin: all 5 models registered; append-only/consent models have add/change(/delete) locked; JSON rendered via `_pretty_json`.

**Tests** (`apps/crm/tests/`, **53 — spec minimum was 28**): `test_models` (8: partial-unique, append-only, birthday_month, cross-org phone OK), `test_customer_service` (8: E.164/HK, dedupe by phone/email, backfill, merge, cross-org reject), `test_segment_dsl` (10: every op, OR logic, relative date, tags, **unknown field/op + injection rejected, no eval**), `test_consent` (6: refusal vs withdrawal, gate, opt-out ts), `test_api` (11: CRUD, manager RO, cross-org 404, preview, ready-to-engage consent filter, system-tag delete block, merge), `test_signals` (7: org seeding, booking/conversation sync, pending/website skipped, **failure-doesn't-break-save**), `test_permissions` (4). **Full suite 267/267 green in Docker.**

### Phase 1a known limitations / debt
- Frontend (`pages/crm/*`, `services/crm.ts`, sidebar CRM group, i18n) is **not built** — that's Phase 1b. The API is live and tested.
- `merge_customers` soft-deletes the duplicate (`is_active=False`) after nulling its phone/email so the primary can claim them; the duplicate row is retained for audit (never hard-deleted).
- A no-org user gets **403** (not empty 200) on CRM endpoints — `IsOrgMember` requires membership. Intentional; matches inventory.

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
- All new routes wired in `App.tsx` under `OrganizationRequiredRoute`.
- Sidebar (`layouts/DashboardLayout.tsx`) uses a typed `NavItem = NavLeaf | NavGroup` model. Inventory is a single collapsible **group** (`inventoryGroup`) whose children are the 11 sub-pages. The group auto-expands when the route starts with `/inventory`, and user expand/collapse state persists to `localStorage` under `sidebar.groupState.v1`. **Future Phase 4-6 inventory features MUST add a new `NavLeaf` to `inventoryGroup.children`, not a new top-level sidebar entry** — this keeps the top-level sidebar from growing beyond ~10 items as the inventory module expands.
- Full i18n coverage in en/zh-CN/zh-TW under `inventory.*` (dashboard, po, recipes, import, reports, audit, ai sub-blocks) and `nav.inventory*`.
- `npm run build:check` — zero new inventory TS errors. `npm run build` — production bundle compiles clean.

### Phase 2/3 known limitations / debt
- The InventoryAI endpoint requires `org.plan == 'power'` AND a valid `OPENAI_API_KEY`. With an empty org (no items) the engine short-circuits before calling OpenAI and returns a clear "inventory is empty" message — confidence 0% in that case is correct, not a bug.
- Pyright shows many warnings (`Cannot access attribute "objects"` etc.); this matches the rest of the codebase (no Django stubs). Don't chase them.

### Phases 4 & 5 — DONE (2026-05-07, 153/153 backend tests pass, frontend production build clean)

**New models** (migrations `0003`, `0004`, `0005`):
- `LocationStock(item, location, current_stock, reorder_level_override)` — per-location ledger projection. Postgres-friendly partial unique constraints split null vs non-null location buckets (`uniq_location_stock_item_location` + `uniq_location_stock_item_null_location`). `InventoryItem.current_stock` stays as the **org-wide aggregate** (sum of all `LocationStock` rows) for back-compat with every existing reader. Migration `0003` includes an idempotent backfill that replays historical movements.
- `StockTake` + `StockTakeLine` — guided cycle-count workflow. Commit emits one ADJUSTMENT movement per variance via StockEngine.
- `LocationItemPricing(item, location, unit_cost, selling_price)` — per-location override.
- `PurchaseOrderEmail` — audit trail for PO sends.
- `PurchaseOrder.sent_at` + `sent_to_email` fields.

**Signal rewrite** (`signals.py`): `recompute_item_stock` now (1) updates the per-location `LocationStock` row, (2) recomputes the org-wide aggregate, (3) emits per-location LOW_STOCK / NEGATIVE_STOCK alerts.

**New services**:
- `services/stock_take_engine.py` — `StockTakeEngine.commit()` routes variances through StockEngine.
- `services/po_send.py` — `render_po_pdf()` (ReportLab; falls back to plain text if missing) + `send_po()` (DRAFT → SENT, attaches PDF, dispatches via Django's `EmailMessage`, records `PurchaseOrderEmail`).
- `services/analytics.py` — Phase 5 reads: `reorder_forecast`, `supplier_scorecards`, `recipe_profitability`, `waste_analysis`. All read-only, no mutations.
- `InventoryAIEngine.insights()` — weekly Plane B summary; falls back to deterministic digest when `OPENAI_API_KEY` is empty.
- New prompt: `prompts/weekly_insights.txt`.

**Celery**:
- `generate_weekly_insights_task` — Monday 08:00 UTC beat schedule, per org. Uses existing WhatsApp owner channel.

**API** (`views.py`, `serializers.py`, `urls.py`):
- New ViewSets: `StockTakeViewSet` (+`commit`, +`cancel`), `LocationStockViewSet` (read-only), `LocationItemPricingViewSet`.
- New actions: `InventoryItemViewSet.bulk_update` (whitelisted patch, owner-only, one audit row per item), `InventoryItemViewSet.location_stocks`, `StockMovementViewSet.export` (CSV streaming), `PurchaseOrderViewSet.send` + `pdf`.
- New report endpoints under `InventoryReportViewSet`: `reorder-forecast`, `supplier-scorecards`, `recipe-profitability`, `waste-analysis`, `weekly-insights`.
- `AuditLoggedMixin._audit` now resolves `instance.organization` via fallback chain (item.organization, stock_take.organization) so it works for models that aren't directly org-scoped.
- Serializer for `PurchaseOrder` now exposes `sent_at`, `sent_to_email`.

**Frontend**:
- New pages under `pages/inventory/`: `StockTakePage` (create with all-active-items helper, in-place counted edit, commit/cancel), `Phase5ReportsPage` (tabbed: forecast / suppliers / margin / waste, plus weekly-insight banner at top), `LocationPricingPage` (CRUD).
- New component: `components/inventory/BarcodeScanner.tsx` — uses native `BarcodeDetector` API (Chromium); falls back to manual entry if unavailable. Wired into `ItemsPage` barcode field.
- `MovementsPage` gains an Export CSV button that downloads via the new endpoint.
- `PurchaseOrdersPage` gains a Send (draft only) button that emails the supplier with a PDF attachment, plus a per-row PDF download icon.
- `services/inventory.ts` extended with all new endpoints + Phase 5 typed wrappers.
- Sidebar (`DashboardLayout.tsx`): three new `NavLeaf` entries inside the existing inventory group — `inventoryStockTake`, `inventoryAnalytics`, `inventoryLocationPricing`. (No new top-level entries — keeps the sidebar compact per the existing convention.)
- i18n: full coverage in en/zh-CN/zh-TW under `inventory.stockTake.*`, `inventory.analytics.*`, `inventory.pricing.*`, `nav.inventoryStockTake|Analytics|LocationPricing`, plus `common.commit|item|location` and `inventory.po.send|sent`.

**Tests** (`apps/inventory/tests/`):
- New: `test_location_stock.py` (7 cases — single-location, multi-location split, NULL bucket, reversal, alert tagging, backfill invariant), `test_phase4_5.py` (13 cases — movement export, bulk edit (allowed + rejected fields), stock-take commit, location pricing CRUD, PO send + PDF, all 5 Phase-5 reports including weekly insights graceful degradation).
- **153 total backend tests, all green in Docker** (`docker compose exec backend pytest`).
- `npm run build:check` shows zero new TS errors in inventory files; `npm run build` produces a clean production bundle.

### Phase 4/5 known limitations / debt
- PO send uses Django's default email backend. In dev with `console` backend it just logs; production should configure `EMAIL_BACKEND` + SMTP. Failure to send does NOT roll back the DRAFT → SENT transition (so the user can retry from the SENT state without flipping back to DRAFT), but the error is recorded on `PurchaseOrderEmail.error`.
- Barcode scanner uses the native `BarcodeDetector` API. Safari and Firefox don't ship it; users on those browsers will see the manual-entry fallback. Adding `@zxing/browser` would be a future polish.
- Multi-location split keeps `InventoryItem.current_stock` as the org-wide aggregate. If a future requirement is "show only this location's stock", the frontend should query `/items/{id}/location-stocks/` rather than refactoring the field.

### Phase 6 — Hardening & QA + Plane A integration — DONE (2026-05-08, 190/190 backend tests pass, frontend production build clean)

This phase closed out the V2 inventory spec without expanding scope. Plane A integration candidates (bookings→recipe, per-org AI distillation, POS imports, etc.) remain deferred — see "Future phases" below.

**Backend**:
- New `apps/inventory/tests/test_firewall_e2e.py` — **22 tests** that pin the firewall as the single chokepoint for every channel:
  - 9 parametrized unit cases for probe/non-probe detection across en/zh-CN/zh-TW.
  - AIService-level: deflection short-circuits before OpenAI is invoked (mock asserts `chat.completions.create.call_count == 0` after a probe — fails loudly on regression).
  - AIService-level: language-correct deflection in en/zh-CN/zh-TW.
  - AIService-level: explicit V2 spec regression — a normal menu question is NOT intercepted (Part 5 acceptance criterion).
  - Widget HTTP path (`POST /api/v1/widget/message/`): probe is deflected end-to-end, OpenAI never called, customer + AI messages are still persisted.
  - Widget HTTP path: legitimate booking question reaches AIService normally.
  - Channel-symmetry: WhatsApp + Instagram conversations route through the same AIService chokepoint, so the AIService-level guard covers them too.
- `tasks.py` owner-phone lookup is now a single `_resolve_owner_phone(org)` helper. Removed the speculative `user.whatsapp_number` fallback (that field doesn't exist on `accounts.User`); now uses `user.phone → org.phone` deterministically.
- `admin.py` rewritten to V2 spec Part 5 quality:
  - Every Phase 1-5 model is registered (was: only 6 of ~17 models).
  - `InventoryItem.sku` and `current_stock` are `readonly_fields` (computed from ledger).
  - `StockMovement` is fully immutable in admin (no add/change/delete).
  - `StockAlert` has a bulk "Mark selected as resolved" action.
  - `InventoryAuditLog`, `RecipeVersion`, `SalesImport`, `SupplierImport` render JSON (`before`, `after`, `changes`, `error_log`, `summary`, `column_map`, `snapshot`) as pretty-formatted `<pre>` blocks via `_pretty_json()`.
  - `RecipeIngredient` is a `TabularInline` on `RecipeAdmin`; `PurchaseOrderItem` and `PurchaseOrderEmail` are inlines on `PurchaseOrderAdmin`; `LocationStock` is an inline on `InventoryItemAdmin`; `StockTakeLine` is an inline on `StockTakeAdmin`.

**Frontend**:
- New shared component `components/inventory/InventoryStates.tsx` — `<InventoryLoading variant="cards|rows">`, `<InventoryEmpty>`, `<InventoryError onRetry>`. Use these on inventory list pages instead of ad-hoc loading/empty markup.
- `MovementsPage` and `SuppliersPage` migrated: skeleton loaders, error state with retry button, i18n-keyed table headers / dialog labels (previously hardcoded English).
- i18n: added `inventory.supplierForm.*`, `inventory.movementsTable.*`, and `common.retry` to all three locales (en / zh-CN / zh-TW).

**Plane A integration (booking → recipe consumption)**:
- New model `RecipeBookingLink(organization, booking, recipe, batches, consumed_at)` with unique `(booking, recipe)`. Lives in inventory; `restaurant.Booking` is unaware. Owner-only API at `/api/v1/inventory/recipe-booking-links/`.
- `signals._on_booking_save` listens to `Booking` post_save. Gated by `INVENTORY_SETTINGS['AUTO_CONSUME_ON_BOOKING_COMPLETE']` (env var `INVENTORY_AUTO_CONSUME_ON_BOOKING`, default **False** so production behavior is unchanged until enabled). When booking flips to `COMPLETED`, consumes each unconsumed link via `StockEngine.consume_recipe`, sets `consumed_at`, and ignores duplicate post_saves. Failures are logged and never block the booking save (inventory is downstream of bookings, not gating).
- The bridge is one-directional: inventory imports from restaurant (lazily via `_connect_booking_signal()` on `apps.inventory.AppConfig.ready`); restaurant code never imports from inventory.

**Plane B per-org AI profile**:
- New model `InventoryAIProfile(organization, profile, generated_at)` (one row per org).
- New service `services/ai_profile.py`: `build_profile()`, `get_or_build_profile()` (TTL via `INVENTORY_SETTINGS['AI_PROFILE_TTL_HOURS']`, default 36), `render_profile_block()`. Profile contains item count, top 10 items by value, top 5 suppliers, recipe count, open alerts, recent negative-movement count.
- `InventoryAIEngine.query()` now prepends the rendered profile block to the prompt context (graceful fallback if profile generation fails).
- New beat task `refresh_inventory_ai_profiles_task` runs daily at 03:00 UTC.

**Recipe decimal-precision fix** (production bug):
- The frontend recipe calculator was raising `Ensure that there are no more than 4 decimal places` when consuming a recipe — `(ing.quantity × batches) / yield_factor` and `output_quantity × batches` produce Decimals with 5–8 fractional digits when operands carry trailing zeros from DB storage, but `StockMovement.quantity` is `Decimal(decimal_places=4)`.
- Fix: quantize required and output quantities to 4 decimal places in both `RecipeEngine.calculate_batch` (display + feasibility) and `StockEngine.consume_recipe` (persistence). All existing tests still pass; new Phase 6 signal tests exercise this path.

**Tests / build**:
- `docker compose exec backend pytest` — **190/190 passing** (was 153 before Phase 6, +22 firewall E2E, +15 Plane A signal/profile/API).
- `docker compose run --rm frontend npm run build` — production bundle compiles clean. `build:check` shows zero new errors in inventory files (pre-existing TS errors in `realestate/`, `restaurant/`, `settings/`, `services/api.ts` are unrelated and CI does not gate on them per Phase 1 convention).
- New migration: `apps/inventory/migrations/0006_inventoryaiprofile_recipebookinglink.py`.

### Phase 6 known limitations / debt
- The booking auto-consume signal is **off by default** in production. Set the env var `INVENTORY_AUTO_CONSUME_ON_BOOKING=true` (or flip `INVENTORY_SETTINGS['AUTO_CONSUME_ON_BOOKING_COMPLETE']` in settings) to enable. There is no per-org toggle yet — it is global. If a future need is "enable for some orgs only", add an `Organization.feature_flags` JSONField check inside `_on_booking_save`.
- `RecipeBookingLink` rows must be created/managed via the API (or admin) before the booking is completed; there is no UI yet to attach recipes to a booking from the bookings page. Adding that UI is a small task and would live in `pages/restaurant/BookingsPage.tsx`.

### V2 spec parity (gap analysis, 2026-05-08)
The `INVENTORY_CLAUDE_CODE_PROMPT_V2.md` spec ends at Part 7 and is **fully discharged**. Subagent audit confirms every model, service, prompt, ViewSet, permission, signal, and Celery task in the spec is present in code. Phases 4 and 5 went *beyond* the V2 spec; Phase 6 closed remaining V2 polish items (admin UX, AIService-unchanged regression test, owner-phone lookup) without adding feature scope. There is no "Phase 7 for parity" needed.

### Future phases (6+) — PROPOSALS ONLY, NOT SPEC

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
