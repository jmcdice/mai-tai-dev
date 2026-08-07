"""Degraded agent detection (issue #41).

A container coming up is not the same as an agent being provisioned. When the
repo clone failed, `agent-status` said "connected", `container-status` said
"running", and the agent cheerfully described an empty directory as if that
were the assignment. Nothing anywhere reported a problem.
"""

import json

import pytest
from docker.errors import NotFound

from tests.conftest import auth_headers


class FakeExecContainer:
    def __init__(self, bootstrap=None, status="running", oom_killed=False, exec_rc=0):
        self.id = "deadbeefcafe"
        self.short_id = "deadbeefcafe"[:12]
        self.name = "maitai-agent-test"
        self.status = status
        self.labels = {"mai-tai.agent": "true"}
        self.attrs = {
            "Created": "2026-08-06T00:00:00Z",
            "RestartCount": 0,
            "State": {"OOMKilled": oom_killed},
            "HostConfig": {"Memory": 4 * 1024**3},
        }
        self._bootstrap = bootstrap
        self._exec_rc = exec_rc
        self.exec_calls = 0

    def exec_run(self, cmd):
        self.exec_calls += 1
        if self._exec_rc != 0:
            return self._exec_rc, b""
        return 0, json.dumps(self._bootstrap).encode()


@pytest.fixture
def container_factory(monkeypatch):
    """Point the spawner at a fake container and clear its caches."""
    from app.services.agents import spawner

    def _install(container):
        spawner._bootstrap_cache.clear()
        spawner._health_cache.clear()

        class _Containers:
            def get(self, name):
                if container is None:
                    raise NotFound("no such container")
                return container

        class _Client:
            containers = _Containers()

        monkeypatch.setattr(spawner, "_get_docker_client", lambda: _Client())
        return container

    yield _install

    # Both caches are module-level; leaking one into the next test would make
    # the cache-behaviour assertions order-dependent.
    spawner._bootstrap_cache.clear()
    spawner._health_cache.clear()


WS_ID = "33333333-3333-3333-3333-333333333333"


def test_failed_clone_reports_degraded(container_factory):
    from uuid import UUID

    from app.services.agents import get_agent_status

    container_factory(
        FakeExecContainer(
            bootstrap={
                "clone": "failed",
                "repo_url": "https://github.com/owner/private",
                "error": "remote: Repository not found.",
            }
        )
    )

    status = get_agent_status(UUID(WS_ID))

    assert status["running"] is True, "the container really is up — that was never the question"
    assert status["degraded"] is True
    assert "Repository clone failed" in status["problems"][0]
    assert "Repository not found" in status["problems"][0]


def test_successful_clone_is_not_degraded(container_factory):
    from uuid import UUID

    from app.services.agents import get_agent_status

    container_factory(FakeExecContainer(bootstrap={"clone": "ok"}))

    status = get_agent_status(UUID(WS_ID))
    assert status["degraded"] is False
    assert status["problems"] == []


def test_oom_kill_reports_degraded(container_factory):
    from uuid import UUID

    from app.services.agents import get_agent_status

    container_factory(FakeExecContainer(bootstrap={"clone": "ok"}, oom_killed=True))

    status = get_agent_status(UUID(WS_ID))
    assert status["degraded"] is True
    assert status["oom_killed"] is True
    assert "memory limit" in status["problems"][0]


def test_container_predating_the_marker_is_not_flagged(container_factory):
    """A missing marker means 'unknown', not 'broken'."""
    from uuid import UUID

    from app.services.agents import get_agent_status

    container_factory(FakeExecContainer(exec_rc=1))

    status = get_agent_status(UUID(WS_ID))
    assert status["bootstrap"] is None
    assert status["degraded"] is False


def test_missing_container_is_not_degraded(container_factory):
    from uuid import UUID

    from app.services.agents import get_agent_status

    container_factory(None)

    status = get_agent_status(UUID(WS_ID))
    assert status["status"] == "not_found"
    assert status["degraded"] is False


def test_bootstrap_read_is_cached_per_container(container_factory):
    """The UI polls status every few seconds; don't exec into the container each time."""
    from uuid import UUID

    from app.services.agents import get_agent_status

    container = container_factory(FakeExecContainer(bootstrap={"clone": "ok"}))

    for _ in range(5):
        get_agent_status(UUID(WS_ID))

    assert container.exec_calls == 1


def test_stopped_container_is_never_execed(container_factory):
    from uuid import UUID

    from app.services.agents import get_agent_status

    container = container_factory(FakeExecContainer(bootstrap={"clone": "ok"}, status="exited"))

    get_agent_status(UUID(WS_ID))
    assert container.exec_calls == 0


# ---------------------------------------------------------------------------
# The endpoint the UI actually polls
# ---------------------------------------------------------------------------


def test_agent_status_endpoint_surfaces_degraded(client, user_a, monkeypatch):
    from app.api.v1 import workspaces as ws_api

    resp = client.post(
        "/api/v1/workspaces",
        json={
            "name": "Broken Coder",
            "workspace_type": "agent",
            "agent_config": {"template": "coder", "repo_url": "https://github.com/o/p"},
        },
        headers=auth_headers(user_a["token"]),
    )
    ws_id = resp.json()["id"]

    monkeypatch.setattr(
        ws_api, "get_agent_problems", lambda wid: ["Repository clone failed (…): not found"]
    )

    resp = client.get(f"/api/v1/workspaces/{ws_id}/agent-status", headers=auth_headers(user_a["token"]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert "clone failed" in body["message"]


def test_healthy_agent_status_unchanged(client, user_a, monkeypatch):
    from app.api.v1 import workspaces as ws_api

    resp = client.post(
        "/api/v1/workspaces",
        json={"name": "Fine", "workspace_type": "agent", "agent_config": {"template": "coder"}},
        headers=auth_headers(user_a["token"]),
    )
    ws_id = resp.json()["id"]

    monkeypatch.setattr(ws_api, "get_agent_problems", lambda wid: [])

    resp = client.get(f"/api/v1/workspaces/{ws_id}/agent-status", headers=auth_headers(user_a["token"]))
    assert resp.json()["status"] == "offline"  # no activity recorded yet
    assert resp.json()["problems"] == []


def test_chat_workspace_status_does_not_consult_docker(client, user_a, monkeypatch):
    from app.api.v1 import workspaces as ws_api

    called = []
    monkeypatch.setattr(ws_api, "get_agent_problems", lambda wid: called.append(wid) or [])

    resp = client.get(
        f"/api/v1/workspaces/{user_a['workspace_id']}/agent-status",
        headers=auth_headers(user_a["token"]),
    )
    assert resp.status_code == 200
    assert called == []
