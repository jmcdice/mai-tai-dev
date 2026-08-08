"""Host probes: postgres, docker, and the supervisor process tree.

Everything here shells out instead of importing a postgres driver or the docker
SDK. The CLI has to work on a bare deployment host where the only thing
guaranteed to be installed is docker, and `docker exec <pg> psql` is already how
the rest of the repo's scripts talk to the database (see
scripts/mai-tai-config.sh).
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

PG_CONTAINER = os.environ.get("PG_CONTAINER", "maitai-postgres")
PG_USER = os.environ.get("POSTGRES_USER", "maitai")
PG_DB = os.environ.get("POSTGRES_DB", "maitai")

REPOS_ROOT = Path(os.environ.get("MAI_TAI_REPOS_ROOT", str(Path.home() / "repos")))
BOOT_REPOS_CONF = Path(
    os.environ.get("MAI_TAI_BOOT_REPOS", str(Path.home() / ".config/mai-tai/boot-repos.conf"))
)

SUPERVISOR_MARKER = "mai-tai-supervisor.sh"
AGENT_PREFIX = "maitai-agent-"
CORE_CONTAINERS = ("maitai-postgres", "maitai-backend", "maitai-frontend")

# Same thresholds the API uses (backend/app/api/v1/workspaces.py:get_agent_status),
# so the CLI and the web UI never disagree about what "offline" means.
CONNECTED_SECS = 420
IDLE_SECS = 600

# psql field/record separators. Message bodies contain newlines and pipes, so
# the usual `-F '|'` line-per-row parsing corrupts them.
_FS = "\x1f"
_RS = "\x1e"


class ProbeError(RuntimeError):
    """A host probe could not run at all (docker missing, container down, ...)."""


def _run(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError as e:
        raise ProbeError(f"{cmd[0]} not found on PATH") from e
    except subprocess.TimeoutExpired as e:
        raise ProbeError(f"timed out after {timeout}s: {shlex.join(cmd)}") from e


def psql(sql: str) -> list[list[str]]:
    """Run a query and return rows as lists of strings.

    NOTE: no `docker exec -i`. Attaching stdin makes the exec'd process swallow
    whatever is piped into the caller, which silently eats the rest of a script.
    """
    proc = _run(
        [
            "docker", "exec", PG_CONTAINER,
            "psql", "-U", PG_USER, "-d", PG_DB,
            "-tA", "-F", _FS, "-R", _RS, "-c", sql,
        ]
    )
    if proc.returncode != 0:
        raise ProbeError(f"psql failed: {proc.stderr.strip() or proc.stdout.strip()}")
    out = proc.stdout.strip(_RS + "\n")
    if not out:
        return []
    return [rec.split(_FS) for rec in out.split(_RS) if rec.strip()]


@dataclass
class Container:
    name: str
    state: str  # running, exited, created, ...
    status: str  # human string, e.g. "Up 6 days (healthy)"
    image: str = ""

    @property
    def running(self) -> bool:
        return self.state == "running"

    @property
    def healthy(self) -> bool | None:
        """True/False when the container declares a healthcheck, else None."""
        if "(healthy)" in self.status:
            return True
        if "(unhealthy)" in self.status or "(health: starting)" in self.status:
            return False
        return None


def containers() -> dict[str, Container]:
    proc = _run(
        ["docker", "ps", "-a", "--format", "{{.Names}}\t{{.State}}\t{{.Status}}\t{{.Image}}"]
    )
    if proc.returncode != 0:
        raise ProbeError(f"docker ps failed: {proc.stderr.strip()}")
    found: dict[str, Container] = {}
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 4:
            found[parts[0]] = Container(*parts)
    return found


def docker_restart(name: str, grace: int = 30) -> None:
    """Bounce a container. The grace period matters: the agent driver runs a
    memory-flush turn on SIGTERM, and cutting that short loses the journal."""
    proc = _run(["docker", "restart", "-t", str(grace), name], timeout=grace + 60)
    if proc.returncode != 0:
        raise ProbeError(f"docker restart {name} failed: {proc.stderr.strip()}")


def agent_container_name(workspace_id: str) -> str:
    """Mirror of spawner._container_name: prefix + first 8 chars of the UUID."""
    return f"{AGENT_PREFIX}{workspace_id[:8]}"


@dataclass
class Session:
    """One host-side bot: a supervisor window and the process tree under it."""

    repo: str
    repo_dir: str
    supervisor_pid: int
    timeout_pid: int | None  # the `timeout` wrapper; this is what you kill
    claude_pid: int | None

    @property
    def alive(self) -> bool:
        return self.claude_pid is not None


def _ps_table() -> list[tuple[int, int, str]]:
    proc = _run(["ps", "-eo", "pid=,ppid=,args="])
    if proc.returncode != 0:
        raise ProbeError(f"ps failed: {proc.stderr.strip()}")
    rows: list[tuple[int, int, str]] = []
    for line in proc.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            rows.append((int(parts[0]), int(parts[1]), parts[2]))
    return rows


def sessions() -> list[Session]:
    """Find every running supervisor and the claude process beneath it."""
    rows = _ps_table()
    by_parent: dict[int, list[tuple[int, str]]] = {}
    for pid, ppid, args in rows:
        by_parent.setdefault(ppid, []).append((pid, args))

    found: list[Session] = []
    for pid, _ppid, args in rows:
        # Match the supervisor itself, not the tmux new-session that spawned it.
        if SUPERVISOR_MARKER not in args or args.startswith("tmux "):
            continue
        parts = shlex.split(args)
        repo_dir = parts[-1] if parts else ""
        if not repo_dir.startswith("/"):
            continue

        timeout_pid = claude_pid = None
        for child_pid, child_args in by_parent.get(pid, []):
            if child_args.startswith("timeout "):
                timeout_pid = child_pid
                for gc_pid, gc_args in by_parent.get(child_pid, []):
                    if gc_args.startswith("claude "):
                        claude_pid = gc_pid
            elif child_args.startswith("claude "):
                # ROTATE_AFTER=0 runs claude without the timeout wrapper.
                claude_pid = child_pid
        found.append(
            Session(
                repo=Path(repo_dir).name,
                repo_dir=repo_dir,
                supervisor_pid=pid,
                timeout_pid=timeout_pid,
                claude_pid=claude_pid,
            )
        )
    return sorted(found, key=lambda s: s.repo)


def boot_repos() -> list[str]:
    """Repos configured to auto-start a session, from boot-repos.conf."""
    if not BOOT_REPOS_CONF.exists():
        return []
    names = []
    for line in BOOT_REPOS_CONF.read_text().splitlines():
        line = line.split("#", 1)[0].strip().rstrip("/")
        if line:
            names.append(Path(line).name)
    return names


def workspace_id_for_repo_dir(repo_dir: str | Path) -> str | None:
    """Read MAI_TAI_WORKSPACE_ID out of a repo directory's .env.mai-tai."""
    env_file = Path(repo_dir) / ".env.mai-tai"
    if not env_file.exists():
        return None
    for line in env_file.read_text().splitlines():
        key, _, value = line.partition("=")
        if key.strip() == "MAI_TAI_WORKSPACE_ID":
            return value.strip().strip("\"'") or None
    return None


def repo_workspace_id(repo: str) -> str | None:
    """Same, addressed by repo name under REPOS_ROOT."""
    return workspace_id_for_repo_dir(REPOS_ROOT / repo)


@dataclass
class Workspace:
    id: str
    name: str
    workspace_type: str
    archived: bool
    heartbeat_secs: int | None  # None = never seen
    schedules_total: int
    schedules_enabled: int
    messages: int
    # Pulled out of agent_config; both None on a plain chat workspace.
    runtime: str | None = None
    template: str | None = None

    @property
    def state(self) -> str:
        if self.heartbeat_secs is None:
            return "never"
        if self.heartbeat_secs < CONNECTED_SECS:
            return "connected"
        if self.heartbeat_secs < IDLE_SECS:
            return "idle"
        return "offline"

    @property
    def kind(self) -> str:
        """`chat`, or the agent's template — what you actually want in a list."""
        if self.workspace_type != "agent":
            return self.workspace_type
        return f"agent/{self.template}" if self.template else "agent"


_WORKSPACES_SQL = """
select w.id::text,
       w.name,
       w.workspace_type,
       w.archived,
       coalesce(round(extract(epoch from (now() at time zone 'utc')
                              - a.last_activity_at))::text, ''),
       (select count(*) from scheduled_tasks s where s.workspace_id = w.id),
       (select count(*) from scheduled_tasks s where s.workspace_id = w.id and s.enabled),
       (select count(*) from messages m where m.workspace_id = w.id),
       coalesce(w.agent_config->>'runtime', ''),
       coalesce(w.agent_config->>'template', '')
from workspaces w
left join workspace_agent_activity a on a.workspace_id = w.id
order by w.archived, lower(w.name)
"""


def workspaces(include_archived: bool = False) -> list[Workspace]:
    found = []
    for row in psql(_WORKSPACES_SQL):
        ws = Workspace(
            id=row[0],
            name=row[1],
            workspace_type=row[2],
            archived=row[3] == "t",
            heartbeat_secs=int(row[4]) if row[4] else None,
            schedules_total=int(row[5]),
            schedules_enabled=int(row[6]),
            messages=int(row[7]),
            runtime=row[8] or None,
            template=row[9] or None,
        )
        if ws.archived and not include_archived:
            continue
        found.append(ws)
    return found


def resolve_workspace(needle: str, include_archived: bool = True) -> Workspace:
    """Find one workspace by id prefix, exact name, or case-insensitive substring."""
    all_ws = workspaces(include_archived=include_archived)
    lowered = needle.lower()
    for ws in all_ws:
        if ws.id == needle or ws.name.lower() == lowered:
            return ws
    partial = [ws for ws in all_ws if ws.id.startswith(needle) or lowered in ws.name.lower()]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        raise ProbeError(f"no workspace matches {needle!r}")
    names = ", ".join(sorted(ws.name for ws in partial))
    raise ProbeError(f"{needle!r} is ambiguous: {names}")


def heartbeat_secs(workspace_id: str) -> int | None:
    """Seconds since this workspace last touched the API; None if never."""
    rows = psql(
        "select round(extract(epoch from (now() at time zone 'utc') - last_activity_at))"
        f" from workspace_agent_activity where workspace_id = '{workspace_id}'"
    )
    if not rows or not rows[0][0]:
        return None
    return int(rows[0][0])


@dataclass
class Schedule:
    workspace: str
    name: str
    cron_expression: str
    timezone: str
    overdue_secs: int | None  # >0 means next_run_at is in the past
    last_status: str
    enabled: bool = True
    wake_agent: bool = True
    last_run_secs: int | None = None

    @property
    def next_in_secs(self) -> int | None:
        """Seconds until the next fire; negative once it is overdue."""
        return None if self.overdue_secs is None else -self.overdue_secs


_SCHEDULES_SQL = """
select w.name,
       s.name,
       s.cron_expression,
       s.timezone,
       coalesce(round(extract(epoch from (now() at time zone 'utc') - s.next_run_at))::text, ''),
       coalesce(s.last_status, ''),
       s.enabled,
       s.wake_agent,
       coalesce(round(extract(epoch from (now() at time zone 'utc') - s.last_run_at))::text, '')
from scheduled_tasks s
join workspaces w on w.id = s.workspace_id
where {where}
order by lower(w.name), lower(s.name)
"""


def _schedules(where: str) -> list[Schedule]:
    return [
        Schedule(
            workspace=row[0],
            name=row[1],
            cron_expression=row[2],
            timezone=row[3],
            overdue_secs=int(row[4]) if row[4] else None,
            last_status=row[5],
            enabled=row[6] == "t",
            wake_agent=row[7] == "t",
            last_run_secs=int(row[8]) if row[8] else None,
        )
        for row in psql(_SCHEDULES_SQL.format(where=where))
        if len(row) >= 9
    ]


def enabled_schedules() -> list[Schedule]:
    return _schedules("s.enabled")


def schedules_for(workspace_id: str) -> list[Schedule]:
    """Every schedule on one workspace, disabled ones included."""
    return _schedules(f"s.workspace_id = '{workspace_id}'")


_MESSAGES_SQL = """
select m.id::text,
       to_char(m.created_at, 'YYYY-MM-DD HH24:MI:SS'),
       to_char(m.created_at, 'YYYY-MM-DD HH24:MI:SS.US'),
       case when m.user_id is not null then 'human'
            else coalesce(m.agent_name, 'agent') end,
       m.message_type,
       m.content
from messages m
where m.workspace_id = '{workspace_id}'
  {extra}
order by m.created_at desc, m.id
limit {limit}
"""


@dataclass
class Message:
    id: str
    created_at: str  # second precision, for display
    cursor: str  # microsecond precision, for paging
    author: str
    message_type: str
    content: str


@dataclass
class Detail:
    """The slow-moving configuration of one workspace."""

    created_at: str
    owner: str
    purpose: str
    agent_config: dict = field(default_factory=dict)
    settings: dict = field(default_factory=dict)


_DETAIL_SQL = """
select to_char(w.created_at, 'YYYY-MM-DD HH24:MI'),
       coalesce(u.email, ''),
       coalesce(w.agent_purpose, ''),
       coalesce(w.agent_config::text, '{{}}'),
       coalesce(w.settings::text, '{{}}')
from workspaces w
left join users u on u.id = w.owner_id
where w.id = '{workspace_id}'
"""


def _json_obj(raw: str) -> dict:
    """Parse a jsonb column that may legitimately hold the literal `null`."""
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def detail(workspace_id: str) -> Detail:
    rows = psql(_DETAIL_SQL.format(workspace_id=workspace_id))
    if not rows:
        raise ProbeError(f"workspace {workspace_id} disappeared mid-query")
    row = rows[0]
    return Detail(
        created_at=row[0],
        owner=row[1],
        purpose=row[2],
        agent_config=_json_obj(row[3]),
        settings=_json_obj(row[4]),
    )


@dataclass
class MessageStats:
    total: int
    from_human: int
    from_agent: int
    first_at: str
    last_at: str
    last_24h: int
    busiest_day: str
    busiest_count: int


_MESSAGE_STATS_SQL = """
select count(*),
       count(*) filter (where user_id is not null),
       count(*) filter (where user_id is null),
       coalesce(to_char(min(created_at), 'YYYY-MM-DD HH24:MI'), ''),
       coalesce(to_char(max(created_at), 'YYYY-MM-DD HH24:MI'), ''),
       count(*) filter (where created_at > (now() at time zone 'utc') - interval '24 hours')
from messages where workspace_id = '{workspace_id}'
"""

_BUSIEST_DAY_SQL = """
select to_char(created_at, 'YYYY-MM-DD'), count(*)
from messages where workspace_id = '{workspace_id}'
group by 1 order by 2 desc, 1 desc limit 1
"""


def message_stats(workspace_id: str) -> MessageStats:
    rows = psql(_MESSAGE_STATS_SQL.format(workspace_id=workspace_id))
    row = rows[0] if rows else ["0", "0", "0", "", "", "0"]
    busiest = psql(_BUSIEST_DAY_SQL.format(workspace_id=workspace_id))
    return MessageStats(
        total=int(row[0]),
        from_human=int(row[1]),
        from_agent=int(row[2]),
        first_at=row[3],
        last_at=row[4],
        last_24h=int(row[5]),
        busiest_day=busiest[0][0] if busiest else "",
        busiest_count=int(busiest[0][1]) if busiest else 0,
    )


@dataclass
class ApiKey:
    name: str
    scopes: str
    last_used_secs: int | None
    expired: bool
    workspace_scoped: bool
    shared_with: int  # how many OTHER workspaces authenticate with this key


# Keyed off workspace_agent_activity, not api_keys.workspace_id: a key can be
# user-scoped (workspace_id NULL) and still be the credential a workspace's
# agent actually presents. Filtering on api_keys.workspace_id reports "no keys"
# for a workspace that is plainly authenticating right now.
_AUTH_SQL = """
select coalesce(k.name, '(unnamed)'),
       coalesce(array_to_string(k.scopes, ','), ''),
       coalesce(round(extract(epoch from (now() at time zone 'utc') - k.last_used_at))::text, ''),
       coalesce((k.expires_at < (now() at time zone 'utc'))::text, 'f'),
       (k.workspace_id is not null)::text,
       (select count(*) - 1 from workspace_agent_activity a2 where a2.api_key_id = k.id)::text
from workspace_agent_activity a
join api_keys k on k.id = a.api_key_id
where a.workspace_id = '{workspace_id}'
"""


def auth_key(workspace_id: str) -> ApiKey | None:
    """The key this workspace's agent last authenticated with, if any.

    Never returns the key material or its hash — only the metadata an operator
    needs to answer "what is this agent using, and who else uses it?".
    """
    rows = psql(_AUTH_SQL.format(workspace_id=workspace_id))
    if not rows or len(rows[0]) < 6:
        return None
    row = rows[0]
    return ApiKey(
        name=row[0],
        scopes=row[1],
        last_used_secs=int(row[2]) if row[2] else None,
        expired=row[3] == "t",
        workspace_scoped=row[4] == "t",
        shared_with=max(0, int(row[5])),
    )


def messages(workspace_id: str, limit: int = 20, since: str | None = None) -> list[Message]:
    """Most recent messages first; pass `since` (a Message.cursor) to page forward.

    Paging keys off the microsecond cursor, not the displayed timestamp: two
    messages posted in the same second are common in a busy channel, and a
    second-precision `>` silently drops the second one.
    """
    extra = f"and m.created_at > '{since}'" if since else ""
    sql = _MESSAGES_SQL.format(workspace_id=workspace_id, extra=extra, limit=limit)
    return [Message(*row[:6]) for row in psql(sql) if len(row) >= 6]
