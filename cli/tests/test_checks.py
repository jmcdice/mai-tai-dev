"""Unit tests for the doctor checks and the host probes' parsing.

None of these touch docker or postgres — the probe boundary is monkeypatched so
the tests describe *what the checks conclude*, which is the part that has been
wrong in production.
"""

from __future__ import annotations

import shlex

import pytest

from mai_tai_admin import cli, probes


def make_ws(**kwargs) -> probes.Workspace:
    defaults = dict(
        id="cd1b8708-5d17-4ef4-b089-84db652a0489",
        name="DevOps / SRE",
        workspace_type="agent",
        archived=False,
        heartbeat_secs=3,
        schedules_total=2,
        schedules_enabled=2,
        messages=7,
    )
    defaults.update(kwargs)
    return probes.Workspace(**defaults)


def runner(up: bool = True, kind: str = "container", label: str = "maitai-agent-cd1b8708"):
    return cli.Runner(kind=kind, label=label, up=up)


class TestWorkspaceState:
    @pytest.mark.parametrize(
        "secs,expected",
        [(0, "connected"), (419, "connected"), (420, "idle"), (599, "idle"), (600, "offline")],
    )
    def test_thresholds_match_the_api(self, secs, expected):
        assert make_ws(heartbeat_secs=secs).state == expected

    def test_never_seen(self):
        assert make_ws(heartbeat_secs=None).state == "never"


class TestBotChecks:
    def test_healthy_bot_passes(self):
        ws = make_ws(heartbeat_secs=3)
        checks = cli._check_bots([ws], {ws.id: runner()})
        assert [c.level for c in checks] == ["ok"]

    def test_alive_but_silent_is_a_failure(self):
        """The Rando case: container up, heartbeat 15h stale.

        `ps` and `docker ps` both report healthy here, which is exactly why the
        check has to key off the heartbeat instead.
        """
        ws = make_ws(name="Rando", heartbeat_secs=54_000)
        checks = cli._check_bots([ws], {ws.id: runner(up=True)})

        assert len(checks) == 1
        assert checks[0].level == "fail"
        assert "alive but not talking" in checks[0].title
        assert "MCP client drop" in checks[0].detail
        assert "bots restart" in checks[0].detail

    def test_runner_down_is_a_failure(self):
        ws = make_ws(heartbeat_secs=54_000)
        checks = cli._check_bots([ws], {ws.id: runner(up=False)})
        assert checks[0].level == "fail"
        assert "runner down" in checks[0].title

    def test_idle_is_only_a_warning(self):
        ws = make_ws(heartbeat_secs=500)
        checks = cli._check_bots([ws], {ws.id: runner()})
        assert checks[0].level == "warn"

    def test_chat_workspace_with_no_runner_is_not_a_fault(self):
        ws = make_ws(workspace_type="chat", heartbeat_secs=None)
        checks = cli._check_bots([ws], {ws.id: runner(kind="none", up=False, label="—")})
        assert checks == []


class TestScheduleChecks:
    def _schedule(self, **kwargs) -> probes.Schedule:
        defaults = dict(
            workspace="DevOps / SRE",
            name="Nightly posture sweep",
            cron_expression="0 6 * * *",
            timezone="America/Denver",
            overdue_secs=-3600,
            last_status="ok",
        )
        defaults.update(kwargs)
        return probes.Schedule(**defaults)

    def test_future_run_is_fine(self, monkeypatch):
        monkeypatch.setattr(probes, "enabled_schedules", lambda: [self._schedule()])
        assert [c.level for c in cli._check_schedules()] == ["ok"]

    def test_overdue_means_the_scheduler_stalled(self, monkeypatch):
        monkeypatch.setattr(
            probes, "enabled_schedules", lambda: [self._schedule(overdue_secs=7200)]
        )
        checks = cli._check_schedules()
        assert checks[0].level == "fail"
        assert "not advancing" in checks[0].title

    def test_a_minute_of_tick_latency_is_tolerated(self, monkeypatch):
        monkeypatch.setattr(probes, "enabled_schedules", lambda: [self._schedule(overdue_secs=30)])
        assert [c.level for c in cli._check_schedules()] == ["ok"]

    def test_errored_last_run_warns(self, monkeypatch):
        monkeypatch.setattr(
            probes, "enabled_schedules", lambda: [self._schedule(last_status="error")]
        )
        assert [c.level for c in cli._check_schedules()] == ["warn"]


class TestCoreChecks:
    def test_missing_container_fails(self):
        checks = cli._check_core({})
        assert all(c.level == "fail" for c in checks)
        assert len(checks) == len(probes.CORE_CONTAINERS)

    def test_unhealthy_warns_but_running_passes(self):
        containers = {
            name: probes.Container(name, "running", "Up 6 days (healthy)")
            for name in probes.CORE_CONTAINERS
        }
        containers["maitai-backend"] = probes.Container(
            "maitai-backend", "running", "Up 2 minutes (unhealthy)"
        )
        levels = {c.title: c.level for c in cli._check_core(containers)}
        assert levels["maitai-backend unhealthy"] == "warn"
        assert levels["maitai-postgres"] == "ok"


class TestOrphanChecks:
    def test_agent_container_without_a_workspace_warns(self):
        ws = make_ws()
        containers = {
            "maitai-agent-deadbeef": probes.Container(
                "maitai-agent-deadbeef", "running", "Up 1 hour"
            ),
            probes.agent_container_name(ws.id): probes.Container(
                probes.agent_container_name(ws.id), "running", "Up 1 hour"
            ),
        }
        checks = cli._check_orphans([ws], containers)
        assert checks[0].level == "warn"
        assert "maitai-agent-deadbeef" in checks[0].detail

    def test_stopped_orphans_are_ignored(self):
        containers = {
            "maitai-agent-deadbeef": probes.Container(
                "maitai-agent-deadbeef", "exited", "Exited (0) 2 days ago"
            )
        }
        assert cli._check_orphans([], containers) == []


class TestSessionParsing:
    PS_ROWS = [
        (100, 1, "tmux new-session -d -s mai-tai -n rando bash -lc 'mai-tai-supervisor.sh /r/rando'"),
        (200, 100, "bash /home/joey/repos/mai-tai-dev/scripts/mai-tai-supervisor.sh /repos/rando"),
        (300, 200, "timeout -k 30 --foreground 24h claude --model claude-opus-5 /mai-tai resume"),
        (400, 300, "claude --model claude-opus-5 /mai-tai resume"),
        (500, 400, "/usr/bin/python3 /home/joey/.local/bin/mai-tai-mcp"),
    ]

    def test_finds_the_pid_to_kill(self, monkeypatch):
        monkeypatch.setattr(probes, "_ps_table", lambda: self.PS_ROWS)
        found = probes.sessions()

        assert len(found) == 1, "the tmux new-session parent must not count as a supervisor"
        session = found[0]
        assert session.repo == "rando"
        assert session.supervisor_pid == 200
        assert session.timeout_pid == 300  # kill this one, not claude
        assert session.claude_pid == 400
        assert session.alive

    def test_supervisor_with_no_claude_is_not_alive(self, monkeypatch):
        monkeypatch.setattr(probes, "_ps_table", lambda: [self.PS_ROWS[1]])
        session = probes.sessions()[0]
        assert not session.alive
        assert session.timeout_pid is None

    def test_claude_without_a_timeout_wrapper(self, monkeypatch):
        """ROTATE_AFTER=0 runs claude directly under the supervisor."""
        rows = [
            self.PS_ROWS[1],
            (400, 200, "claude --model claude-opus-5 /mai-tai resume"),
        ]
        monkeypatch.setattr(probes, "_ps_table", lambda: rows)
        session = probes.sessions()[0]
        assert session.timeout_pid is None
        assert session.claude_pid == 400


class TestBootRepos:
    def test_comments_and_trailing_slashes(self, tmp_path, monkeypatch):
        conf = tmp_path / "boot-repos.conf"
        conf.write_text(
            "# Repos to auto-start\n"
            "folio/\n"
            "\n"
            "rando\n"
            "# surf-trip/   # archived 2026-07-15\n"
            "halo-craft/  \n"
        )
        monkeypatch.setattr(probes, "BOOT_REPOS_CONF", conf)
        assert probes.boot_repos() == ["folio", "rando", "halo-craft"]

    def test_missing_file_is_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(probes, "BOOT_REPOS_CONF", tmp_path / "nope.conf")
        assert probes.boot_repos() == []


class TestWorkspaceIdLookup:
    def test_reads_env_mai_tai(self, tmp_path):
        (tmp_path / ".env.mai-tai").write_text(
            "# generated\nMAI_TAI_WORKSPACE_ID=0bb9085a-df90-4cf7-af87-7f0cc368f438\n"
        )
        assert probes.workspace_id_for_repo_dir(tmp_path) == "0bb9085a-df90-4cf7-af87-7f0cc368f438"

    def test_quoted_value(self, tmp_path):
        (tmp_path / ".env.mai-tai").write_text('MAI_TAI_WORKSPACE_ID="abc-123"\n')
        assert probes.workspace_id_for_repo_dir(tmp_path) == "abc-123"

    def test_absent_file(self, tmp_path):
        assert probes.workspace_id_for_repo_dir(tmp_path) is None


class TestResolveWorkspace:
    ALL = [
        make_ws(id="cd1b8708-aaaa", name="DevOps / SRE"),
        make_ws(id="0bb9085a-bbbb", name="Rando"),
        make_ws(id="6a756b41-cccc", name="JoeyTV"),
    ]

    @pytest.fixture(autouse=True)
    def _patch(self, monkeypatch):
        monkeypatch.setattr(probes, "workspaces", lambda include_archived=False: self.ALL)

    @pytest.mark.parametrize("needle", ["Rando", "rando", "0bb9085a", "0bb9085a-bbbb"])
    def test_matches(self, needle):
        assert probes.resolve_workspace(needle).name == "Rando"

    def test_substring(self):
        assert probes.resolve_workspace("devops").name == "DevOps / SRE"

    def test_unknown(self):
        with pytest.raises(probes.ProbeError, match="no workspace matches"):
            probes.resolve_workspace("nope")

    def test_ambiguous_names_the_candidates(self, monkeypatch):
        monkeypatch.setattr(
            probes,
            "workspaces",
            lambda include_archived=False: [
                make_ws(id="a1", name="Bot One"),
                make_ws(id="a2", name="Bot Two"),
            ],
        )
        with pytest.raises(probes.ProbeError, match="ambiguous: Bot One, Bot Two"):
            probes.resolve_workspace("bot")


class TestMessages:
    ROW = [
        "9f1c",
        "2026-08-07 21:14:03",
        "2026-08-07 21:14:03.418922",
        "human",
        "chat",
        "line one\nline two | with a pipe",
    ]

    def test_multiline_bodies_survive(self, monkeypatch):
        monkeypatch.setattr(probes, "psql", lambda sql: [self.ROW])
        message = probes.messages("ws-1")[0]
        assert message.content == "line one\nline two | with a pipe"
        assert message.created_at == "2026-08-07 21:14:03"

    def test_cursor_keeps_microseconds(self, monkeypatch):
        """Second-precision paging drops same-second messages; the cursor can't."""
        monkeypatch.setattr(probes, "psql", lambda sql: [self.ROW])
        assert probes.messages("ws-1")[0].cursor == "2026-08-07 21:14:03.418922"

    def test_since_filters_on_the_cursor(self, monkeypatch):
        captured = []

        def fake_psql(sql):
            captured.append(sql)
            return []

        monkeypatch.setattr(probes, "psql", fake_psql)
        probes.messages("ws-1", limit=100, since="2026-08-07 21:14:03.418922")
        assert "m.created_at > '2026-08-07 21:14:03.418922'" in captured[0]
        assert "limit 100" in captured[0]

    def test_short_rows_are_skipped(self, monkeypatch):
        monkeypatch.setattr(probes, "psql", lambda sql: [self.ROW[:4]])
        assert probes.messages("ws-1") == []


class TestWorkspaceKind:
    def test_chat(self):
        assert make_ws(workspace_type="chat").kind == "chat"

    def test_agent_shows_its_template(self):
        assert make_ws(workspace_type="agent", template="monitor").kind == "agent/monitor"

    def test_agent_without_a_template(self):
        assert make_ws(workspace_type="agent", template=None).kind == "agent"


class TestJsonColumns:
    @pytest.mark.parametrize("raw", ["null", "", "[1,2]", '"a string"', "not json"])
    def test_non_objects_become_empty(self, raw):
        assert probes._json_obj(raw) == {}

    def test_object(self):
        assert probes._json_obj('{"runtime": "claude-code"}') == {"runtime": "claude-code"}

    def test_detail_tolerates_a_null_agent_config(self, monkeypatch):
        row = ["2026-06-24 05:32", "jmcdice@gmail.com", "", "null", '{"dude_mode": true}']
        monkeypatch.setattr(probes, "psql", lambda sql: [row])
        info = probes.detail("ws-1")
        assert info.agent_config == {}
        assert info.settings == {"dude_mode": True}

    def test_detail_on_a_vanished_workspace(self, monkeypatch):
        monkeypatch.setattr(probes, "psql", lambda sql: [])
        with pytest.raises(probes.ProbeError, match="disappeared"):
            probes.detail("ws-1")


class TestAuthKey:
    ROW = ["Default Agent Key", "read,write", "3", "f", "f", "9"]

    def test_reports_a_user_scoped_shared_key(self, monkeypatch):
        """The live deployment has one user-scoped key serving every workspace.

        Reading api_keys.workspace_id instead would report "no keys" for a
        workspace that is authenticating right now.
        """
        monkeypatch.setattr(probes, "psql", lambda sql: [self.ROW])
        key = probes.auth_key("ws-1")
        assert key.workspace_scoped is False
        assert key.shared_with == 9
        assert key.last_used_secs == 3

    def test_never_authenticated(self, monkeypatch):
        monkeypatch.setattr(probes, "psql", lambda sql: [])
        assert probes.auth_key("ws-1") is None

    def test_sole_user_is_not_shared(self, monkeypatch):
        monkeypatch.setattr(probes, "psql", lambda sql: [[*self.ROW[:5], "0"]])
        assert probes.auth_key("ws-1").shared_with == 0

    def test_count_never_goes_negative(self, monkeypatch):
        # `count(*) - 1` is -1 if the join row vanishes between the subquery
        # and the outer query.
        monkeypatch.setattr(probes, "psql", lambda sql: [[*self.ROW[:5], "-1"]])
        assert probes.auth_key("ws-1").shared_with == 0


class TestSchedulesForWorkspace:
    ROWS = [
        ["DevOps / SRE", "Nightly sweep", "0 6 * * *", "America/Denver", "-3600", "ok", "t", "t", "82800"],
        ["DevOps / SRE", "Old loop", "0 * * * *", "UTC", "", "", "f", "f", ""],
    ]

    def test_includes_disabled(self, monkeypatch):
        monkeypatch.setattr(probes, "psql", lambda sql: self.ROWS)
        found = probes.schedules_for("ws-1")
        assert [s.enabled for s in found] == [True, False]
        assert found[1].wake_agent is False
        assert found[1].last_run_secs is None

    def test_next_in_inverts_overdue(self, monkeypatch):
        monkeypatch.setattr(probes, "psql", lambda sql: self.ROWS)
        assert probes.schedules_for("ws-1")[0].next_in_secs == 3600

    def test_scoped_to_the_workspace(self, monkeypatch):
        captured = []

        def fake_psql(sql):
            captured.append(sql)
            return []

        monkeypatch.setattr(probes, "psql", fake_psql)
        probes.schedules_for("ws-1")
        assert "s.workspace_id = 'ws-1'" in captured[0]
        probes.enabled_schedules()
        assert "where s.enabled" in captured[1]


class TestMessageStats:
    def test_empty_workspace(self, monkeypatch):
        monkeypatch.setattr(probes, "psql", lambda sql: [])
        stats = probes.message_stats("ws-1")
        assert stats.total == 0
        assert stats.busiest_day == ""

    def test_populated(self, monkeypatch):
        def fake_psql(sql):
            if "group by" in sql:
                return [["2026-08-06", "39"]]
            return [["112", "29", "83", "2026-06-24 05:33", "2026-08-06 23:49", "0"]]

        monkeypatch.setattr(probes, "psql", fake_psql)
        stats = probes.message_stats("ws-1")
        assert (stats.total, stats.from_human, stats.from_agent) == (112, 29, 83)
        assert (stats.busiest_day, stats.busiest_count) == ("2026-08-06", 39)


class TestTurnHealth:
    def test_parses_counts_per_workspace(self, monkeypatch):
        monkeypatch.setattr(
            probes, "psql", lambda sql: [["ws-1", "4", "0", "2026-08-10 23:41"], ["ws-2", "0", "9", ""]]
        )
        health = probes.turn_health()
        assert (health["ws-1"].failed, health["ws-1"].succeeded) == (4, 0)
        assert health["ws-1"].last_failure_at == "2026-08-10 23:41"
        assert (health["ws-2"].failed, health["ws-2"].succeeded) == (0, 9)

    def test_no_agent_messages_at_all(self, monkeypatch):
        monkeypatch.setattr(probes, "psql", lambda sql: [])
        assert probes.turn_health() == {}

    def test_query_matches_the_driver_markers_in_ascii(self, monkeypatch):
        """The literals carry emoji; the SQL must not."""
        seen = {}
        monkeypatch.setattr(probes, "psql", lambda sql: seen.setdefault("sql", sql) and [])
        probes.turn_health()
        sql = seen["sql"]
        assert "I hit an error processing that message" in sql
        assert "Send me a message and I" in sql
        assert sql.isascii()

    def test_window_is_configurable_and_not_injectable(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(probes, "psql", lambda sql: seen.setdefault("sql", sql) and [])
        probes.turn_health(hours=72)
        assert "interval '72 hours'" in seen["sql"]


class TestTurnChecks:
    """`doctor`'s blind spot: connected, checking in, answering nothing."""

    def _health(self, monkeypatch, **rows):
        monkeypatch.setattr(
            probes,
            "turn_health",
            lambda *a, **kw: {
                ws: probes.TurnHealth(ws, f, s, "2026-08-10 23:41") for ws, (f, s) in rows.items()
            },
        )

    def test_every_turn_failing_is_a_failure(self, monkeypatch):
        ws = make_ws(name="Supervisor", heartbeat_secs=2)
        self._health(monkeypatch, **{ws.id: (5, 0)})

        checks = cli._check_turns([ws], {ws.id: runner()})

        assert len(checks) == 1
        assert checks[0].level == "fail"
        assert "connected but not answering" in checks[0].title
        # The one-line diagnosis, because nothing else on the box names the cause.
        assert "claude -p hi" in checks[0].detail

    def test_a_healthy_agent_emits_nothing(self, monkeypatch):
        ws = make_ws(heartbeat_secs=2)
        self._health(monkeypatch, **{ws.id: (0, 12)})
        assert cli._check_turns([ws], {ws.id: runner()}) == []

    def test_some_failures_among_successes_is_only_a_warning(self, monkeypatch):
        ws = make_ws(heartbeat_secs=2)
        self._health(monkeypatch, **{ws.id: (2, 6)})

        checks = cli._check_turns([ws], {ws.id: runner()})

        assert checks[0].level == "warn"
        assert "2 of 8" in checks[0].detail

    def test_workspace_with_no_runner_is_skipped(self, monkeypatch):
        ws = make_ws(workspace_type="chat", heartbeat_secs=None)
        self._health(monkeypatch, **{ws.id: (3, 0)})
        assert cli._check_turns([ws], {ws.id: runner(kind="none", up=False)}) == []

    def test_silent_workspace_is_not_reported(self, monkeypatch):
        """No agent messages in the window is not evidence of a broken agent."""
        ws = make_ws(heartbeat_secs=2)
        self._health(monkeypatch)
        assert cli._check_turns([ws], {ws.id: runner()}) == []

    def test_a_healthy_bot_check_does_not_hide_it(self, monkeypatch):
        """The exact deception: heartbeat fresh, so _check_bots says ok."""
        ws = make_ws(name="Supervisor", heartbeat_secs=2)
        self._health(monkeypatch, **{ws.id: (5, 0)})

        assert cli._check_bots([ws], {ws.id: runner()})[0].level == "ok"
        assert cli._check_turns([ws], {ws.id: runner()})[0].level == "fail"


class TestContainers:
    def test_image_is_parsed(self, monkeypatch):
        proc = type("P", (), {"returncode": 0, "stdout": "a\trunning\tUp 3 hours\tmai-tai-agent:latest\n", "stderr": ""})
        monkeypatch.setattr(probes, "_run", lambda cmd, **kw: proc)
        found = probes.containers()
        assert found["a"].image == "mai-tai-agent:latest"
        assert found["a"].running


class TestDescribeFormatting:
    @pytest.mark.parametrize(
        "secs,expected",
        [(None, "—"), (0, "in 0s"), (3600, "in 1h00m"), (-90, "1m overdue")],
    )
    def test_countdown(self, secs, expected):
        assert expected in cli._countdown(secs)

    def test_scalar_types(self):
        assert cli._scalar(None) == "[dim]—[/dim]"
        assert cli._scalar(True) == "true"
        assert cli._scalar(False) == "false"
        assert cli._scalar(3) == "3"

    def test_scalar_collapses_and_clips(self):
        out = cli._scalar("a paragraph\nwith  newlines " + "x" * 200, width=40)
        assert "\n" not in out
        assert len(out) == 40
        assert out.endswith("...")


class TestWindowNames:
    @pytest.mark.parametrize(
        "repo,expected",
        [
            ("rando", "rando"),
            ("test.bot-1", "test-bot-1"),  # tmux rejects '.' in window names
            ("a:b", "a-b"),  # and ':' is its target separator
            ("weird//name", "weird-name"),  # repeats collapse
            ("trailing.", "trailing"),
        ],
    )
    def test_sanitize_matches_the_shell_version(self, repo, expected):
        assert probes.sanitize_window(repo) == expected


class TestTmuxLifecycle:
    @pytest.fixture
    def repo_dir(self, tmp_path, monkeypatch):
        d = tmp_path / "repos" / "rando"
        d.mkdir(parents=True)
        (d / ".env.mai-tai").write_text("MAI_TAI_WORKSPACE_ID=abc\n")
        supervisor = tmp_path / "sup.sh"
        supervisor.write_text("#!/bin/sh\n")
        supervisor.chmod(0o755)
        monkeypatch.setattr(probes, "SUPERVISOR_PATH", supervisor)
        return d

    def _fake_run(self, monkeypatch, returncode=0, stdout="", stderr=""):
        calls = []

        def run(cmd, timeout=30):
            calls.append(cmd)
            return type("P", (), {"returncode": returncode, "stdout": stdout, "stderr": stderr})

        monkeypatch.setattr(probes, "_run", run)
        return calls

    def test_missing_directory(self, tmp_path, monkeypatch, repo_dir):
        with pytest.raises(probes.ProbeError, match="directory not found"):
            probes.tmux_start("ghost", tmp_path / "nope")

    def test_missing_env_file(self, tmp_path, monkeypatch, repo_dir):
        bare = tmp_path / "repos" / "bare"
        bare.mkdir()
        with pytest.raises(probes.ProbeError, match="no .env.mai-tai"):
            probes.tmux_start("bare", bare)

    def test_supervisor_must_be_executable(self, tmp_path, monkeypatch, repo_dir):
        dud = tmp_path / "dud.sh"
        dud.write_text("#!/bin/sh\n")
        dud.chmod(0o644)
        monkeypatch.setattr(probes, "SUPERVISOR_PATH", dud)
        with pytest.raises(probes.ProbeError, match="not executable"):
            probes.tmux_start("rando", repo_dir)

    def test_already_running_is_refused(self, monkeypatch, repo_dir):
        monkeypatch.setattr(probes, "tmux_windows", lambda: ["rando"])
        with pytest.raises(probes.ProbeError, match="already running"):
            probes.tmux_start("rando", repo_dir)

    def test_first_bot_creates_the_session(self, monkeypatch, repo_dir):
        monkeypatch.setattr(probes, "tmux_windows", lambda: [])
        calls = self._fake_run(monkeypatch)
        assert probes.tmux_start("rando", repo_dir) == "rando"
        assert calls[0][:2] == ["tmux", "new-session"]

    def test_later_bots_get_a_free_index(self, monkeypatch, repo_dir):
        monkeypatch.setattr(probes, "tmux_windows", lambda: ["folio"])
        monkeypatch.setattr(probes, "_next_free_window_index", lambda: 3)
        calls = self._fake_run(monkeypatch)
        probes.tmux_start("rando", repo_dir)
        assert calls[0][:2] == ["tmux", "new-window"]
        assert f"{probes.TMUX_SESSION}:3" in calls[0]

    def test_repo_dir_is_quoted_into_the_command(self, monkeypatch, tmp_path):
        spaced = tmp_path / "repos" / "my repo"
        spaced.mkdir(parents=True)
        (spaced / ".env.mai-tai").write_text("x=1\n")
        supervisor = tmp_path / "sup.sh"
        supervisor.write_text("#!/bin/sh\n")
        supervisor.chmod(0o755)
        monkeypatch.setattr(probes, "SUPERVISOR_PATH", supervisor)
        monkeypatch.setattr(probes, "tmux_windows", lambda: [])
        calls = self._fake_run(monkeypatch)
        probes.tmux_start("my repo", spaced)

        # tmux hands the string to `sh -c`, which runs `bash -lc <inner>`, which
        # runs <inner>. Parse both layers back apart: the supervisor must end up
        # with the directory as a single argv element, spaces and all.
        outer = shlex.split(calls[0][-1])
        assert outer[:2] == ["bash", "-lc"]
        assert shlex.split(outer[2]) == [str(supervisor), str(spaced)]

    def test_tmux_failure_surfaces(self, monkeypatch, repo_dir):
        monkeypatch.setattr(probes, "tmux_windows", lambda: [])
        self._fake_run(monkeypatch, returncode=1, stderr="no server running")
        with pytest.raises(probes.ProbeError, match="no server running"):
            probes.tmux_start("rando", repo_dir)

    def test_stop_requires_a_running_window(self, monkeypatch):
        monkeypatch.setattr(probes, "tmux_windows", lambda: [])
        with pytest.raises(probes.ProbeError, match="no window"):
            probes.tmux_stop("rando")

    def test_stop_targets_by_name(self, monkeypatch):
        monkeypatch.setattr(probes, "tmux_windows", lambda: ["test-bot-1"])
        calls = self._fake_run(monkeypatch)
        assert probes.tmux_stop("test.bot-1") == "test-bot-1"
        assert calls[0][-1] == f"{probes.TMUX_SESSION}:test-bot-1"

    def test_no_session_means_no_windows(self, monkeypatch):
        self._fake_run(monkeypatch, returncode=1, stderr="no server running")
        assert probes.tmux_windows() == []

    def test_free_index_skips_used_ones(self, monkeypatch):
        self._fake_run(monkeypatch, stdout="0\n1\n3\n")
        assert probes._next_free_window_index() == 2


class TestBotsCommands:
    @pytest.fixture
    def runner(self):
        from typer.testing import CliRunner

        return CliRunner()

    def test_start_rejects_repo_and_all_together(self, runner):
        result = runner.invoke(cli.app, ["bots", "start", "rando", "--all"])
        assert result.exit_code == 2

    def test_start_rejects_neither(self, runner):
        result = runner.invoke(cli.app, ["bots", "start"])
        assert result.exit_code == 2

    def test_all_is_idempotent(self, runner, monkeypatch):
        """Everything already up must exit 0, or a healthy run reads as broken."""
        monkeypatch.setattr(probes, "boot_repos", lambda: ["rando", "folio"])

        def already(repo, repo_dir):
            raise probes.ProbeError(f"{repo}: window is already running")

        monkeypatch.setattr(probes, "tmux_start", already)
        result = runner.invoke(cli.app, ["bots", "start", "--all"])
        assert result.exit_code == 0
        assert "2 already up" in result.stdout

    def test_a_real_failure_exits_nonzero(self, runner, monkeypatch):
        monkeypatch.setattr(probes, "boot_repos", lambda: ["rando"])

        def broken(repo, repo_dir):
            raise probes.ProbeError(f"{repo}: directory not found")

        monkeypatch.setattr(probes, "tmux_start", broken)
        result = runner.invoke(cli.app, ["bots", "start", "--all"])
        assert result.exit_code == 1
        assert "1 failed" in result.stdout

    def test_start_reports_the_window(self, runner, monkeypatch):
        monkeypatch.setattr(probes, "tmux_start", lambda repo, d: "test-bot-1")
        result = runner.invoke(cli.app, ["bots", "start", "test.bot-1"])
        assert result.exit_code == 0
        assert "test-bot-1" in result.stdout

    def test_stop_is_not_restart(self, runner, monkeypatch):
        monkeypatch.setattr(probes, "tmux_stop", lambda repo: "rando")
        result = runner.invoke(cli.app, ["bots", "stop", "rando"])
        assert result.exit_code == 0
        assert "stay down" in result.stdout

    def test_stop_unknown_repo(self, runner, monkeypatch):
        def missing(repo):
            raise probes.ProbeError("rando: no window 'rando' is running")

        monkeypatch.setattr(probes, "tmux_stop", missing)
        assert runner.invoke(cli.app, ["bots", "stop", "rando"]).exit_code == 2

    def test_version(self, runner):
        result = runner.invoke(cli.app, ["--version"])
        assert result.exit_code == 0
        assert cli.__version__ in result.stdout


class TestSupervisorCheck:
    def test_missing_supervisor_names_the_cli_fix(self, monkeypatch):
        monkeypatch.setattr(probes, "boot_repos", lambda: ["rando", "folio"])
        monkeypatch.setattr(probes, "sessions", lambda: [])
        checks = cli._check_supervisors()
        assert checks[0].level == "fail"
        assert "mai-tai bots start rando" in checks[0].detail

    def test_all_running(self, monkeypatch):
        monkeypatch.setattr(probes, "boot_repos", lambda: ["rando"])
        monkeypatch.setattr(
            probes,
            "sessions",
            lambda: [probes.Session("rando", "/repos/rando", 1, 2, 3)],
        )
        # Pin the drift probe so this test stays about "are they running" and
        # does not depend on a supervisor script existing on the test host.
        monkeypatch.setattr(probes, "supervisor_version_on_disk", lambda: None)
        assert cli._check_supervisors()[0].level == "ok"

    def test_nothing_configured_is_not_a_check(self, monkeypatch):
        monkeypatch.setattr(probes, "boot_repos", lambda: [])
        assert cli._check_supervisors() == []


class TestSupervisorDrift:
    """bash parses the whole script up front, so a running supervisor keeps
    executing the text it started with. mai-tai-dev ran pre-#37 code for a week
    and cold-greeted every night; nothing noticed. These cover the noticing."""

    def sessions(self, *repos):
        return [probes.Session(r, f"/repos/{r}", 100 + i, 200, 300) for i, r in enumerate(repos)]

    def test_up_to_date_reports_the_version(self, monkeypatch):
        monkeypatch.setattr(probes, "supervisor_version_on_disk", lambda: 2)
        monkeypatch.setattr(probes, "supervisor_running_version", lambda repo, pid: 2)
        checks = cli._check_supervisor_drift(self.sessions("rando", "folio"))
        assert [c.level for c in checks] == ["ok"]
        assert "v2" in checks[0].detail

    def test_older_running_version_warns_and_names_the_fix(self, monkeypatch):
        monkeypatch.setattr(probes, "supervisor_version_on_disk", lambda: 3)
        monkeypatch.setattr(
            probes, "supervisor_running_version", lambda repo, pid: 1 if repo == "rando" else 3
        )
        checks = cli._check_supervisor_drift(self.sessions("rando", "folio"))
        assert [c.level for c in checks] == ["warn"]
        assert "rando (v1)" in checks[0].detail
        assert "folio" not in checks[0].detail
        assert "mai-tai bots restart rando" in checks[0].detail

    def test_unstamped_supervisor_is_drift(self, monkeypatch):
        """No state file means it started before the stamp existed — which is
        precisely the week-old-code case, not a reason to stay quiet."""
        monkeypatch.setattr(probes, "supervisor_version_on_disk", lambda: 2)
        monkeypatch.setattr(probes, "supervisor_running_version", lambda repo, pid: None)
        checks = cli._check_supervisor_drift(self.sessions("mai-tai-dev"))
        assert checks[0].level == "warn"
        assert "mai-tai-dev (unstamped)" in checks[0].detail

    def test_unreadable_script_is_silent(self, monkeypatch):
        """Can't read the script => no opinion. Never invent drift."""
        monkeypatch.setattr(probes, "supervisor_version_on_disk", lambda: None)
        assert cli._check_supervisor_drift(self.sessions("rando")) == []

    def test_newer_running_version_is_not_drift(self, monkeypatch):
        """Someone restarted onto a newer script than this checkout has."""
        monkeypatch.setattr(probes, "supervisor_version_on_disk", lambda: 2)
        monkeypatch.setattr(probes, "supervisor_running_version", lambda repo, pid: 5)
        assert cli._check_supervisor_drift(self.sessions("rando"))[0].level == "ok"


class TestSupervisorVersionProbes:
    def test_reads_version_from_the_script(self, tmp_path, monkeypatch):
        script = tmp_path / "sup.sh"
        script.write_text("#!/usr/bin/env bash\nset -uo pipefail\n\nSUPERVISOR_VERSION=7\n")
        monkeypatch.setattr(probes, "SUPERVISOR_PATH", script)
        assert probes.supervisor_version_on_disk() == 7

    def test_unstamped_script_reads_none(self, tmp_path, monkeypatch):
        script = tmp_path / "sup.sh"
        script.write_text("#!/usr/bin/env bash\necho hi\n")
        monkeypatch.setattr(probes, "SUPERVISOR_PATH", script)
        assert probes.supervisor_version_on_disk() is None

    def test_missing_script_reads_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(probes, "SUPERVISOR_PATH", tmp_path / "nope.sh")
        assert probes.supervisor_version_on_disk() is None

    def test_ignores_a_commented_mention(self, tmp_path, monkeypatch):
        """The header talks about SUPERVISOR_VERSION; only the assignment counts."""
        script = tmp_path / "sup.sh"
        script.write_text("# BUMP SUPERVISOR_VERSION=99 when you change this\nSUPERVISOR_VERSION=4\n")
        monkeypatch.setattr(probes, "SUPERVISOR_PATH", script)
        assert probes.supervisor_version_on_disk() == 4

    def test_running_version_from_state_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(probes, "SUPERVISOR_LOG_DIR", tmp_path)
        (tmp_path / "supervisor-rando.state").write_text(
            "version=3\npid=4242\nrepo_dir=/repos/rando\nstarted=2026-08-14 09:00:00\n"
        )
        assert probes.supervisor_running_version("rando", 4242) == 3

    def test_state_file_for_a_dead_pid_is_ignored(self, tmp_path, monkeypatch):
        """A supervisor restarted by hand leaves the old file behind. Trusting
        it would report the new process as running code it never parsed."""
        monkeypatch.setattr(probes, "SUPERVISOR_LOG_DIR", tmp_path)
        (tmp_path / "supervisor-rando.state").write_text("version=3\npid=1111\n")
        assert probes.supervisor_running_version("rando", 4242) is None

    def test_missing_state_file_is_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(probes, "SUPERVISOR_LOG_DIR", tmp_path)
        assert probes.supervisor_running_version("rando", 4242) is None

    def test_garbled_state_file_is_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(probes, "SUPERVISOR_LOG_DIR", tmp_path)
        (tmp_path / "supervisor-rando.state").write_text("version=notanumber\npid=4242\n")
        assert probes.supervisor_running_version("rando", 4242) is None


class TestAgeFormatting:
    @pytest.mark.parametrize(
        "secs,expected",
        [
            (None, "never"),
            (3, "3s"),
            (59, "59s"),
            (60, "1m"),
            (3599, "59m"),
            (3600, "1h00m"),
            (54_000, "15h00m"),
            (86_400, "1d00h"),
            (2_041_000, "23d14h"),
        ],
    )
    def test_ages(self, secs, expected):
        assert cli._age(secs) == expected
