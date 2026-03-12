# Mai-Tai

**Async human-agent collaboration. Spin up AI agents, step away, check in from your phone.**

Mai-Tai is a self-hosted platform that lets you launch AI coding agents as Docker containers, communicate with them via a mobile-first web UI, and stay in the loop from anywhere — no IDE required.

## What It Does

- **Spin up agents** — create a workspace, pick a template (research, coding, assistant), and Mai-Tai spawns a Docker container running Claude Code connected to your workspace
- **Talk to your agents** — real-time WebSocket messaging from any device, including mobile
- **Step away** — agents run autonomously in Docker, sending you updates and asking questions via Mai-Tai when they need you
- **Persistent memory** — agents remember lessons learned across restarts via a per-workspace mounted volume
- **Stash** — save and organize links with AI enrichment and `#NNNN` issue numbers

## Quick Start

**Prerequisites:** Docker, Docker Compose, Git

```bash
git clone https://github.com/jmcdice/mai-tai-dev.git && cd mai-tai-dev
cp .env.example .env
# Edit .env: set SECRET_KEY, NEXTAUTH_SECRET, and your Anthropic API key
./dev.sh local up
```

Visit **http://localhost:3000** — the first account created becomes admin.

## Agent Workspaces

The core feature. Create an agent workspace, pick a template, and Mai-Tai launches a Docker container running Claude Code connected to your workspace via MCP.

### Templates

| Template | Description |
|---|---|
| **Research** | Searches the web, compiles findings, sends reports |
| **Coding Agent** | Clones a GitHub repo, writes code, opens PRs |
| **Personal Assistant** | General tasks, daily questions, follow-ups |
| **Monitor** | Periodic checks, alerts on changes |
| **Custom** | Your own system prompt and behavior |

### How It Works

```
You (mobile/browser)
    │
    ▼
Mai-Tai Web UI  ──WebSocket──▶  Backend (FastAPI)  ──▶  PostgreSQL
                                       │
                               Docker Socket
                                       │
                                       ▼
                          ┌─────────────────────┐
                          │  Agent Container     │
                          │  (Claude Code + MCP) │
                          │  /home/agent/memory/ │  ← persistent volume
                          └─────────────────────┘
```

Each agent container:
- Runs Claude Code in headless mai-tai mode
- Connects to your workspace via the MCP server
- Has a persistent volume at `/home/agent/memory/` for lessons and task notes
- Gets template-specific `CLAUDE.md` with working principles baked in

### Coding Agent Setup

1. Create a workspace → select **Coding Agent** template
2. Enter your GitHub repo URL
3. Add a GitHub PAT in Settings → AI tab
4. Start the agent — it clones the repo and gets to work

### MCP Config (host-based sessions)

For Claude Code sessions running directly on a machine (not in a Docker container):

```bash
# Global credentials (~/.config/mai-tai/config)
MAI_TAI_API_URL=http://localhost:8000
MAI_TAI_API_KEY=mt_your_key_here

# Per-project workspace (.env.mai-tai in project root)
MAI_TAI_WORKSPACE_ID=your-workspace-uuid
```

## Features

- **Docker-per-agent** — each workspace gets its own isolated container
- **Persistent memory** — agents learn from corrections, lessons survive restarts
- **Mobile-first** — designed for checking in from your phone
- **Real-time** — WebSocket-powered live updates
- **Multi-workspace** — separate workspaces per project/agent
- **Auth** — email/password + optional OAuth (GitHub, Google)
- **Admin panel** — user management, registration toggle, impersonation
- **Stash** — save links with AI enrichment and `#NNNN` issue tracking
- **Self-hosted** — runs entirely on your machine, no data leaves your network

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  Mai-Tai Platform                │
│                                                  │
│  Frontend (Next.js)  ◀──▶  Backend (FastAPI)     │
│         │                        │               │
│         │ WebSocket         PostgreSQL           │
│         │                        │               │
│         │                  Docker Socket         │
│         │                        │               │
│         │               Agent Containers         │
│         │               (Claude Code + MCP)      │
└─────────────────────────────────────────────────┘
         ▲
         │
   You (anywhere)
```

## Development

```bash
./dev.sh local up          # Start everything
./dev.sh local logs        # View logs
./dev.sh local rebuild     # Rebuild after code changes
./dev.sh local migrate     # Run database migrations
./dev.sh local down        # Stop everything
./dev.sh local nuke-db     # Wipe database and start fresh
```

## Configuration

See `.env.example` for all options. Key settings:

| Variable | Description |
|---|---|
| `SECRET_KEY` | JWT signing key (required, change in production) |
| `NEXTAUTH_SECRET` | NextAuth session encryption |
| `CORS_ORIGINS` | JSON array of allowed origins |
| `REGISTRATION_ENABLED` | Set `false` to disable new signups (also toggleable in admin UI) |
| `AGENT_IMAGE` | Docker image for agent containers (default: `mai-tai-agent:latest`) |
| `GITHUB_CLIENT_ID/SECRET` | GitHub OAuth (optional) |
| `GOOGLE_CLIENT_ID/SECRET` | Google OAuth (optional) |

### Building the Agent Image

```bash
docker build -t mai-tai-agent:latest ./agent
```

This image is required for agent workspaces. Rebuild after changes to `agent/`.

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT — see [LICENSE](LICENSE) for details.
