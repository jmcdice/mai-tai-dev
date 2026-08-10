"""Unit tests for `mai-tai init` and its provisioning helpers.

Nothing here touches docker, postgres, or the network — the HTTP call and the
probe boundary are monkeypatched, so what the tests describe is the *decisions*
init makes: what it skips, what it refuses, and what it writes where. Those are
the parts that can silently produce a deployment where Start Agent never works.
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from mai_tai_admin import bootstrap
from mai_tai_admin.probes import ProbeError


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, body: str) -> None:
        self._body = body.encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestApi:
    def test_json_body_and_bearer_token(self, monkeypatch):
        seen = {}

        def fake_urlopen(request, timeout=None):
            seen["url"] = request.full_url
            seen["method"] = request.method
            seen["headers"] = dict(request.headers)
            seen["data"] = request.data
            return FakeResponse('{"ok": true}')

        monkeypatch.setattr(bootstrap.urllib.request, "urlopen", fake_urlopen)
        result = bootstrap.api(
            "POST", "/api/v1/thing", api_url="http://h:8000", token="t0k", json_body={"a": 1}
        )

        assert result == {"ok": True}
        assert seen["url"] == "http://h:8000/api/v1/thing"
        assert seen["method"] == "POST"
        assert seen["headers"]["Authorization"] == "Bearer t0k"
        assert json.loads(seen["data"]) == {"a": 1}

    def test_login_sends_a_form_not_json(self, monkeypatch):
        """The backend uses OAuth2PasswordRequestForm; JSON gets a 422."""
        seen = {}

        def fake_urlopen(request, timeout=None):
            seen["headers"] = dict(request.headers)
            seen["data"] = request.data.decode()
            return FakeResponse('{"access_token": "abc", "refresh_token": "d"}')

        monkeypatch.setattr(bootstrap.urllib.request, "urlopen", fake_urlopen)
        assert bootstrap.login("me@example.com", "pw") == "abc"
        assert seen["headers"]["Content-type"] == "application/x-www-form-urlencoded"
        assert "username=me%40example.com" in seen["data"]
        assert "email=" not in seen["data"]

    def test_empty_body_is_none_not_a_json_error(self, monkeypatch):
        monkeypatch.setattr(
            bootstrap.urllib.request, "urlopen", lambda r, timeout=None: FakeResponse("")
        )
        assert bootstrap.api("PUT", "/api/v1/thing") is None

    def test_http_error_surfaces_the_fastapi_detail(self, monkeypatch):
        def fake_urlopen(request, timeout=None):
            raise urllib.error.HTTPError(
                request.full_url, 400, "Bad Request", {}, io.BytesIO(b'{"detail": "Email already registered"}')
            )

        monkeypatch.setattr(bootstrap.urllib.request, "urlopen", fake_urlopen)
        with pytest.raises(bootstrap.ApiError) as excinfo:
            bootstrap.api("POST", "/api/v1/auth/register")
        assert excinfo.value.status == 400
        assert "Email already registered" in str(excinfo.value)

    def test_validation_errors_are_flattened(self, monkeypatch):
        body = '{"detail": [{"msg": "field required"}, {"msg": "not an email"}]}'

        def fake_urlopen(request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, 422, "x", {}, io.BytesIO(body.encode()))

        monkeypatch.setattr(bootstrap.urllib.request, "urlopen", fake_urlopen)
        with pytest.raises(bootstrap.ApiError) as excinfo:
            bootstrap.api("POST", "/api/v1/auth/register")
        assert "field required; not an email" in str(excinfo.value)

    def test_unreachable_backend_is_a_probe_error_not_a_traceback(self, monkeypatch):
        def fake_urlopen(request, timeout=None):
            raise urllib.error.URLError("Connection refused")

        monkeypatch.setattr(bootstrap.urllib.request, "urlopen", fake_urlopen)
        with pytest.raises(ProbeError, match="cannot reach the backend"):
            bootstrap.api("GET", "/health")

    def test_backend_healthy_is_false_when_unreachable(self, monkeypatch):
        def fake_urlopen(request, timeout=None):
            raise urllib.error.URLError("nope")

        monkeypatch.setattr(bootstrap.urllib.request, "urlopen", fake_urlopen)
        assert bootstrap.backend_healthy() is False


# ---------------------------------------------------------------------------
# Host config — the file that decides whether agents can start at all
# ---------------------------------------------------------------------------


class TestHostConfig:
    def test_missing_file_reads_as_empty(self, tmp_path):
        assert bootstrap.read_host_config(tmp_path / "nope") == {}

    def test_parses_ignoring_comments_and_blanks(self, tmp_path):
        path = tmp_path / "config"
        path.write_text("# a comment\n\nMAI_TAI_API_KEY=mt_abc\nMAI_TAI_API_URL=http://x:8000\n")
        assert bootstrap.read_host_config(path) == {
            "MAI_TAI_API_KEY": "mt_abc",
            "MAI_TAI_API_URL": "http://x:8000",
        }

    def test_write_creates_the_file_mode_0600(self, tmp_path):
        path = tmp_path / "sub" / "config"
        bootstrap.write_host_config({"MAI_TAI_API_KEY": "mt_abc"}, path=path)
        assert path.read_text() == "MAI_TAI_API_KEY=mt_abc\n"
        assert path.stat().st_mode & 0o777 == 0o600

    def test_write_preserves_unrelated_lines(self, tmp_path):
        """The MCP server reads this file too — clobbering it breaks host sessions."""
        path = tmp_path / "config"
        path.write_text("# mine\nMAI_TAI_WORKSPACE_ID=ws-123\nMAI_TAI_API_KEY=old\n")
        bootstrap.write_host_config({"MAI_TAI_API_KEY": "new"}, path=path)
        text = path.read_text()
        assert "# mine" in text
        assert "MAI_TAI_WORKSPACE_ID=ws-123" in text
        assert "MAI_TAI_API_KEY=new" in text
        assert "old" not in text

    def test_write_appends_keys_that_were_not_there(self, tmp_path):
        path = tmp_path / "config"
        path.write_text("MAI_TAI_API_KEY=mt_abc\n")
        bootstrap.write_host_config({"MAI_TAI_API_URL": "http://h:8000"}, path=path)
        assert "MAI_TAI_API_URL=http://h:8000" in path.read_text()
        assert "MAI_TAI_API_KEY=mt_abc" in path.read_text()

    def test_has_key_is_false_when_the_value_is_blank(self, tmp_path):
        path = tmp_path / "config"
        path.write_text("MAI_TAI_API_KEY=\n")
        assert bootstrap.host_config_has_key(path) is False

    def test_ensure_dir_is_idempotent(self, tmp_path):
        path = tmp_path / "deep" / "er" / "config"
        assert bootstrap.ensure_host_config_dir(path) == path.parent
        assert bootstrap.ensure_host_config_dir(path).is_dir()


# ---------------------------------------------------------------------------
# Vertex detection
# ---------------------------------------------------------------------------


class TestVertexConfigured:
    @pytest.fixture
    def adc(self, tmp_path, monkeypatch):
        path = tmp_path / "adc.json"
        monkeypatch.setattr(bootstrap, "GCLOUD_ADC_PATH", path)
        return path

    def test_all_three_present(self, adc):
        adc.write_text("{}")
        assert bootstrap.vertex_configured(
            {"CLAUDE_CODE_USE_VERTEX": "1", "ANTHROPIC_VERTEX_PROJECT_ID": "p"}
        )

    def test_flag_on_but_no_adc_on_disk(self, adc):
        """The state that produces an agent which starts and then dies."""
        assert not bootstrap.vertex_configured(
            {"CLAUDE_CODE_USE_VERTEX": "1", "ANTHROPIC_VERTEX_PROJECT_ID": "p"}
        )

    def test_flag_on_but_no_project(self, adc):
        adc.write_text("{}")
        assert not bootstrap.vertex_configured({"CLAUDE_CODE_USE_VERTEX": "1"})

    def test_flag_off(self, adc):
        adc.write_text("{}")
        assert not bootstrap.vertex_configured(
            {"CLAUDE_CODE_USE_VERTEX": "", "ANTHROPIC_VERTEX_PROJECT_ID": "p"}
        )


# ---------------------------------------------------------------------------
# Docker-facing helpers
# ---------------------------------------------------------------------------


class Completed:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestStackAndImage:
    def test_stack_running_needs_all_three(self, monkeypatch):
        from mai_tai_admin import probes

        def only_two():
            return {
                "maitai-postgres": probes.Container("maitai-postgres", "running", "Up"),
                "maitai-backend": probes.Container("maitai-backend", "running", "Up"),
            }

        monkeypatch.setattr(probes, "containers", only_two)
        assert bootstrap.stack_running() is False

    def test_stack_running_false_when_docker_is_missing(self, monkeypatch):
        from mai_tai_admin import probes

        def boom():
            raise ProbeError("docker not found on PATH")

        monkeypatch.setattr(probes, "containers", boom)
        assert bootstrap.stack_running() is False

    def test_agent_image_exists_reads_the_exit_code(self, monkeypatch):
        from mai_tai_admin import probes

        monkeypatch.setattr(probes, "_run", lambda cmd, timeout=30: Completed(returncode=1))
        assert bootstrap.agent_image_exists("mai-tai-agent:latest") is False

    def test_build_uses_the_repo_root_as_context(self, tmp_path, monkeypatch):
        """Building from agents/ leaves mcp-server/ outside the context."""
        (tmp_path / "agents/claude-code").mkdir(parents=True)
        (tmp_path / "agents/claude-code/Dockerfile").write_text("FROM scratch\n")
        seen = {}

        from mai_tai_admin import probes

        def fake_run(cmd, timeout=30):
            seen["cmd"] = cmd
            return Completed(returncode=0)

        monkeypatch.setattr(probes, "_run", fake_run)
        bootstrap.build_agent_image("img:t", repo_root=tmp_path)
        assert seen["cmd"][-1] == str(tmp_path)
        assert seen["cmd"][:3] == ["docker", "build", "-t"]

    def test_build_refuses_outside_the_repo(self, tmp_path):
        with pytest.raises(ProbeError, match="the mai-tai repo"):
            bootstrap.build_agent_image("img:t", repo_root=tmp_path)

    def test_build_failure_reports_the_tail_not_the_whole_log(self, tmp_path, monkeypatch):
        (tmp_path / "agents/claude-code").mkdir(parents=True)
        (tmp_path / "agents/claude-code/Dockerfile").write_text("FROM scratch\n")
        noise = "\n".join(f"line {i}" for i in range(200))

        from mai_tai_admin import probes

        monkeypatch.setattr(
            probes, "_run", lambda cmd, timeout=30: Completed(returncode=1, stderr=noise)
        )
        with pytest.raises(ProbeError) as excinfo:
            bootstrap.build_agent_image("img:t", repo_root=tmp_path)
        assert "line 199" in str(excinfo.value)
        assert "line 100" not in str(excinfo.value)


class TestUserCount:
    def test_counts_rows(self, monkeypatch):
        from mai_tai_admin import probes

        monkeypatch.setattr(probes, "psql", lambda sql: [["3"]])
        assert bootstrap.user_count() == 3

    def test_unmigrated_database_is_unknown_not_zero(self, monkeypatch):
        """Before migrations `users` does not exist. Reporting 0 would make
        init try to register into a database that cannot hold the row."""
        from mai_tai_admin import probes

        def boom(sql):
            raise ProbeError('relation "users" does not exist')

        monkeypatch.setattr(probes, "psql", boom)
        assert bootstrap.user_count() is None


# ---------------------------------------------------------------------------
# Workspace + agent
# ---------------------------------------------------------------------------


class TestWorkspace:
    def test_find_matches_by_name(self, monkeypatch):
        monkeypatch.setattr(
            bootstrap,
            "api",
            lambda *a, **k: {"workspaces": [{"id": "1", "name": "Other"}, {"id": "2", "name": "Supervisor"}]},
        )
        assert bootstrap.find_workspace("t", "Supervisor")["id"] == "2"

    def test_find_handles_a_bare_list_response(self, monkeypatch):
        monkeypatch.setattr(bootstrap, "api", lambda *a, **k: [{"id": "9", "name": "Supervisor"}])
        assert bootstrap.find_workspace("t", "Supervisor")["id"] == "9"

    def test_find_returns_none_when_absent(self, monkeypatch):
        monkeypatch.setattr(bootstrap, "api", lambda *a, **k: {"workspaces": []})
        assert bootstrap.find_workspace("t", "Supervisor") is None

    def test_create_omits_model_when_unset(self, monkeypatch):
        """An explicit null model would override the runtime's own default."""
        seen = {}

        def fake_api(method, path, **kwargs):
            seen.update(kwargs.get("json_body") or {})
            return {"id": "abc"}

        monkeypatch.setattr(bootstrap, "api", fake_api)
        bootstrap.create_agent_workspace("t", name="S", template="assistant")
        assert "model" not in seen["agent_config"]
        assert seen["workspace_type"] == "agent"
        assert seen["agent_config"]["template"] == "assistant"

    def test_create_passes_the_model_through(self, monkeypatch):
        seen = {}

        def fake_api(method, path, **kwargs):
            seen.update(kwargs.get("json_body") or {})
            return {"id": "abc"}

        monkeypatch.setattr(bootstrap, "api", fake_api)
        bootstrap.create_agent_workspace("t", model="opus")
        assert seen["agent_config"]["model"] == "opus"


class TestWaitForCheckin:
    WS = "cd1b8708-5d17-4ef4-b089-84db652a0489"

    def test_returns_the_heartbeat_age(self, monkeypatch):
        from mai_tai_admin import probes

        monkeypatch.setattr(probes, "heartbeat_secs", lambda ws: 4)
        assert bootstrap.wait_for_checkin(self.WS, timeout=1) == 4

    def test_gives_up_immediately_when_the_container_died(self, monkeypatch):
        """No heartbeat and no container means waiting out the timeout is
        pointless — the agent is never going to check in."""
        from mai_tai_admin import probes

        monkeypatch.setattr(probes, "heartbeat_secs", lambda ws: None)
        monkeypatch.setattr(probes, "containers", dict)
        monkeypatch.setattr(bootstrap.time, "sleep", lambda s: pytest.fail("should not sleep"))
        assert bootstrap.wait_for_checkin(self.WS, timeout=300) is None

    def test_keeps_waiting_while_the_container_is_up(self, monkeypatch):
        from mai_tai_admin import probes

        calls = {"n": 0}

        def heartbeat(ws):
            calls["n"] += 1
            return 2 if calls["n"] > 2 else None

        monkeypatch.setattr(probes, "heartbeat_secs", heartbeat)
        monkeypatch.setattr(
            probes,
            "containers",
            lambda: {
                probes.agent_container_name(self.WS): probes.Container(
                    probes.agent_container_name(self.WS), "running", "Up"
                )
            },
        )
        monkeypatch.setattr(bootstrap.time, "sleep", lambda s: None)
        assert bootstrap.wait_for_checkin(self.WS, timeout=300) == 2
