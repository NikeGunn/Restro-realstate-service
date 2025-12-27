# AI Business Chat Platform MVP

## Overview
Multi-tenant AI business chatbot platform supporting Restaurants and Real Estate agencies.

## Tech Stack
- **Backend**: Python 3.11, Django, Django REST Framework, PostgreSQL, Redis, Celery
- **Frontend**: React, Vite, TypeScript, Tailwind CSS, Shadcn UI
- **Widget**: Vanilla JavaScript (embeddable)
- **Infrastructure**: Docker, docker-compose

## Quick Start

### Prerequisites
- Docker & Docker Compose
- OpenAI API Key

### Setup

1. Clone the repository:
```bash
cd "Restro & real estate"
```

2. Copy environment file:
```bash
cp .env.example .env
```

3. Edit `.env` and add your OpenAI API key:
```
OPENAI_API_KEY=your-openai-api-key-here
```

4. Start all services:
```bash
docker-compose up --build
```

5. Access the services:
   - **Backend API**: http://localhost:8000
   - **Frontend Dashboard**: http://localhost:3000
   - **API Documentation**: http://localhost:8000/api/docs/

### Create Superuser
```bash
docker-compose exec backend python manage.py createsuperuser
```

## Project Structure

```
├── backend/                 # Django Backend
│   ├── config/             # Django settings & configuration
│   ├── apps/
│   │   ├── accounts/       # Auth & Organizations
│   │   ├── messaging/      # Omnichannel Messaging
│   │   ├── ai_engine/      # AI Conversation Engine
│   │   ├── handoff/        # Human Handoff System
│   │   ├── knowledge/      # Knowledge Base
│   │   └── analytics/      # Analytics (MVP)
│   ├── prompts/            # AI Prompt Templates
│   └── requirements.txt
├── frontend/               # React Admin Dashboard
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── services/
│   │   └── types/
│   └── package.json
├── widget/                 # Embeddable Chatbot Widget
│   ├── src/
│   └── dist/
├── docker-compose.yml
└── README.md
```

## Phase 1 Features (Current)
- ✅ Authentication & Organizations
- ✅ Unified Inbox
- ✅ Website Chatbot Widget
- ✅ Knowledge Base
- ✅ Human Handoff

## API Endpoints

### Authentication
- `POST /api/auth/register/` - Register new user
- `POST /api/auth/login/` - Login
- `POST /api/auth/logout/` - Logout
- `GET /api/auth/me/` - Current user

### Organizations
- `GET /api/organizations/` - List organizations
- `POST /api/organizations/` - Create organization
- `GET /api/organizations/{id}/` - Get organization
- `GET /api/organizations/{id}/locations/` - List locations

### Messaging
- `GET /api/conversations/` - List conversations
- `GET /api/conversations/{id}/` - Get conversation
- `GET /api/conversations/{id}/messages/` - Get messages
- `POST /api/conversations/{id}/messages/` - Send message

### Knowledge Base
- `GET /api/knowledge/` - Get knowledge base
- `POST /api/knowledge/faqs/` - Add FAQ
- `PUT /api/knowledge/profile/` - Update business profile

### Widget
- `POST /api/widget/init/` - Initialize widget session
- `POST /api/widget/message/` - Send message from widget

## License
Proprietary - All rights reserved
