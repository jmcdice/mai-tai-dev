# Feature Plan: WhatsApp Bridge for Mai-Tai

**Branch:** `feature/whatsapp-bridge`
**Status:** Draft / planning
**Author:** Joey + agent (mai-tai mode)
**Date:** 2026-06-20

## Goal

Let a mai-tai workspace's agent send and receive WhatsApp messages, so real people
(who do **not** have mai-tai accounts) can talk to the agent from a WhatsApp group or
DM. The motivating use case: a surf-trip WhatsApp group where 11 people can ask the
agent trip questions ("when does Dave land?", "what day is the boat trip?") and get
answers, sourced from the `../surf-trip/` project.

## Core concept: one workspace, two channels

A workspace becomes a **membrane** between two channels, with the agent in the middle:

| Who / what | `channel` | Mirrored to WhatsApp? | Visible in web UI? |
|---|---|---|---|
| Owner types in web UI | `private` | ❌ never | ✅ |
| Agent replies to owner | `private` | ❌ never | ✅ |
| WhatsApp users message | `wa` | (originated there) | ✅ (owner watches) |
| Agent addresses WhatsApp | `wa` | ✅ via `send_to_wa` | ✅ |

- **Default is private.** The owner ↔ agent side-conversation in the web UI never
  leaks to WhatsApp.
- **Going public is deliberate.** The *only* path to WhatsApp is the new `send_to_wa`
  MCP tool. Normal `chat_with_human` replies stay private.
- The agent can carry info across the membrane on request
  ("tell the WA crew the surf report") without exposing the private channel.

The WhatsApp target is per-workspace config: it can be a **group JID** (surf trip) or
an **individual JID / list** (a personal WA assistant — just me). Same machinery.

## Architecture

```
 WhatsApp (group or DM)
        │  (WhatsApp Web protocol, linked device)
        ▼
 Evolution API  ── Docker container, owns the WA session + QR linking
        │  webhook (inbound)         ▲ REST sendText (outbound)
        ▼                            │
 mai-tai backend  ── NEW: wa_bridge module
        │  - verify webhook, resolve instance → workspace
        │  - filter: only act if agent was @-mentioned (configurable)
        │  - write Message(channel="wa", source="whatsapp", wa_name, wa_number)
        │  - on agent send_to_wa: POST to Evolution sendText
        ▼
 messages table (existing) ── channel + wa_* in message_metadata
        ▲
        │  MCP (existing transport)
 Agent (Claude Code, mai-tai mode)
        │  - reads private + wa messages in one timeline
        │  - send_to_wa(text) = NEW tool, the only door to WhatsApp
        ▼
 ../surf-trip/  ── mounted read-only so the agent can answer trip questions
```

### Why Evolution API (vs. rolling our own Baileys)

The hard part of WhatsApp-Web bots is **staying linked** (sessions drop, re-pairing,
reconnect, media). Evolution API solves that and exposes a clean REST + webhook model
that maps 1:1 onto how our backend already broadcasts. We own only a thin adapter.
Another Docker container on this host is acceptable.

> ⚠️ **Ban risk:** the WhatsApp Web route (Evolution/Baileys) is unofficial and against
> WhatsApp ToS. Use a **dedicated/burner number**, never a personal one. Fine for 11
> friends; not for production-scale outreach.

## Data model changes

No schema migration strictly required — `Message.message_metadata` (JSONB) already
exists. We standardize these keys:

- `channel`: `"private"` (default) | `"wa"`
- `source`: existing field; `"whatsapp"` for inbound WA
- `wa_name`: sender display name (e.g. "Dave")
- `wa_number`: sender phone (e.g. "+1...")
- `wa_message_id`: Evolution message id (idempotency / dedupe)

Optional: add `Workspace.agent_config.whatsapp = { instance, target_jid, mention_required }`
to bind a workspace to a WA instance.

## New components

1. **Evolution API service** (`docker-compose.yml`)
   - Image: `atendai/evolution-api` (or pinned tag), with its own Postgres/Redis or
     reuse existing Postgres with a separate DB.
   - Env: API key, webhook URL → mai-tai backend.

2. **Backend `wa_bridge`** (`backend/app/services/wa_bridge.py` + `api/v1/whatsapp.py`)
   - `POST /api/v1/whatsapp/webhook` — receive Evolution events (auth via shared secret).
   - Resolve instance → workspace; dedupe by `wa_message_id`.
   - Mention filter: only create a message (and wake the agent) if the bot was
     @-mentioned, when `mention_required` is on. Otherwise store as context only
     (configurable — start with mention-required ON).
   - `send_to_wa(workspace, text)` helper → Evolution `POST /message/sendText`.

3. **New MCP tool `send_to_wa`** (`mcp-server/mai_tai_mcp/server.py`)
   - Posts a message with `channel="wa"`; backend mirrors it to WhatsApp.
   - Docstring makes clear: this is the ONLY way to reach WhatsApp; everything else
     stays private.

4. **Wait-loop tweak** (`mcp-server/mai_tai_mcp/server.py`)
   - `_wait_for_response_polling` currently wakes only on messages with
     `user_id is not None`. WA messages have `user_id = NULL`. Update the wake
     condition to also return messages with `source == "whatsapp"`, and surface
     `wa_name` so the agent knows who asked and via which channel.

5. **Frontend labeling** (optional, nice-to-have)
   - Badge/color `wa` vs `private` messages; show `wa_name` on WA messages.
   - "🌐 sent to WhatsApp" indicator on mirrored agent messages.

## Reply routing rules (agent behavior)

- Owner asks in web UI → answer with `chat_with_human` → **private**.
- WA user @-mentions the agent → answer with `send_to_wa` → **public**.
- Owner says "tell the WA group X" → agent composes, calls `send_to_wa` → **public**,
  while the acknowledgement back to the owner stays **private**.

## Phased rollout

**Phase 1 — Bridge skeleton (no agent yet)**
- Stand up Evolution API in compose; link the burner number via QR.
- Implement webhook ingest → write `channel="wa"` messages into a test workspace.
- Implement `send_to_wa` backend helper; verify a manual API call posts to the group.

**Phase 2 — Agent loop**
- Add `send_to_wa` MCP tool + wait-loop tweak.
- Run a Claude Code agent (mai-tai mode) bound to the workspace; confirm it sees WA
  messages, answers via `send_to_wa`, and keeps the private channel separate.

**Phase 3 — Surf trip wiring**
- Mount `../surf-trip/` read-only into the agent's environment.
- Mention-required ON; seed agent instructions with trip context.
- Create the real WA group, add the 11 + the bot number, dry-run Q&A.

**Phase 4 — Polish**
- Frontend channel badges, dedupe hardening, rate-limit/guardrails, error handling
  for dropped WA sessions (alert owner in private channel when the link drops).

## Open questions / decisions deferred

- Evolution: dedicated DB vs. reuse existing Postgres instance.
- How the agent runs always-on (reuse `agent_spawner` container vs. a plain
  long-lived Claude Code session). Lean: reuse the agent-container pattern.
- Mention detection details from Evolution payload (mentioned JIDs array).
- Whether non-mention WA messages are stored as silent context or dropped (start: dropped).
```
