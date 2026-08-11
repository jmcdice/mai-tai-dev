"""`mai-tai` — operator CLI for a Mai-Tai deployment.

Runs on the host that owns the deployment: it needs the docker socket, the
postgres container, and the supervisor process tree. That is exactly why it is
not part of the mai-tai-mcp package — agents get the MCP server, operators get
this.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import sys
import tempfile
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

import typer
from rich.console import Console
from rich.table import Table

from . import __version__, bootstrap, bundle, probes
from .probes import ProbeError

app = typer.Typer(
    help="Operator CLI for a Mai-Tai deployment.",
    add_completion=False,
)
ws_app = typer.Typer(help="Workspaces.", no_args_is_help=True)
bots_app = typer.Typer(help="Bot sessions and agent containers.", no_args_is_help=True)
config_app = typer.Typer(help="Move a whole deployment between hosts.", no_args_is_help=True)
app.add_typer(ws_app, name="ws")
app.add_typer(bots_app, name="bots")
app.add_typer(config_app, name="config")

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


def _check_turns(workspaces: list[probes.Workspace], runners: dict[str, Runner]) -> list[Check]:
    """The gap every other check has: connected, and answering nothing.

    Heartbeats prove the MCP client is attached, not that a model replies. An
    agent pointed at a model its project hasn't enabled checks in, greets you,
    and then fails every turn — `status` shows `connected`, `docker ps` shows
    Up, and the whole thing reads as a working install.
    """
    health = probes.turn_health()
    checks = []
    for ws in workspaces:
        if runners[ws.id].kind == "none":
            continue
        turns = health.get(ws.id)
        if turns is None or not turns.failed:
            continue
        if turns.succeeded:
            checks.append(
                Check(
                    "warn",
                    f"{ws.name}: some turns failing",
                    f"{turns.failed} of {turns.failed + turns.succeeded} replies in the "
                    f"last 24h were errors, most recently {turns.last_failure_at}",
                )
            )
        else:
            checks.append(
                Check(
                    "fail",
                    f"{ws.name}: connected but not answering",
                    f"all {turns.failed} turn(s) in the last 24h failed, most recently "
                    f"{turns.last_failure_at} — the agent is up and checking in but no "
                    "reply is getting through. Often a model the project has not enabled; "
                    f"`docker exec {runners[ws.id].label} claude -p hi` names it.",
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
                f"— start with: mai-tai bots start {missing[0]}",
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
        *_check_turns(workspaces, runners),
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


def _step(n: int, total: int, title: str) -> None:
    console.print(f"\n[bold]({n}/{total}) {title}[/bold]")


def _ok(message: str) -> None:
    console.print(f"  [green]✓[/green] {message}")


def _skip(message: str) -> None:
    console.print(f"  [dim]·[/dim] [dim]{message}[/dim]")


def _warn(message: str) -> None:
    console.print(f"  [yellow]![/yellow] {message}")


@app.command()
def init(  # noqa: C901 - a setup wizard is a sequence; splitting it hides the order
    email: str = typer.Option(None, "--email", help="Admin account email."),
    password: str = typer.Option(None, "--password", help="Admin password. Prompted if omitted."),
    name: str = typer.Option(None, "--name", help="Display name for the admin account."),
    anthropic_key: str = typer.Option(
        None, "--anthropic-key", help="Anthropic API key for agents. Ignored when Vertex is set up."
    ),
    workspace_name: str = typer.Option(
        bootstrap.DEFAULT_WORKSPACE_NAME, "--workspace", help="Name of the first agent workspace."
    ),
    template: str = typer.Option(
        bootstrap.DEFAULT_TEMPLATE, "--template", help="Agent template for that workspace."
    ),
    model: str = typer.Option(None, "--model", help="Model for the agent (default: runtime's)."),
    vertex_project: str = typer.Option(
        None, "--vertex-project", help="Auth agents via Vertex using this GCP project."
    ),
    vertex_region: str = typer.Option(
        "global", "--vertex-region", help="Vertex region, with --vertex-project."
    ),
    api_url: str = typer.Option(
        bootstrap.DEFAULT_API_URL, "--api-url", help="Backend URL as seen from this host."
    ),
    skip_build: bool = typer.Option(False, "--skip-build", help="Don't build the agent image."),
    skip_agent: bool = typer.Option(
        False, "--skip-agent", help="Provision everything but don't start the agent."
    ),
    non_interactive: bool = typer.Option(
        False, "--non-interactive", help="Never prompt; fail instead. For CI."
    ),
) -> None:
    """Take a fresh clone all the way to an agent you can talk to.

    Idempotent: every step checks whether it has already been done, so running
    this twice is safe and tells you what the host already has.
    """
    total = 7

    # Secrets come from the environment when they aren't flags. Not a
    # convenience: `--password` lands in argv, which is world-readable in `ps`,
    # and a hidden prompt cannot be piped — getpass falls back to echoing and
    # then reads EOF. Env vars are the only way to script this safely.
    email = email or os.environ.get("MAI_TAI_ADMIN_EMAIL") or None
    password = password or os.environ.get("MAI_TAI_ADMIN_PASSWORD") or None
    name = name or os.environ.get("MAI_TAI_ADMIN_NAME") or None
    anthropic_key = anthropic_key or os.environ.get("MAI_TAI_ANTHROPIC_KEY") or None
    vertex_project = vertex_project or os.environ.get("MAI_TAI_VERTEX_PROJECT") or None

    # Everything below reads the repo's .env or runs dev.sh out of it, so say so
    # now rather than failing three steps in. A plain `pip install ./cli` puts
    # this package in site-packages, where it cannot find the checkout on its
    # own — cwd is the only hint we get.
    if not bootstrap.repo_root_found():
        _fail(
            f"{bundle.REPO_ROOT} is not a mai-tai checkout.\n"
            "  Run `mai-tai init` from the repo root, or set MAI_TAI_REPO_ROOT."
        )

    # ---- 1. host config directory, BEFORE anything starts ----------------
    # Compose bind-mounts ${HOME}/.config/mai-tai into the backend. If it does
    # not exist when the stack first comes up, Docker creates it as root and
    # the operator can no longer write their own config into it. This has to
    # happen first or not at all.
    _step(1, total, "Host config directory")
    try:
        config_dir = bootstrap.ensure_host_config_dir()
    except OSError as e:
        _fail(f"cannot create the host config directory: {e}")
    _ok(f"{config_dir}")

    # ---- 2. stack --------------------------------------------------------
    _step(2, total, "Stack")
    if bootstrap.stack_running() and bootstrap.backend_healthy(api_url):
        _skip("already up")
    else:
        console.print("  [dim]./dev.sh local up — generating secrets, migrating...[/dim]")
        try:
            bootstrap.stack_up()
        except ProbeError as e:
            _fail(str(e))
        if not bootstrap.wait_for_backend(api_url):
            _fail(f"the stack started but {api_url}/health never answered.")
        _ok("stack up, database migrated")

    # ---- 3. agent image --------------------------------------------------
    _step(3, total, "Agent image")
    image = os.environ.get("AGENT_IMAGE", bootstrap.DEFAULT_AGENT_IMAGE)
    if bootstrap.agent_image_exists(image):
        _skip(f"{image} already built")
    elif skip_build:
        _warn(f"{image} is missing and --skip-build was passed; agents will not start")
    else:
        console.print(f"  [dim]building {image} — this takes a few minutes...[/dim]")
        try:
            bootstrap.build_agent_image(image)
        except ProbeError as e:
            _fail(str(e))
        _ok(f"built {image}")

    # ---- 4. admin account ------------------------------------------------
    _step(4, total, "Admin account")
    existing_users = bootstrap.user_count()
    raw_api_key: str | None = None

    if existing_users:
        _skip(f"{existing_users} account(s) already exist — logging in instead")
        email = email or _prompt("Email", non_interactive, "--email is required")
        password = password or _prompt(
            "Password", non_interactive, "--password is required", hide_input=True
        )
        try:
            token = bootstrap.login(email, password, api_url=api_url)
        except ProbeError as e:
            _fail(str(e))
        _ok(f"logged in as {email}")
    else:
        email = email or _prompt("Email", non_interactive, "--email is required")
        name = name or email.split("@")[0]
        password = password or _prompt(
            "Choose a password", non_interactive, "--password is required", hide_input=True
        )
        try:
            created = bootstrap.register(email, name, password, api_url=api_url)
            token = bootstrap.login(email, password, api_url=api_url)
        except ProbeError as e:
            _fail(str(e))
        # Register hands back the raw key exactly once. Catching it here is the
        # difference between init working and the user hunting for it later.
        raw_api_key = (created.get("api_key") or {}).get("key")
        _ok(f"created {email} (first account — this one is admin)")

    # ---- 5. Mai-Tai API key on the host ----------------------------------
    _step(5, total, "Agent credential (~/.config/mai-tai/config)")
    if bootstrap.host_config_has_key():
        _skip("MAI_TAI_API_KEY already present")
    else:
        if raw_api_key is None:
            # An existing deployment's provisioned key is unrecoverable by
            # design — only its hash is stored — so mint a new one.
            try:
                raw_api_key = bootstrap.create_user_api_key(token, api_url=api_url)
            except ProbeError as e:
                _fail(str(e))
        try:
            written = bootstrap.write_host_config(
                {"MAI_TAI_API_URL": api_url, "MAI_TAI_API_KEY": raw_api_key}
            )
        except OSError as e:
            _fail(f"cannot write the host config: {e}")
        _ok(f"wrote {written} (mode 0600)")
        console.print("    [dim]this is the file the backend reads when it spawns an agent[/dim]")

    # ---- 6. model credential ---------------------------------------------
    _step(6, total, "Model credential")
    if vertex_project and not bootstrap.vertex_configured():
        # .env.example ships the Vertex keys blank, so a fresh install has no
        # Vertex config even on a host whose ADC is right there. Write it.
        if not bootstrap.adc_present():
            _fail(
                f"--vertex-project was given but {bootstrap.GCLOUD_ADC_PATH} does not exist.\n"
                "  Run: gcloud auth application-default login"
            )
        written = bootstrap.configure_vertex(vertex_project, vertex_region)
        console.print(f"  [dim]wrote Vertex config to {written}, recreating backend...[/dim]")
        try:
            bootstrap.restart_backend()
        except ProbeError as e:
            _fail(str(e))
        if not bootstrap.wait_for_backend(api_url):
            _fail("the backend did not come back after being recreated for Vertex.")
        _ok(f"Vertex via {vertex_project} ({vertex_region}) — no per-user key needed")
    elif bootstrap.vertex_configured():
        _skip("host Vertex ADC is configured — agents need no per-user key")
    elif bootstrap.has_anthropic_key(token, api_url=api_url):
        _skip("this account already has an Anthropic key stored")
    else:
        if bootstrap.adc_present():
            # The most annoying possible outcome: a host that could use Vertex
            # for free being asked to go find a key. Say so before asking.
            _warn(
                "gcloud ADC is on this host but .env has no Vertex config — "
                "re-run with --vertex-project <gcp-project> to use it instead"
            )
        key = anthropic_key or _prompt(
            "Anthropic API key (sk-ant-... or a Pro/Max OAuth token)",
            non_interactive,
            "--anthropic-key is required (or pass --vertex-project)",
            hide_input=True,
        )
        try:
            bootstrap.set_anthropic_key(token, key, api_url=api_url)
        except ProbeError as e:
            _fail(str(e))
        _ok("stored, encrypted at rest")

    # ---- 7. workspace + agent --------------------------------------------
    _step(7, total, f"Agent workspace {workspace_name!r}")
    try:
        workspace = bootstrap.find_workspace(token, workspace_name, api_url=api_url)
        if workspace:
            _skip(f"already exists ({str(workspace['id'])[:8]})")
        else:
            workspace = bootstrap.create_agent_workspace(
                token,
                name=workspace_name,
                template=template,
                model=model,
                api_url=api_url,
            )
            _ok(f"created ({str(workspace['id'])[:8]}, template={template})")
    except ProbeError as e:
        _fail(str(e))

    workspace_id = str(workspace["id"])
    if skip_agent:
        _skip("--skip-agent: not starting the container")
    elif bootstrap.agent_container_running(workspace_id):
        _skip("agent container already running")
    else:
        try:
            bootstrap.start_agent(token, workspace_id, api_url=api_url)
        except ProbeError as e:
            _fail(str(e))
        console.print("  [dim]waiting for the agent to check in...[/dim]")
        # A running container is not a working agent. Wait for the heartbeat.
        age = bootstrap.wait_for_checkin(workspace_id)
        if age is None:
            _warn("the container started but never checked in")
            console.print(
                f"    [dim]mai-tai describe {workspace_id[:8]}   "
                f"docker logs {probes.agent_container_name(workspace_id)}[/dim]"
            )
        else:
            _ok(f"agent checked in ({_age(age)} ago)")

    frontend = api_url.replace(":8000", ":3000")
    console.print(f"\n[green]Ready.[/green] Open [bold]{frontend}[/bold], sign in as {email}, "
                  f"and say hi to {workspace_name}.")


def _prompt(label: str, non_interactive: bool, failure: str, hide_input: bool = False) -> str:
    """Ask, unless we were told not to. Missing stdin is a failure, not a hang."""
    if non_interactive:
        _fail(failure)
    try:
        value = typer.prompt(label, hide_input=hide_input)
    except (EOFError, typer.Abort):
        _fail(f"{failure} (no input available)")
    if not value:
        _fail(failure)
    return value


@bots_app.command("list")
def bots_list() -> None:
    """Every bot: host tmux sessions (configured or not) and agent containers."""
    workspaces = probes.workspaces()
    runners = _runners(workspaces)
    by_id = {ws.id: ws for ws in workspaces}
    configured = probes.boot_repos()
    running_repos = {session.repo for session in probes.sessions()}

    table = Table(title="Bots", title_justify="left", header_style="bold")
    table.add_column("Bot")
    table.add_column("Kind")
    table.add_column("Workspace")
    table.add_column("Boot", justify="center")
    table.add_column("Up", justify="center")
    table.add_column("Heartbeat", justify="right")

    def row(label: str, kind: str, ws: probes.Workspace | None, boot: str, up: bool) -> None:
        table.add_row(
            label,
            kind,
            ws.name if ws else "[red]unmapped[/red]",
            boot,
            "[green]yes[/green]" if up else "[red]no[/red]",
            _age(ws.heartbeat_secs) if ws else "—",
        )

    for session in probes.sessions():
        ws_id = probes.workspace_id_for_repo_dir(session.repo_dir)
        boot = "[green]✓[/green]" if session.repo in configured else "[dim]—[/dim]"
        row(session.repo, "tmux", by_id.get(ws_id or ""), boot, session.alive)

    # Configured but not running is the interesting case: it means a reboot or a
    # crash lost a bot that is supposed to be up.
    for repo in configured:
        if repo not in running_repos:
            ws_id = probes.repo_workspace_id(repo)
            row(repo, "tmux", by_id.get(ws_id or ""), "[green]✓[/green]", False)

    for ws in workspaces:
        runner = runners[ws.id]
        if runner.kind == "container":
            row(runner.label, "container", ws, "[dim]n/a[/dim]", runner.up)

    console.print(table)
    if configured:
        console.print(
            f"[dim]Boot ✓ = listed in {probes.BOOT_REPOS_CONF}, started at @reboot.[/dim]"
        )


@bots_app.command("start")
def bots_start(
    repo: str = typer.Argument(None, help="Repo name under the repos root."),
    all_configured: bool = typer.Option(False, "--all", help="Start every repo in boot-repos.conf."),
) -> None:
    """Start a host bot: a tmux window running the supervisor for that repo.

    Agent containers are started through the API, not here — this is the tmux
    side only.
    """
    if all_configured == bool(repo):
        _fail("give a repo name or --all, not both")

    repos = probes.boot_repos() if all_configured else [repo]
    if not repos:
        _fail(f"no repos configured in {probes.BOOT_REPOS_CONF}")

    started = skipped = failed = 0
    for name in repos:
        try:
            window = probes.tmux_start(name, probes.REPOS_ROOT / name)
        except ProbeError as e:
            # Already-running is a skip, not a failure — `bots start --all` has
            # to stay idempotent so it can be used as "make sure they're all up"
            # without a green run looking like a broken one.
            if "already running" in str(e):
                console.print(f"  [dim]skip[/dim]  {e}")
                skipped += 1
            else:
                console.print(f"  [red]fail[/red]  {e}")
                failed += 1
            continue
        console.print(f"  [green]start[/green] {name} → window {window!r}")
        started += 1

    console.print(f"\n{started} started, {skipped} already up, {failed} failed")
    console.print(f"[dim]Attach with: tmux attach -t {probes.TMUX_SESSION}[/dim]")
    if failed:
        raise typer.Exit(code=1)


@bots_app.command("stop")
def bots_stop(
    repo: str = typer.Argument(..., help="Repo name whose supervisor window to kill."),
) -> None:
    """Stop a host bot for good.

    Not the same as `bots restart`: this kills the supervisor window, so nothing
    brings the bot back until you start it again or the host reboots.
    """
    try:
        window = probes.tmux_stop(repo)
    except ProbeError as e:
        _fail(str(e))
    console.print(f"[green]✓[/green] killed window {window!r} — {repo} will stay down")


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


@contextlib.contextmanager
def _staging() -> Iterator[Path]:
    """A private scratch directory that always gets cleaned up.

    Both halves of this feature spill a full database dump — plus, on export,
    the .env — onto disk. Leaving that in /tmp after a crash is a credential
    leak, so cleanup is a `finally`, not a courtesy.
    """
    stage = Path(tempfile.mkdtemp(prefix="mai-tai-bundle-"))
    stage.chmod(0o700)
    try:
        yield stage
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def _print_counts(counts: dict) -> None:
    if not counts:
        return
    width = max(len(key) for key in counts)
    for key, value in counts.items():
        console.print(f"  [dim]{key.ljust(width)}[/dim]  {value}")


def _human_size(path: Path) -> str:
    size = float(path.stat().st_size)
    for unit in ("B", "K", "M", "G"):
        if size < 1024 or unit == "G":
            return f"{size:.0f}{unit}"
        size /= 1024
    return f"{size:.0f}G"


@config_app.command("export")
def config_export(
    out: str = typer.Argument(None, help="Where to write the bundle."),
    scrub: bool = typer.Option(False, "--scrub", help="Strip credentials from users.settings."),
    with_env: bool = typer.Option(False, "--with-env", help="Also bundle the repo's .env."),
) -> None:
    """Write a portable copy of this deployment: users, workspaces, agents, history."""
    target = Path(out) if out else Path.cwd() / bundle.default_bundle_name()
    target = target.expanduser().resolve()

    console.print(
        f"Dumping {'scrubbed ' if scrub else ''}database from "
        f"[bold]{probes.PG_CONTAINER}[/bold]..."
    )
    with _staging() as stage:
        manifest, notes, leaks = bundle.export_bundle(
            target, stage=stage, scrub=scrub, with_env=with_env
        )

    for note in notes:
        console.print(f"[yellow]![/yellow] {note}")
    console.print(f"\n[green]✓[/green] wrote {target} ({_human_size(target)}, mode 0600)\n")
    _print_counts(manifest.counts)
    console.print()

    if scrub:
        console.print("Scrubbed bundle — users.settings carries no credentials.")
        console.print("On the target you'll need to:")
        console.print("  1. Put .env in place       [dim]mai-tai config check-env[/dim]")
        console.print("  2. Copy ~/.config/mai-tai/config so existing mt_ keys authenticate")
        console.print("  3. Re-enter Anthropic / GitHub / LLM keys in Settings > AI")
        _warn_about_leaks(leaks, scrubbed=True)
        return

    env_note = " and your .env" if manifest.includes_env else ""
    err_console.print("[red]TREAT THIS FILE AS A SECRET.[/red]")
    err_console.print(
        f"It carries the credentials from users.settings (Anthropic/OpenAI keys, GitHub\n"
        f"token, LLM keys){env_note}, plus full message history. Those settings are\n"
        "Fernet-encrypted at rest, but the key derives from SECRET_KEY unless\n"
        "ENCRYPTION_KEY is set — a bundle plus a leaked .env is plaintext. Don't commit\n"
        "it, don't put it in cloud storage, and delete it once the move is done."
    )
    _warn_about_leaks(leaks, scrubbed=False)
    console.print("\n[dim]Use --scrub to drop the credentials held in users.settings.[/dim]")


def _warn_about_leaks(leaks: dict[str, int], *, scrubbed: bool) -> None:
    """Report credential-shaped strings left in the dump.

    --scrub only strips users.settings. Message history is not scrubbed and
    never can be safely — agents paste keys into chat and operators paste them
    back — so a scrubbed bundle is *not* automatically safe to hand around.
    Saying so only when we can point at something keeps the warning meaningful.
    """
    if not scrubbed and not leaks:
        return
    console.print()
    if not leaks:
        err_console.print(
            "[yellow]![/yellow] Note: --scrub does not touch message history. No "
            "credential-shaped strings were found in it, but that is a pattern scan, "
            "not a proof."
        )
        return
    err_console.print("[red]![/red] Credential-shaped strings remain in the message history:")
    for label, count in sorted(leaks.items(), key=lambda item: -item[1]):
        err_console.print(f"    [red]{count:>4}[/red]  {label}")
    err_console.print(
        "  These are in chat content, which no scrub touches. Treat this bundle as secret "
        "and rotate anything that actually leaked."
    )


@config_app.command("inspect")
def config_inspect(
    bundle_path: str = typer.Argument(..., metavar="BUNDLE", help="Bundle to look inside."),
) -> None:
    """Show what a bundle contains without restoring any of it."""
    path = Path(bundle_path).expanduser()
    with _staging() as stage:
        try:
            manifest, notes = bundle.unpack(path, stage)
        except ProbeError as e:
            _fail(str(e))
        dump = stage / "database.sql"
        dump_size = _human_size(dump) if dump.exists() else "[red]missing[/red]"

    console.print(f"\n[bold]{path}[/bold]\n")
    _kv(
        [
            ("format", f"v{manifest.bundle_version}"),
            ("exported", manifest.exported_at or "—"),
            ("source host", manifest.source_host or "—"),
            ("schema", manifest.alembic_revision),
            ("dump size", dump_size),
            (
                "secrets",
                "[red]yes — treat as credential material[/red]"
                if manifest.contains_secrets
                else "[green]scrubbed[/green]",
            ),
            ("includes .env", "yes" if manifest.includes_env else "no"),
            ("crypto key", manifest.crypto_fingerprint),
        ]
    )
    console.print("\n[bold]Contents[/bold]")
    _print_counts(manifest.counts)
    for note in notes:
        console.print(f"[yellow]![/yellow] {note}")
    console.print()


@config_app.command("import")
def config_import(
    bundle_path: str = typer.Argument(..., metavar="BUNDLE", help="Bundle to restore."),
    disable_schedules: bool = typer.Option(
        False,
        "--disable-schedules",
        help="Turn every scheduled task off after restoring (recommended for a clone).",
    ),
) -> None:
    """Replace this deployment's database with a bundle's.

    Destructive and interactive by design: there is no --yes. A bundle restore
    wipes every workspace on this host, and the one place you never want that
    to be scriptable is a machine where somebody typed the wrong path.
    """
    path = Path(bundle_path).expanduser()
    with _staging() as stage:
        try:
            manifest, notes = bundle.unpack(path, stage)
            bundle.check_version(manifest)
            bundle.require_pg()
        except ProbeError as e:
            _fail(str(e))

        for note in notes:
            console.print(f"[yellow]![/yellow] {note}")

        console.print(f"\n[bold]{path}[/bold]  [dim]v{manifest.bundle_version}, "
                      f"from {manifest.source_host or 'unknown'} at "
                      f"{manifest.exported_at or 'unknown'}[/dim]\n")
        _print_counts(manifest.counts)
        console.print()

        warning = bundle.fingerprint_warning(manifest)
        if warning:
            err_console.print(f"[yellow]![/yellow] {warning}\n")

        existing = probes.psql("select count(*) from workspaces")
        held = existing[0][0] if existing else "?"
        err_console.print(
            f"[red]This REPLACES the database in {probes.PG_CONTAINER} "
            f"({probes.PG_DB}).[/red]"
        )
        err_console.print(f"[red]It currently holds {held} workspace(s). They will be dropped.[/red]")

        # A restored clone is live: schedules arrive enabled, and the next tick
        # wakes agents that then do real work — send messages, hit the LAN — from
        # a host that was only ever meant to be a copy.
        incoming = manifest.enabled_schedules
        if incoming and not disable_schedules:
            err_console.print(
                f"[yellow]![/yellow] The bundle carries {incoming} ENABLED schedule(s). This host "
                "will start firing them as soon as the backend comes up. Re-run with "
                "--disable-schedules if this is a clone."
            )
        console.print()

        # Fail closed: no stdin (cron, CI) must abort, not fall through to a wipe.
        try:
            confirm = typer.prompt("Type 'replace' to continue", default="", show_default=False)
        except (EOFError, typer.Abort):
            console.print("\nNo input available. Aborted — nothing changed.")
            raise typer.Exit(code=1) from None
        if confirm != "replace":
            console.print("Aborted. Nothing changed.")
            raise typer.Exit(code=0)

        console.print("Restoring...")
        try:
            bundle.restore(stage)
        except ProbeError as e:
            err_console.print(f"[red]✗[/red] {e}")
            err_console.print("[red]The database may be in a partial state.[/red]")
            raise typer.Exit(code=1) from None
        console.print("[green]✓[/green] database restored")

        if disable_schedules:
            turned_off = bundle.disable_all_schedules()
            console.print(f"[green]✓[/green] disabled {turned_off} schedule(s)")

        imported_env = bundle.place_imported_env(stage)

    if imported_env:
        console.print(f"\nBundle included a .env — written to {imported_env} (mode 0600).")
        console.print(f"[dim]Review it, then: mv {imported_env} {bundle.env_path()}[/dim]")

    console.print("\n[green]Import complete.[/green] Remaining steps:")
    console.print("  1. Ensure .env is in place   [dim]mai-tai config check-env[/dim]")
    console.print("  2. Restart the stack         [dim]./dev.sh local up[/dim]")

    # Only nag about re-entering credentials when the bundle actually dropped
    # them; a full bundle carries them and the target is ready to go.
    if not manifest.contains_secrets:
        console.print("  3. Re-enter credentials in Settings > AI (this bundle was scrubbed)")
        console.print("\n[dim]Users needing credentials re-entered:[/dim]")
        for row in probes.psql("select email from users order by email"):
            console.print(f"  [dim]- {row[0]}[/dim]")
    else:
        err_console.print(
            f"\n[yellow]![/yellow] Delete {path} now that the move is done; it holds live secrets."
        )


@config_app.command("check-env")
def config_check_env() -> None:
    """Report which .env keys this host is missing. Exits 1 if a required one is."""
    try:
        results = bundle.check_env()
    except ProbeError as e:
        _fail(str(e))

    console.print(f"Checking {bundle.env_path()}\n")
    missing = 0
    for required in (True, False):
        console.print(f"  [bold]{'Required' if required else 'Optional'}:[/bold]")
        for check in (c for c in results if c.required == required):
            if check.present:
                console.print(f"    [green]ok[/green]       {check.key}")
            elif required:
                console.print(f"    [red]MISSING[/red]  {check.key}")
                missing += 1
            else:
                console.print(f"    [yellow]unset[/yellow]    {check.key}")
        console.print()

    if missing:
        err_console.print(
            f"[red]{missing} required key(s) missing[/red] — the stack will not come up cleanly."
        )
        raise typer.Exit(code=1)
    console.print("[green]All required keys present.[/green]")


def main() -> None:
    try:
        app()
    except ProbeError as e:
        err_console.print(f"[red]error:[/red] {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
