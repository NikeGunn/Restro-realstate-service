# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-tenant AI business chatbot platform ("Kribaat" / chatplatform) with two verticals — **Restaurant** and **Real Estate** — sharing one core. Production lives at `kribaat.com` and is deployed to a K3s cluster via ArgoCD GitOps. The repository contains three deployable artifacts: a Django backend, a React/Vite admin dashboard, and an embeddable vanilla-JS widget served by the backend at `backend/apps/widget/widget.js`.

The product spec is `agent.md` (gitignored locally but authoritative for scope decisions). It is strict about NOT building POS/CRM/payments/delivery features — keep changes inside the documented scope unless the user explicitly overrides.

## Common Commands

### Local development (docker-compose)
```bash
docker-compose up --build                                    # All services (db, redis, backend, celery, celery-beat, frontend)
docker-compose exec backend python manage.py migrate
docker-compose exec backend python manage.py createsuperuser
docker-compose exec backend python manage.py makemigrations <app>
```
Backend → http://localhost:8000 · Frontend → http://localhost:3000 · API docs → http://localhost:8000/api/docs/

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

- **Don't add features outside `agent.md` scope** (no payments, no POS, no CRM features, no delivery). If unsure, prefer human handoff over a new feature.
- **Don't hardcode prompts** — AI prompt templates live as files (referenced from `apps/ai_engine/`), not inline strings.
- **Don't commit secrets, `.env*`, `.pem`, or `k8s/secrets.yaml`** — `.gitignore` blocks the common cases but be deliberate.
- **`*.ps1` scripts are gitignored** (except `config.ps1.example`). Local-only deployment helpers; don't rely on them in CI or docs.
- **`agent.md`, `QUICK_REFERENCE.txt`, `SECURITY*.md`, `*-diagnostic.ps1`, `check_*.py` and similar debug scripts are gitignored** — when investigating, you may find such files locally; don't commit them.
- The repo path contains a space (`Restro & real estate`). Quote paths in shell commands.
