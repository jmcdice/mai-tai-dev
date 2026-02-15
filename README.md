# Mai-Tai 🍹

**Real-time collaboration between humans and AI coding agents.**

Mai-Tai is a web-based platform that enables asynchronous communication between developers and AI coding agents. Think of it as a shared workspace where you can check in on what your agents are doing, send them messages, and receive updates—all in real-time.

## TL;DR for Agents

Just tell your AI coding agent:

> Clone and run https://github.com/jmcdice/mai-tai-dev, make the frontend accessible on the local network, then give me the URL to access it.

Your agent will handle the rest.

## Features

- 🔄 **Real-time messaging** - WebSocket-powered live updates
- 👥 **Multi-workspace** - Organize projects into separate workspaces
- 🤖 **MCP Integration** - Connect any AI agent via the Model Context Protocol
- 🔐 **OAuth authentication** - Sign in with GitHub or Google
- 📱 **Mobile-first** - Responsive design that works on any device

## Quick Start

**Prerequisites:** Docker, Docker Compose, Git, [uv](https://docs.astral.sh/uv/) (for the `uvx` command)

> We use `uvx` (the UV package runner) to run the MCP server. Install UV with `curl -LsSf https://astral.sh/uv/install.sh | sh`

```bash
git clone https://github.com/jmcdice/mai-tai-dev.git && cd mai-tai-dev
cp .env.example .env
./dev.sh local up
```

That's it! Visit **http://localhost:3000** to create a local account.

This starts:

- **Frontend** at http://localhost:3000
- **Backend API** at http://localhost:8000
- **PostgreSQL** database

The first account created automatically becomes admin.

### Connect an AI agent

Once running, go to the web UI at http://localhost:3000, create a local account, and follow the onboarding flow. It will generate a setup blob that you paste to your agent - the agent handles the rest.

The MCP server runs via `uvx` (no pip install needed):

```bash
uvx --refresh mai-tai-mcp
```

This is automatically configured when your agent executes the setup blob.

## Development

```bash
# Start everything
./dev.sh local up

# View logs
./dev.sh local logs

# Rebuild after code changes
./dev.sh local rebuild

# Run database migrations
./dev.sh local migrate

# Stop everything
./dev.sh local down

# Nuclear option: wipe database and start fresh
./dev.sh local nuke-db
```

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Frontend  │────▶│   Backend   │────▶│  PostgreSQL │
│  (Next.js)  │     │  (FastAPI)  │     │             │
└─────────────┘     └─────────────┘     └─────────────┘
       ▲                   ▲
       │                   │
       └───────────────────┴──── WebSocket (real-time updates)

┌─────────────┐
│  AI Agent   │────▶ MCP Server (mai-tai-mcp)
│  (Claude,   │
│   etc.)     │
└─────────────┘
```

## Tech Stack

- **Frontend**: Next.js 14+ (App Router), Tailwind CSS, shadcn/ui
- **Backend**: FastAPI, SQLAlchemy, Alembic
- **Database**: PostgreSQL 16
- **Auth**: NextAuth.js with OAuth providers
- **MCP Server**: Python package (`mai-tai-mcp`)

## Configuration

See `.env.example` for all configuration options. Key settings:

| Variable                  | Description                             |
| ------------------------- | --------------------------------------- |
| `SECRET_KEY`              | JWT signing key (change in production!) |
| `GITHUB_CLIENT_ID/SECRET` | GitHub OAuth credentials (optional)     |
| `GOOGLE_CLIENT_ID/SECRET` | Google OAuth credentials (optional)     |
| `NEXTAUTH_SECRET`         | NextAuth session encryption             |
| `EXTRA_CORS_ORIGIN`       | Additional CORS origin for LAN access   |

### LAN Access (Optional)

> **Note:** Mai-Tai runs 100% locally on your machine. This section is only needed if you want to access it from **other devices on your local network** (like your phone). This does NOT expose anything to the internet.

By default, Mai-Tai only accepts connections from `localhost`. To access from other devices on your home/office network:

```bash
# 1. Find your machine's LAN IP (e.g., 192.168.1.100)
ip addr | grep "192.168"    # Linux
ipconfig getifaddr en0      # macOS

# 2. Update .env with your IP:
NEXT_PUBLIC_API_URL=http://192.168.1.100:8000
NEXT_PUBLIC_WS_URL=ws://192.168.1.100:8000
EXTRA_CORS_ORIGIN=http://192.168.1.100:3000
NEXTAUTH_URL=http://192.168.1.100:3000

# 3. Rebuild and restart
./dev.sh local rebuild
```

Now access Mai-Tai at `http://192.168.1.100:3000` from any device on your local network (phone, tablet, another computer, etc.).

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](LICENSE) for details.
