# mai-tai-admin

Operator CLI for a Mai-Tai deployment. Answers "are my bots actually alive?"
from the host, without opening the web UI or hand-writing psql.

```
$ mai-tai status
  Workspace       Type    Runner                  Up    Heartbeat  State      Sched
  DevOps / SRE    agent   maitai-agent-cd1b8708   yes          12s  connected    2/2
  Rando           agent   tmux:rando              yes           4s  connected    0/0
  ...

$ mai-tai doctor
  ✓ maitai-postgres              Up 6 days (healthy)
  ✗ Rando: alive but not talking tmux:rando is up, last heartbeat 15h02m ago —
                                 likely an MCP client drop.
                                 Fix: mai-tai bots restart 'Rando'
  1 failure(s), 0 warning(s)

$ mai-tai bots restart Rando
```

## Not for agents

This is deliberately a separate package from `mai-tai-mcp`, and it is never
published to PyPI.

`mai-tai-mcp` is installed inside every agent container. Anything shipped there
is handed to every agent by definition, so putting operator verbs in it would be
privilege escalation by packaging. This tool needs the docker socket, the
postgres container, and the host process table — three things agent containers
are specifically denied. It stays on the operator's host.

## Install

```bash
uv tool install --editable ./cli
```

Requires Python 3.11+, and on the host: `docker`, `ps`, and a running
`maitai-postgres`.

## Commands

| Command | What it does |
| --- | --- |
| `mai-tai status` | One row per workspace: runner, uptime, heartbeat age, state, schedules |
| `mai-tai doctor` | Health checks across core containers, bots, orphans, and schedules. Exits 1 on any failure |
| `mai-tai ws list [--archived]` | Every workspace with agent type, message counts, and last-seen |
| `mai-tai describe <ws>` | One workspace in full: runner, agent config, settings, message stats, auth, schedules. Also `mai-tai ws describe` |
| `mai-tai bots restart <target> [--wait N]` | Bounce a bot by repo name or workspace, then wait for its heartbeat to come back |
| `mai-tai tail <workspace> [-n N] [-f]` | Read a workspace's conversation; `-f` follows |

`<target>` and `<workspace>` resolve by id prefix, exact name, or
case-insensitive substring — `mai-tai tail devops` is enough. An ambiguous
match lists the candidates instead of guessing.

The `Type` column is the agent type, not just `chat` vs `agent`: a workspace
running the monitor template reads `agent/monitor`, pulled from
`agent_config->>'template'`.

`describe` prints `agent_config` verbatim rather than a curated subset, so a
key the spawner starts honouring tomorrow shows up here instead of being
silently dropped. Its **Auth** section keys off `workspace_agent_activity`, not
`api_keys.workspace_id` — a key can be user-scoped and still be the credential a
workspace's agent presents, and filtering on `api_keys.workspace_id` reports
"no keys" for a workspace that is plainly authenticating right now. It reports
key metadata only: never the key material or its hash.

## What doctor checks

- **Core containers** — postgres, backend, frontend running and healthy
- **Supervisors** — every repo in `boot-repos.conf` has a live session, and every
  live session has a `claude` process under it
- **Bots** — the one that matters: a runner that is *up* while its heartbeat is
  stale. Both `ps` and `docker ps` call this healthy; only
  `workspace_agent_activity` shows the bot has been talking to nobody for hours.
  That is the MCP-client-drop failure mode, and it is invisible to every other
  tool on the box.
- **Orphans** — running `maitai-agent-*` containers with no matching workspace
- **Schedules** — `next_run_at` in the past means the scheduler loop stalled

## Design notes

Everything shells out — no psycopg, no docker SDK. The CLI has to work on a bare
deployment host where docker is the only guaranteed dependency, and
`docker exec <pg> psql` is already how `scripts/mai-tai-config.sh` talks to the
database.

Two traps worth knowing, both encoded in `probes.py`:

- **Never `docker exec -i`.** Attaching stdin makes the exec'd process swallow
  whatever is piped into the caller, silently eating the rest of a script.
- **psql needs exotic separators.** Message bodies contain newlines and pipes,
  so the usual `-F '|'` line-per-row parsing corrupts them. We use `\x1f`/`\x1e`.

The status thresholds (`<420s` connected, `<600s` idle, else offline) are
duplicated from `backend/app/api/v1/workspaces.py:get_agent_status` so the CLI
and the web UI never disagree about what "offline" means. If those move, move
them here too.

## Tests

```bash
uv run --with pytest --with typer --with rich python -m pytest cli/tests -q
```

No docker or postgres required — the probe boundary is monkeypatched, so the
tests assert what the checks *conclude*, which is the part that has been wrong
in production.
