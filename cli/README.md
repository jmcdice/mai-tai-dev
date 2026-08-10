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

`mai-tai init` is the exception to that last requirement — it is the command you
run *before* there is anything to talk to.

## init

```bash
mai-tai init
```

Takes a bare `git clone` to an agent that answers you, in seven steps:

1. **Host config directory** — `~/.config/mai-tai/`
2. **Stack** — `./dev.sh local up` (generates `.env` secrets, runs migrations)
3. **Agent image** — `docker build -t mai-tai-agent:latest`
4. **Admin account** — registers the first user, or logs in if one exists
5. **Agent credential** — writes the API key to `~/.config/mai-tai/config`, 0600
6. **Model credential** — detects Vertex, or stores an `ANTHROPIC_API_KEY`
7. **Supervisor workspace** — creates it, starts the agent, waits for a check-in

Every step is skipped if it is already done, so re-running after a failure picks
up where it stopped rather than starting over.

Step 1 runs first for a reason. Compose bind-mounts `~/.config/mai-tai` into the
backend, and Docker creates a missing bind-mount source *as root* — do it after
`up` and the operator can no longer write their own config file.

Step 5 is the one nobody discovers on their own. The backend reads
`~/.config/mai-tai/config` off the host to authenticate the containers it
spawns; without it every **Start Agent** click returns *"No Mai-Tai API key
available"* and nothing in the UI says why. The write is merge-preserving,
because `mai-tai-mcp` reads the same file.

Step 7 waits on a row in `workspace_agent_activity`, not on `docker ps`. A
running container is not a working agent — that is the entire lesson of the
watchdog, see `doctor` below.

| Flag | Use |
| --- | --- |
| `--email / --password / --name` | Account details, instead of prompting |
| `--anthropic-key` | Model credential, instead of prompting |
| `--vertex-project` / `--vertex-region` | Auth agents off the host's gcloud ADC instead of a key |
| `--workspace / --template / --model` | Override the default `Supervisor` / `assistant` workspace |
| `--skip-build` | Trust an existing `mai-tai-agent:latest` |
| `--skip-agent` | Stop after step 6; provision no workspace |
| `--non-interactive` | Never prompt; fail instead. For CI |

Secrets also read from the environment — `MAI_TAI_ADMIN_EMAIL`,
`MAI_TAI_ADMIN_PASSWORD`, `MAI_TAI_ADMIN_NAME`, `MAI_TAI_ANTHROPIC_KEY`,
`MAI_TAI_VERTEX_PROJECT`. Prefer these over the flags when scripting: `--password`
lands in argv, which is world-readable in `ps`, and piping into the hidden prompt
does not work — `getpass` falls back to echoing and then reads EOF.

**Check-in is not proof the agent can think.** Step 7 waits for a row in
`workspace_agent_activity`, which the agent writes when its MCP client connects
— *before* it ever calls a model. A workspace whose model is not enabled on your
Vertex project will check in, greet you, and then fail its first real turn with
`exit=1`. If that happens, `docker exec <agent> claude -p hi` names the model and
says so; re-run with `--model opus` (or whatever your project has enabled).

**On Vertex?** `.env.example` ships `CLAUDE_CODE_USE_VERTEX` blank, so a fresh
install has no Vertex config even on a host with working ADC — and step 6 will
ask for an Anthropic key it does not need. `--vertex-project <gcp-project>`
writes the three keys into `.env` and recreates the backend to pick them up. A
*recreate*, not a restart: compose passes environment at create time, so a
restarted container keeps the values it was born with.

## Commands

| Command | What it does |
| --- | --- |
| `mai-tai init` | Bare clone → running stack, admin account, and a live Supervisor agent |
| `mai-tai status` | One row per workspace: runner, uptime, heartbeat age, state, schedules |
| `mai-tai doctor` | Health checks across core containers, bots, orphans, and schedules. Exits 1 on any failure |
| `mai-tai ws list [--archived]` | Every workspace with agent type, message counts, and last-seen |
| `mai-tai describe <ws>` | One workspace in full: runner, agent config, settings, message stats, auth, schedules. Also `mai-tai ws describe` |
| `mai-tai bots list` | Every bot: tmux sessions and agent containers, plus which are configured to start at boot |
| `mai-tai bots start <repo> \| --all` | Start a supervisor window for a repo |
| `mai-tai bots stop <repo>` | Kill a supervisor window for good |
| `mai-tai bots restart <target> [--wait N]` | Bounce a bot by repo name or workspace, then wait for its heartbeat to come back |
| `mai-tai tail <workspace> [-n N] [-f]` | Read a workspace's conversation; `-f` follows |
| `mai-tai config export [--scrub] [--with-env] [out]` | Write a portable copy of the whole deployment |
| `mai-tai config inspect <bundle>` | Show what a bundle holds without restoring it |
| `mai-tai config import <bundle> [--disable-schedules]` | Replace this host's database with a bundle's |
| `mai-tai config check-env` | Report which `.env` keys this host is missing |

`restart` and `stop` are different operations, deliberately. `restart` kills the
`timeout` wrapper and the supervisor relaunches the bot in place — the same
thing the 24h rotation does. `stop` kills the whole supervisor window, so
nothing brings the bot back until you start it or the host reboots.

`bots start --all` is idempotent: repos already running are reported as skipped
and it still exits 0, so it is safe as a "make sure everything is up" call.

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

## Bundles

`mai-tai config export` produces a tar.gz holding `manifest.json`,
`database.sql`, an `env.template` skeleton, and — only with `--with-env` — the
source `.env`. The format is unchanged from `scripts/mai-tai-config.sh` and the
version is deliberately still `2`, so a bundle written here restores on a host
that only has the old shell script.

Three things worth knowing before you rely on it:

- **`--scrub` only strips `users.settings`.** Message history is not scrubbed
  and cannot safely be — agents paste keys into chat. Every export scans the
  dump for credential-shaped strings (`sk-ant-`, `ghp_`, private-key blocks,
  and friends) and prints counts, never values. A non-zero count on a
  `--scrub` bundle means it is still secret.
- **A restored clone is live.** Schedules arrive enabled and start firing on
  the next tick, from a host meant to be a copy. Import says so before the
  prompt; `--disable-schedules` turns them off as part of the restore.
- **`import` is interactive on purpose — there is no `--yes`.** It wipes every
  workspace on the host, and the one place you never want that scriptable is a
  machine where somebody typed the wrong path. With no stdin it aborts rather
  than falling through to the wipe.

Scrubbing happens in a throwaway copy of the database, never in the dump text
and never as an `UPDATE` appended to the restore. A trailing `UPDATE` would
leave the plaintext sitting in the bundle's `COPY` blocks, and those are not
safely regex-editable. Copy → scrub → verify → dump is the only ordering where
the bytes on disk never held a credential; the scratch database is dropped in a
`finally`, because left behind it is unscrubbed live data under a name nobody
would think to look at.

Extraction only ever writes the four known member names. Path traversal and
symlink attacks are impossible by construction rather than by validation — a
tarball is not a trusted input just because you were the one who made it.

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

## What stays in `scripts/`

`scripts/boot-mai-tai.sh` still owns the `@reboot` path and nothing else. That
is on purpose: cron runs it with a bare environment, and this CLI is a
uv-installed Python tool. If booting the bots depended on that venv, a broken
venv after a power cut would mean no bots *and* no CLI to explain why. The boot
path needs nothing but bash, tmux, and claude.

Same reasoning keeps `mai-tai-supervisor.sh` and `verify-boot-cron-env.sh` in
shell — the latter exists specifically to prove the *bare* cron environment
works, so rewriting it in Python would defeat the test. The DNS/TLS/DDNS
scripts are thin `gcloud` and `acme.sh` wrappers with no connection to the
mai-tai data model.

Everything else has moved here. `mai-tai-agent.sh` was deleted (tmux-era agent
runner, superseded by the Docker spawner) and `mai-tai-config.sh` became
`mai-tai config`.

## Design notes

Everything shells out — no psycopg, no docker SDK. The CLI has to work on a bare
deployment host where docker is the only guaranteed dependency, and
`docker exec <pg> psql` is how the repo's scripts have always talked to the
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
uv run --project cli --with pytest python -m pytest cli/tests -q
```

No docker or postgres required — the probe boundary is monkeypatched, so the
tests assert what the checks *conclude*, which is the part that has been wrong
in production.
