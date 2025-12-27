# AI Agent Instructions — Business Chat Platform MVP

You are a senior full-stack engineer and product architect.

Your job is to build a production-ready MVP of a **multi-tenant AI business chatbot platform** that supports:
- Restaurants
- Real Estate agencies

This platform must be:
- Simple to set up for businesses
- Modular and extensible
- Safe to run without third-party integrations
- Easy to deploy and maintain

You must follow this document strictly.
Do NOT add extra features.
Do NOT over-engineer.
Build only what is described.

---

## 1. PRODUCT GOAL (READ THIS FIRST)

We are building ONE platform with:
- Shared core features (auth, chat, AI, inbox)
- Business-specific verticals (restaurant, real estate)
- Feature gating (basic vs power plans)

This is NOT:
- A POS system
- A CRM replacement
- A payment platform

This IS:
- A 24/7 AI assistant
- A lead capture system
- A booking assistant
- A human handoff tool

---

## 2. TECH STACK (MANDATORY)

### Backend
- Python 3.11
- Django
- Django REST Framework
- PostgreSQL
- Redis (for queues + locks)
- Celery (background tasks)

### AI
- OpenAI API (chat completions)
- Prompt templates stored as files
- Strict fallback to human handoff when uncertain

### Frontend (Admin Dashboard)
- React
- Vite
- TypeScript
- Tailwind CSS
- Shadcn UI

### Website Chatbot Widget
- Vanilla JavaScript
- Embeddable via `<script>` tag
- No framework dependencies

### Infrastructure
- Docker (mandatory)
- docker-compose for local setup
- Environment-based config (.env)

---

## 3. SYSTEM ARCHITECTURE (HIGH LEVEL)

### Core Layers
1. Authentication & Organizations
2. Omnichannel Messaging Engine
3. AI Conversation Engine
4. Human Handoff System
5. Knowledge Base
6. Analytics (MVP)
7. Vertical Modules (Restaurant, Real Estate)

Each vertical MUST plug into the core platform.
No vertical should duplicate core logic.

---

## 4. CORE PLATFORM — REQUIRED FEATURES

### 4.1 Authentication & Organization

Entities:
- User
- Organization (Business)
- Location
- Role (Owner, Manager)

Rules:
- One user can belong to multiple organizations
- Access is scoped by role and location
- One login, many businesses

---

### 4.2 Omnichannel Messaging

Channels:
- Website chatbot
- WhatsApp (API-ready, mock first)
- Instagram (API-ready, mock first)

Requirements:
- Unified inbox
- Channel-agnostic conversation model
- Location-aware routing
- Message deduplication
- Conversation state machine (FSM)

---

### 4.3 AI Conversation Engine

Rules:
- AI can ONLY answer using:
  - Knowledge base
  - Vertical-specific data
- AI must say “I’ll connect you to a human” if uncertain
- Every message must have:
  - confidence score
  - intent classification

---

### 4.4 Human Handoff

Features:
- Manual reply dashboard
- Conversation locking
- AI disabled when human takes over
- Alerts for:
  - High intent
  - Booking failure
  - Confused user

---

### 4.5 Knowledge Base

Data:
- Business profile
- Location overrides
- FAQs
- Free text notes

Rules:
- Location data overrides business data
- AI must never hallucinate outside this data

---

### 4.6 Analytics (MVP ONLY)

Metrics:
- Total messages
- AI vs human handled
- Leads / bookings created
- Avg response time

No advanced charts.
Simple counts only.

---

### 4.7 Website Chatbot Widget

Requirements:
- Copy-paste JS snippet
- Auto-detect or ask for location
- Same logic as WhatsApp
- Minimal UI
- Lightweight

---

## 5. VERTICAL 1 — RESTAURANT

### Goal
Handle:
- Menu queries
- Bookings
- Customer chats

NOT:
- Payments
- POS
- Delivery
- Table-level seating

### Data Models
- MenuCategory
- MenuItem
- Booking
- OpeningHours
- DailySpecial

### Chatbot Capabilities
- Answer menu & price
- Answer opening hours
- Booking flow:
  - Location
  - Date
  - Time
  - Party size
  - Contact details
- Escalate if:
  - Fully booked
  - Special request
  - Unclear intent

---

## 6. VERTICAL 2 — REAL ESTATE

### Goal
Capture, qualify, and convert leads

NOT:
- CRM replacement
- Legal workflows
- Mortgage tools

### Data Models
- PropertyListing
- Lead
- Appointment

### Chatbot Capabilities
- Property availability
- Lead qualification:
  - Buy or rent
  - Budget
  - Area
  - Timeline
- Appointment booking
- Escalate high-intent leads

---

## 7. FEATURE GATING (PLANS)

### BASIC PLAN
- 1 location / office
- Website + WhatsApp
- Basic AI flows
- Human handoff
- Basic analytics

### POWER PLAN
- Multiple locations
- Website + WhatsApp + Instagram
- Alerts & escalation rules
- Aggregated analytics
- Advanced AI usage

Feature flags must be implemented at API level.

---

## 8. DEVELOPMENT PHASES (STRICT ORDER)

### Phase 1
- Auth & organizations
- Unified inbox
- Website chatbot
- Knowledge base
- Human handoff

### Phase 2
- Restaurant vertical
- Booking flow
- Basic analytics

### Phase 3
- Real estate vertical
- Lead qualification
- Appointments

### Phase 4
- Feature gating
- Alerts
- Hardening & cleanup

Do NOT skip phases.

---

## 9. QUALITY RULES

- Clear folder structure
- Reusable services
- Clean API contracts
- No magic numbers
- No hardcoded prompts
- All setup documented

---

## 10. FINAL INSTRUCTION

You are building a **sellable MVP**, not a demo.

When unsure:
- Choose simplicity
- Prefer human handoff
- Avoid feature creep

Start with Phase 1.
