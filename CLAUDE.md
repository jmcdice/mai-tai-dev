# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is Mai-Tai

A real-time collaboration platform between humans and AI coding agents. Users interact with AI agents through workspace-based chat powered by WebSockets. Agents connect via MCP (Model Context Protocol).

## Development Commands

All development uses Docker Compose via `./dev.sh local`:

```bash
./dev.sh local up          # Start all services (postgres, backend, frontend)
./dev.sh local down        # Stop all services
./dev.sh local rebuild     # Full rebuild (no cache) and restart
./dev.sh local logs        # Tail all logs (or: ./dev.sh local logs backend)
./dev.sh local migrate     # Run alembic migrations
./dev.sh local status      # Health check all services
./dev.sh local shell       # Shell into backend container (default)
./dev.sh local nuke-db     # Wipe database and start fresh
```

Services run at: Frontend http://localhost:3000, Backend http://localhost:8000, Postgres on port 5433.

## Linting and Type Checking

```bash
# Backend (Python) -- run inside container or with ruff installed locally
cd backend && ruff check .

# Frontend (TypeScript)
cd frontend && npx tsc --noEmit
cd frontend && npm run build    # Full production build check
```

Ruff config is at `backend/ruff.toml` (ignores F821 for SQLAlchemy forward references).

## CI Pipeline

PRs run: frontend build + type check, backend ruff lint, Trivy security scan, CodeQL static analysis. All must pass.

## Architecture

Three-service Docker Compose stack plus a standalone MCP server:

**Backend** (`backend/`) -- Python FastAPI with async SQLAlchemy (asyncpg) and Alembic migrations.

- `app/main.py` -- FastAPI app, CORS config, rate limiting (slowapi)
- `app/api/v1/` -- All REST endpoints, organized by domain (auth, workspaces, mcp, websocket, admin, dashboard, feedback)
- `app/api/v1/router.py` -- Combines all route modules under `/api/v1`
- `app/api/deps.py` -- Authentication dependencies: JWT for web users, API key (X-API-Key header) for MCP agents
- `app/models/` -- SQLAlchemy ORM models (User, Workspace, Message, ApiKey, Agent, Feedback, WorkspaceAgentActivity)
- `app/schemas/` -- Pydantic request/response schemas
- `app/core/config.py` -- Settings from env vars via pydantic-settings
- `app/core/websocket.py` -- ConnectionManager for real-time broadcast per workspace channel
- `app/db/session.py` -- Async engine and session factory
- `alembic/versions/` -- Sequential numbered migrations (001-007)

**Frontend** (`frontend/`) -- Next.js 15 App Router with TypeScript, Tailwind CSS, shadcn/ui.

- `app/(authenticated)/` -- Protected routes (dashboard, workspaces, agents, settings, admin, search, docs)
- `app/(public)/` -- Public routes (landing page)
- `app/api/auth/` -- NextAuth.js route handlers (GitHub + Google OAuth)
- `lib/api.ts` -- Typed API client for all backend endpoints
- `lib/auth.tsx` -- AuthContext provider (dual-mode: JWT for local, IAP for production)
- `hooks/use-websocket.ts` -- WebSocket hook for real-time updates
- `components/chat/` -- Chat UI components
- `components/ui/` -- shadcn/ui primitives

**MCP Server** (`mcp-server/`) -- Python package (`mai-tai-mcp`), published to PyPI, run via `uvx`.

- `mai_tai_mcp/server.py` -- FastMCP server with tools: `chat_with_human` (blocking), `update_status` (non-blocking), `get_messages`, `get_project_info`
- `mai_tai_mcp/backend.py` -- HTTP client for backend API
- `mai_tai_mcp/ws_client.py` -- WebSocket client
- `mai_tai_mcp/config.py` -- Configuration from env vars
- `mai_tai_mcp/prompts/` -- Agent instruction markdown files
- Uses HTTP polling (not WebSocket) for waiting on human responses
- Monitors stdin to detect client disconnect and prevent zombie processes

## Key Data Flow

1. **Web user sends message** -> Frontend WebSocket -> Backend saves to DB + broadcasts to workspace channel
2. **MCP agent sends message** -> `POST /api/v1/mcp/messages` (API key auth) -> Backend saves + WebSocket broadcast
3. **Agent waits for human** -> `chat_with_human` tool polls `GET /api/v1/mcp/messages?unseen=true` every 3s
4. **Message acknowledgment** -> `POST /api/v1/mcp/messages/acknowledge` marks messages as seen (sets `seen_at`)

## Authentication

Two auth modes controlled by `USE_IAP` env var:

- **Local dev (default)**: JWT tokens via `/api/v1/auth/login`, stored in localStorage. NextAuth.js handles OAuth.
- **Production**: Google Identity-Aware Proxy (IAP) with auto-provisioning of users.

MCP agents authenticate with hashed API keys (`X-API-Key` header, `mt_` prefix). Keys are workspace-scoped or user-scoped.

## Database

PostgreSQL 16. Alembic for migrations (run inside backend container). Models use SQLAlchemy 2.0 mapped_column style. The `message_metadata` column is mapped from a DB column named `metadata` (via `mapped_column("metadata", JSONB)`).

## Conventions

- Commit messages use conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
- Branch naming: `feature/`, `fix/`, `docs/`, `refactor/`
- Backend uses async/await throughout (async SQLAlchemy sessions)
- Frontend uses `@/` path alias for imports from project root
- UI components follow shadcn/ui patterns in `components/ui/`
- Environment config via `.env` file (copy from `.env.example`)
