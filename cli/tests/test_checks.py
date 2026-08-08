"""Unit tests for the doctor checks and the host probes' parsing.

None of these touch docker or postgres — the probe boundary is monkeypatched so
the tests describe *what the checks conclude*, which is the part that has been
wrong in production.
"""

from __future__ import annotations

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
