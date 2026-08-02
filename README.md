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
| `AGENT_MODEL` | Model agents run (default: `sonnet`) |
| `CLAUDE_CODE_USE_VERTEX` | Set `1` to auth agents via Google Vertex AI instead of an Anthropic key |
| `ANTHROPIC_VERTEX_PROJECT_ID` | GCP project for Vertex (required when Vertex is on) |
| `CLOUD_ML_REGION` | Vertex region (default: `global`) |
| `GITHUB_CLIENT_ID/SECRET` | GitHub OAuth (optional) |
| `GOOGLE_CLIENT_ID/SECRET` | Google OAuth (optional) |

With Vertex enabled, the backend reads the host's Application Default
Credentials (`~/.config/gcloud`, mounted read-only) and passes them to each
agent container — no per-user Anthropic key needed. Run `gcloud auth
application-default login` on the host first.

### Building the Agent Image

Build from the **repo root**, not `agents/` — the images copy `mcp-server/`
into the container, so it has to be inside the build context.

```bash
# Claude Code runtime (required for agent workspaces)
docker build -t mai-tai-agent:latest -f agents/claude-code/Dockerfile .

# OpenAI Codex runtime (optional — for workspaces using the codex runtime)
docker build -t mai-tai-agent-codex:latest -f agents/codex/Dockerfile .
```

Rebuild after changes to `agents/`.

Agent containers run a **driver loop**: each user message triggers one CLI
turn (`claude -p --resume`), so there is no long-lived agent process to babysit.
Persistent memory lives on the per-workspace volume: `MEMORY.md` (curated,
size-capped, loaded every session), `journal/` (daily notes), and
`tasks/lessons.md` — plus a `search_history` tool backed by Postgres full-text
search over the workspace's entire message history.

## Migrating to Another Host

`scripts/mai-tai-config.sh` moves a whole deployment — users, workspaces,
agents, and full message history — to another machine.

```bash
# On the source host
./scripts/mai-tai-config.sh export mai-tai-backup.tar.gz
./scripts/mai-tai-config.sh inspect mai-tai-backup.tar.gz   # peek without restoring

# On the target host
./scripts/mai-tai-config.sh check-env                       # what's missing from .env
./scripts/mai-tai-config.sh import mai-tai-backup.tar.gz    # prompts before wiping
```

### ⚠️ Treat the bundle as a secret

By default the dump is byte-for-byte complete, so the credentials in
`users.settings` (Anthropic/OpenAI keys, GitHub token, LLM keys) travel with
it. That's deliberate — the target comes up as a working copy with nothing to
re-enter. The tradeoff is that the tarball *is* credential material. It's
written mode `0600`, `mai-tai-export-*.tar.gz` is gitignored, and you should
delete it once the move is done.

Those settings are Fernet-encrypted at rest, but the key comes from
`ENCRYPTION_KEY` — or, when that's unset, from `SECRET_KEY` — so **the target
needs the same values or the restored credentials decrypt to nothing**. Import
fingerprints both ends and warns on a mismatch before it touches the database.

| Flag | Effect |
|---|---|
| *(none)* | Full fidelity — credentials included, nothing to re-enter on the target |
| `--scrub` | Strip credentials from `users.settings`; safe to store, but you re-enter keys in **Settings → AI** |
| `--with-env` | Also bundle `.env`. Import writes it to `.env.imported` for review rather than overwriting |

Password hashes and `mt_` API-key hashes are always included, so logins and
existing agent configs keep working on the target.

Either way, copy `~/.config/mai-tai/config` across so existing `mt_` API keys
still authenticate — and fix its `MAI_TAI_API_URL` to point at the target.

### What the bundle doesn't carry

The bundle is the database plus (optionally) `.env`. Everything below is
source-host specific and has to be handled on the target by hand:

- **The host's address, baked into `.env`.** `NEXT_PUBLIC_API_URL`,
  `NEXT_PUBLIC_WS_URL`, and `NEXTAUTH_URL` are compiled into the frontend
  bundle. Left alone, the target's UI loads fine and then quietly talks to the
  *source* host. Rewrite them before `./dev.sh local up`.
- **The agent image.** `mai-tai-agent:latest` is built locally, so a fresh
  clone has none — agent workspaces fail to start until you build it (see
  [Building the Agent Image](#building-the-agent-image)).
- **TLS and LAN DNS.** `caddy/certs/` is untracked and `infra/dnsmasq.conf`
  hardcodes the source host's IP, so both services crash-loop on a new host.
  Unless you're serving the same domain from the target, leave them stopped:
  `docker compose stop caddy dnsmasq`.

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT — see [LICENSE](LICENSE) for details.
