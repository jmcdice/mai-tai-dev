"""`mai-tai` — operator CLI for a Mai-Tai deployment.

Runs on the host that owns the deployment: it needs the docker socket, the
postgres container, and the supervisor process tree. That is exactly why it is
not part of the mai-tai-mcp package — agents get the MCP server, operators get
this.
"""

from __future__ import annotations

import os
import signal
import sys
import time
from dataclasses import dataclass
from typing import NoReturn

import typer
from rich.console import Console
from rich.table import Table

from . import __version__, probes
from .probes import ProbeError

app = typer.Typer(
    help="Operator CLI for a Mai-Tai deployment.",
    add_completion=False,
)
ws_app = typer.Typer(help="Workspaces.", no_args_is_help=True)
bots_app = typer.Typer(help="Bot sessions and agent containers.", no_args_is_help=True)
app.add_typer(ws_app, name="ws")
app.add_typer(bots_app, name="bots")

console = Console()
err_console = Console(stderr=True)

STATE_COLOR = {
    "connected": "green",
    "idle": "yellow",
    "offline": "red",
    "never": "dim",
}


def _age(secs: int | None) -> str:
    if secs is None:
        return "never"
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m"
    if secs < 86400:
        return f"{secs // 3600}h{(secs % 3600) // 60:02d}m"
    return f"{secs // 86400}d{(secs % 86400) // 3600:02d}h"


def _countdown(secs: int | None) -> str:
    """`_age` for a value that may be in the future."""
    if secs is None:
        return "—"
    return f"in {_age(secs)}" if secs >= 0 else f"[red]{_age(-secs)} overdue[/red]"


@dataclass
class Runner:
    """Whatever is actually executing a workspace's agent, if anything."""

    kind: str  # container | session | none
    label: str
    up: bool
    session: probes.Session | None = None
    container: probes.Container | None = None


def _runners(workspaces: list[probes.Workspace]) -> dict[str, Runner]:
    """Map workspace id -> the container or host session running it."""
    containers = probes.containers()
    by_workspace: dict[str, Runner] = {}

    for session in probes.sessions():
        ws_id = probes.workspace_id_for_repo_dir(session.repo_dir)
        if ws_id:
            by_workspace[ws_id] = Runner(
                kind="session",
                label=f"tmux:{session.repo}",
                up=session.alive,
                session=session,
            )

    for ws in workspaces:
        if ws.id in by_workspace:
            continue
        name = probes.agent_container_name(ws.id)
        container = containers.get(name)
        if container:
            by_workspace[ws.id] = Runner(
                kind="container",
                label=name,
                up=container.running,
                container=container,
            )
        else:
            by_workspace[ws.id] = Runner(kind="none", label="—", up=False)

    return by_workspace


def _fail(message: str) -> NoReturn:
    err_console.print(f"[red]error:[/red] {message}")
    raise typer.Exit(code=2)


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", help="Show version and exit."),
) -> None:
    if version:
        console.print(f"mai-tai {__version__}")
        raise typer.Exit()
    # `no_args_is_help` on the group would swallow `--version`, so do it here.
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit()


@app.command()
def status(
    archived: bool = typer.Option(False, "--archived", help="Include archived workspaces."),
) -> None:
    """One line per workspace: what's running it and how fresh its heartbeat is."""
    workspaces = probes.workspaces(include_archived=archived)
    runners = _runners(workspaces)

    table = Table(title="Mai-Tai workspaces", title_justify="left", header_style="bold")
    table.add_column("Workspace")
    table.add_column("Type")
    table.add_column("Runner")
    table.add_column("Up", justify="center")
    table.add_column("Heartbeat", justify="right")
    table.add_column("State")
    table.add_column("Sched", justify="right")

    for ws in workspaces:
        runner = runners[ws.id]
        state = ws.state
        sched = (
            f"{ws.schedules_enabled}/{ws.schedules_total}" if ws.schedules_total else "—"
        )
        table.add_row(
            f"[dim]{ws.name}[/dim]" if ws.archived else ws.name,
            ws.kind,
            runner.label,
            "[green]yes[/green]" if runner.up else "[red]no[/red]",
            _age(ws.heartbeat_secs),
            f"[{STATE_COLOR[state]}]{state}[/{STATE_COLOR[state]}]",
            sched,
        )

    console.print(table)


@ws_app.command("list")
def ws_list(
    archived: bool = typer.Option(False, "--archived", help="Include archived workspaces."),
) -> None:
    """Every workspace, with ids you can paste into other commands."""
    workspaces = probes.workspaces(include_archived=archived)

    table = Table(title="Workspaces", title_justify="left", header_style="bold")
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Msgs", justify="right")
    table.add_column("Sched", justify="right")
    table.add_column("Last seen", justify="right")
    table.add_column("")

    for ws in workspaces:
        table.add_row(
            ws.id[:8],
            ws.name,
            ws.kind,
            str(ws.messages),
            f"{ws.schedules_enabled}/{ws.schedules_total}" if ws.schedules_total else "—",
            _age(ws.heartbeat_secs),
            "[dim]archived[/dim]" if ws.archived else "",
        )

    console.print(table)
    console.print(f"[dim]{len(workspaces)} workspace(s)[/dim]")


def _kv(rows: list[tuple[str, str]], indent: str = "  ") -> None:
    """Print aligned key/value lines. Values may contain rich markup."""
    if not rows:
        return
    width = max(len(key) for key, _ in rows)
    for key, value in rows:
        console.print(f"{indent}[dim]{key.ljust(width)}[/dim]  {value}")


def _runner_rows(ws: probes.Workspace, runner: Runner) -> list[tuple[str, str]]:
    state = ws.state
    rows = [
        ("runner", f"{runner.label} ({runner.kind})" if runner.kind != "none" else "[dim]—[/dim]"),
        ("up", "[green]yes[/green]" if runner.up else "[red]no[/red]"),
        ("state", f"[{STATE_COLOR[state]}]{state}[/{STATE_COLOR[state]}]"),
        ("heartbeat", f"{_age(ws.heartbeat_secs)} ago" if ws.heartbeat_secs is not None else "never"),
    ]
    if runner.container is not None:
        rows.append(("image", runner.container.image or "—"))
        rows.append(("uptime", runner.container.status))
    if runner.session is not None:
        pids = f"supervisor {runner.session.supervisor_pid}"
        if runner.session.timeout_pid:
            pids += f", timeout {runner.session.timeout_pid}"
        if runner.session.claude_pid:
            pids += f", claude {runner.session.claude_pid}"
        rows.append(("repo", runner.session.repo_dir))
        rows.append(("pids", pids))
    return rows


@app.command()
def describe(
    workspace: str = typer.Argument(..., help="Workspace name or id prefix."),
) -> None:
    """Everything known about one workspace: runner, agent config, and stats."""
    try:
        ws = probes.resolve_workspace(workspace)
    except ProbeError as e:
        _fail(str(e))

    info = probes.detail(ws.id)
    runner = _runners([ws])[ws.id]
    stats = probes.message_stats(ws.id)
    key = probes.auth_key(ws.id)
    schedules = probes.schedules_for(ws.id)

    archived = " [dim](archived)[/dim]" if ws.archived else ""
    console.print(f"\n[bold]{ws.name}[/bold]{archived}  [dim]{ws.id}[/dim]")
    if info.purpose:
        console.print(f"[italic dim]{info.purpose.strip()}[/italic dim]")
    console.print()

    _kv(
        [
            ("type", ws.kind),
            ("owner", info.owner or "—"),
            ("created", info.created_at),
            *_runner_rows(ws, runner),
        ]
    )

    # agent_config is the spawner's input: runtime, model, template, repo_url.
    # Show it verbatim rather than a curated subset, so a key we don't know
    # about yet still shows up here instead of being silently dropped.
    value_width = max(40, console.width - 24)

    console.print("\n[bold]Agent config[/bold]")
    if info.agent_config:
        _kv([(k, _scalar(v, value_width)) for k, v in sorted(info.agent_config.items())])
    else:
        console.print("  [dim]none — not an agent workspace[/dim]")

    if info.settings:
        console.print("\n[bold]Settings[/bold]")
        _kv([(k, _scalar(v, value_width)) for k, v in sorted(info.settings.items())])

    console.print("\n[bold]Messages[/bold]")
    _kv(
        [
            ("total", f"{stats.total}  [dim]({stats.from_human} human / {stats.from_agent} agent)[/dim]"),
            ("last 24h", str(stats.last_24h)),
            ("first", stats.first_at or "—"),
            ("latest", stats.last_at or "—"),
            ("busiest day", f"{stats.busiest_day} ({stats.busiest_count})" if stats.busiest_day else "—"),
        ]
    )

    console.print("\n[bold]Auth[/bold]")
    if key is None:
        console.print("  [dim]this workspace has never authenticated[/dim]")
    else:
        scope = "workspace-scoped" if key.workspace_scoped else "[yellow]user-scoped[/yellow]"
        if key.shared_with:
            scope += f" — shared with {key.shared_with} other workspace(s)"
        used = f"{_age(key.last_used_secs)} ago" if key.last_used_secs is not None else "never"
        _kv(
            [
                ("key", key.name + (" [red](expired)[/red]" if key.expired else "")),
                ("scopes", key.scopes or "none"),
                ("scope", scope),
                ("last used", used),
            ]
        )

    console.print(
        f"\n[bold]Schedules[/bold] [dim]({ws.schedules_enabled} enabled / {len(schedules)})[/dim]"
    )
    if not schedules:
        console.print("  [dim]none[/dim]")
    else:
        table = Table(box=None, show_header=False, pad_edge=False, padding=(0, 1))
        for sched in schedules:
            last = f"last {_age(sched.last_run_secs)} ago" if sched.last_run_secs else "never run"
            if sched.last_status == "error":
                last += " [yellow](error)[/yellow]"
            table.add_row(
                "[green]✓[/green]" if sched.enabled else "[dim]○[/dim]",
                sched.name + ("" if sched.wake_agent else " [dim](no-wake)[/dim]"),
                f"[dim]{sched.cron_expression}[/dim]",
                f"[dim]{sched.timezone}[/dim]",
                _countdown(sched.next_in_secs) if sched.enabled else "[dim]disabled[/dim]",
                f"[dim]{last}[/dim]",
            )
        console.print(table)
    console.print()


def _scalar(value: object, width: int = 100) -> str:
    if value is None:
        return "[dim]—[/dim]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        # project_context and friends run to paragraphs. Collapse to one line
        # and clip to the terminal, or the wrap lands back in column zero and
        # the key/value alignment stops meaning anything.
        collapsed = " ".join(value.split())
        return collapsed if len(collapsed) <= width else collapsed[: width - 3] + "..."
    return str(value)


# Reachable both ways: `mai-tai describe X` is what you type, `mai-tai ws
# describe X` is where you look for it after using `mai-tai ws list`.
ws_app.command("describe")(describe)


@dataclass
class Check:
    level: str  # ok | warn | fail
    title: str
    detail: str = ""


def _check_core(containers: dict[str, probes.Container]) -> list[Check]:
    checks = []
    for name in probes.CORE_CONTAINERS:
        container = containers.get(name)
        if container is None:
            checks.append(Check("fail", f"{name} missing", "container does not exist"))
        elif not container.running:
            checks.append(Check("fail", f"{name} not running", container.status))
        elif container.healthy is False:
            checks.append(Check("warn", f"{name} unhealthy", container.status))
        else:
            checks.append(Check("ok", name, container.status))
    return checks


def _check_bots(
    workspaces: list[probes.Workspace], runners: dict[str, Runner]
) -> list[Check]:
    checks = []
    for ws in workspaces:
        runner = runners[ws.id]
        if runner.kind == "none":
            continue  # a chat workspace nobody is running is not a fault
        if not runner.up:
            checks.append(
                Check("fail", f"{ws.name}: runner down", f"{runner.label} is not running")
            )
            continue
        if ws.state == "connected":
            checks.append(Check("ok", ws.name, f"{runner.label}, {_age(ws.heartbeat_secs)} ago"))
        elif ws.state == "idle":
            checks.append(
                Check("warn", f"{ws.name}: heartbeat slow", f"last seen {_age(ws.heartbeat_secs)} ago")
            )
        else:
            # The one that bit us: process alive, MCP client gave up. `ps` says
            # healthy, the bot has been talking to nobody for hours.
            checks.append(
                Check(
                    "fail",
                    f"{ws.name}: alive but not talking",
                    f"{runner.label} is up, last heartbeat {_age(ws.heartbeat_secs)} ago "
                    f"— likely an MCP client drop. Fix: mai-tai bots restart {ws.name!r}",
                )
            )
    return checks


def _check_supervisors() -> list[Check]:
    configured = probes.boot_repos()
    if not configured:
        return []
    running = {session.repo for session in probes.sessions()}
    missing = [repo for repo in configured if repo not in running]
    if missing:
        return [
            Check(
                "fail",
                "supervisor windows missing",
                f"configured but not running: {', '.join(missing)} "
                "— start with scripts/boot-mai-tai.sh --start <repo>",
            )
        ]
    return [Check("ok", "supervisors", f"{len(configured)} configured, all running")]


def _check_orphans(
    workspaces: list[probes.Workspace], containers: dict[str, probes.Container]
) -> list[Check]:
    expected = {probes.agent_container_name(ws.id) for ws in workspaces}
    orphans = [
        name
        for name, container in containers.items()
        if name.startswith(probes.AGENT_PREFIX) and container.running and name not in expected
    ]
    if orphans:
        return [
            Check(
                "warn",
                "orphan agent containers",
                f"{', '.join(sorted(orphans))} — running with no active workspace",
            )
        ]
    return []


def _check_schedules() -> list[Check]:
    checks = []
    schedules = probes.enabled_schedules()
    if not schedules:
        return [Check("ok", "schedules", "none enabled")]

    # next_run_at drifting into the past means the scheduler loop is not
    # advancing tasks. A minute of slack absorbs normal tick latency.
    overdue = [s for s in schedules if s.overdue_secs and s.overdue_secs > 60]
    errored = [s for s in schedules if s.last_status == "error"]

    if overdue:
        detail = ", ".join(f"{s.workspace}/{s.name} ({_age(s.overdue_secs)} late)" for s in overdue)
        checks.append(Check("fail", "scheduler not advancing", detail))
    if errored:
        detail = ", ".join(f"{s.workspace}/{s.name}" for s in errored)
        checks.append(Check("warn", "schedules last ran with an error", detail))
    if not overdue and not errored:
        checks.append(Check("ok", "schedules", f"{len(schedules)} enabled, all on time"))
    return checks


@app.command()
def doctor() -> None:
    """Run the health checks an operator would otherwise run by hand.

    Exits non-zero if anything failed, so it works in a cron or a CI step.
    """
    containers = probes.containers()
    workspaces = probes.workspaces()
    runners = _runners(workspaces)

    checks = [
        *_check_core(containers),
        *_check_supervisors(),
        *_check_bots(workspaces, runners),
        *_check_orphans(workspaces, containers),
        *_check_schedules(),
    ]

    marks = {"ok": "[green]✓[/green]", "warn": "[yellow]![/yellow]", "fail": "[red]✗[/red]"}
    for check in checks:
        line = f"  {marks[check.level]} {check.title}"
        if check.detail:
            line += f"  [dim]{check.detail}[/dim]"
        console.print(line)

    fails = sum(1 for c in checks if c.level == "fail")
    warns = sum(1 for c in checks if c.level == "warn")
    console.print()
    if fails:
        console.print(f"[red]{fails} failed[/red], {warns} warning(s), {len(checks)} checks")
        raise typer.Exit(code=1)
    console.print(f"[green]all clear[/green] — {warns} warning(s), {len(checks)} checks")


def _wait_for_heartbeat(workspace_id: str, timeout: int) -> int | None:
    """Poll until the workspace reports a fresh heartbeat, or give up."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(5)
        secs = probes.heartbeat_secs(workspace_id)
        if secs is not None and secs < probes.CONNECTED_SECS:
            return secs
    return None


@bots_app.command("restart")
def bots_restart(
    target: str = typer.Argument(..., help="Repo name, workspace name, or id prefix."),
    wait: int = typer.Option(180, "--wait", help="Seconds to wait for the heartbeat to return."),
) -> None:
    """Restart a bot: kill the session (the supervisor relaunches it) or bounce the container."""
    session = next((s for s in probes.sessions() if s.repo == target), None)

    if session is None:
        try:
            ws = probes.resolve_workspace(target)
        except ProbeError as e:
            _fail(str(e))
        runner = _runners([ws])[ws.id]
        if runner.kind == "session":
            session = runner.session
        elif runner.kind == "container":
            console.print(f"Restarting container [bold]{runner.label}[/bold]...")
            probes.docker_restart(runner.label)
            _report_recovery(ws.id, ws.name, wait)
            return
        else:
            _fail(f"{ws.name!r} has nothing running to restart")

    ws_id = probes.workspace_id_for_repo_dir(session.repo_dir)
    # Kill the `timeout` wrapper, not claude: the supervisor's loop is watching
    # that pid, and killing it is exactly what the 24h rotation does.
    pid = session.timeout_pid or session.claude_pid
    if pid is None:
        _fail(f"session {session.repo!r} has a supervisor but no claude process to kill")

    console.print(f"Killing [bold]{session.repo}[/bold] (pid {pid}); supervisor relaunches in ~3s...")
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        _fail(f"pid {pid} vanished before we could signal it")
    except PermissionError:
        _fail(f"not permitted to signal pid {pid} — run as the user that owns the session")

    if ws_id is None:
        console.print(
            f"[yellow]![/yellow] no .env.mai-tai in {session.repo_dir}, cannot verify the heartbeat"
        )
        return
    _report_recovery(ws_id, session.repo, wait)


def _report_recovery(workspace_id: str, label: str, wait: int) -> None:
    console.print(f"Waiting up to {wait}s for {label} to check in...")
    secs = _wait_for_heartbeat(workspace_id, wait)
    if secs is None:
        err_console.print(
            f"[red]✗[/red] {label} has not checked in after {wait}s — "
            "look at the tmux pane or `docker logs`"
        )
        raise typer.Exit(code=1)
    console.print(f"[green]✓[/green] {label} is back — heartbeat {_age(secs)} ago")


@app.command()
def tail(
    workspace: str = typer.Argument(..., help="Workspace name or id prefix."),
    limit: int = typer.Option(20, "--limit", "-n", help="How much backlog to show."),
    follow: bool = typer.Option(False, "--follow", "-f", help="Keep printing new messages."),
    interval: float = typer.Option(3.0, "--interval", help="Poll seconds when following."),
) -> None:
    """Print a channel's messages, optionally following like `tail -f`."""
    try:
        ws = probes.resolve_workspace(workspace)
    except ProbeError as e:
        _fail(str(e))

    console.print(f"[dim]— {ws.name} ({ws.id[:8]}) —[/dim]")
    backlog = list(reversed(probes.messages(ws.id, limit=limit)))
    for message in backlog:
        _print_message(message)

    if not follow:
        return

    since = backlog[-1].cursor if backlog else "1970-01-01"
    try:
        while True:
            time.sleep(interval)
            fresh = list(reversed(probes.messages(ws.id, limit=100, since=since)))
            for message in fresh:
                _print_message(message)
                since = message.cursor
    except KeyboardInterrupt:
        console.print("[dim]— stopped —[/dim]")


def _print_message(message: probes.Message) -> None:
    color = "cyan" if message.author == "human" else "magenta"
    suffix = "" if message.message_type == "chat" else f" [dim]({message.message_type})[/dim]"
    console.print(f"[dim]{message.created_at}[/dim] [{color}]{message.author}[/{color}]{suffix}")
    console.print(message.content.strip(), markup=False, highlight=False)
    console.print()


def main() -> None:
    try:
        app()
    except ProbeError as e:
        err_console.print(f"[red]error:[/red] {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
