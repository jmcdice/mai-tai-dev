"""Agent container lifecycle: teardown on delete, and orphan reconciliation.

Regression cover for issue #42 — deleting a workspace returned 204 and dropped
the row while leaving the container running under `restart: unless-stopped`,
polling a workspace that no longer existed at ~1,260 requests an hour, forever,
with nothing in the UI to reveal it.
"""

import pytest
from docker.errors import DockerException

from tests.conftest import auth_headers


def make_agent_workspace(client, token: str, name: str = "Agent WS") -> dict:
    resp = client.post(
        "/api/v1/workspaces",
        json={
            "name": name,
            "workspace_type": "agent",
            "agent_config": {"template": "coder"},
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Delete tears the agent down
# ---------------------------------------------------------------------------


def test_deleting_agent_workspace_stops_its_container(client, user_a, monkeypatch):
    from app.api.v1 import workspaces as ws_api

    ws = make_agent_workspace(client, user_a["token"])
    calls = []
    monkeypatch.setattr(
        ws_api, "stop_agent", lambda wid, **kw: calls.append((str(wid), kw)) or {"status": "stopped"}
    )

    resp = client.delete(f"/api/v1/workspaces/{ws['id']}", headers=auth_headers(user_a["token"]))
    assert resp.status_code == 204
    assert calls == [(ws["id"], {"remove_memory": True})], (
        "delete must stop the agent and reclaim its memory volume"
    )


def test_deleting_chat_workspace_does_not_touch_docker(client, user_a, monkeypatch):
    from app.api.v1 import workspaces as ws_api

    called = []
    monkeypatch.setattr(ws_api, "stop_agent", lambda wid, **kw: called.append(wid))

    resp = client.post(
        "/api/v1/workspaces", json={"name": "Just Chat"}, headers=auth_headers(user_a["token"])
    )
    ws_id = resp.json()["id"]
    resp = client.delete(f"/api/v1/workspaces/{ws_id}", headers=auth_headers(user_a["token"]))

    assert resp.status_code == 204
    assert called == []


def test_delete_succeeds_even_when_docker_is_down(client, user_a, monkeypatch):
    """A Docker outage must not strand the user with an undeletable workspace."""
    from app.api.v1 import workspaces as ws_api

    ws = make_agent_workspace(client, user_a["token"])

    def explode(*args, **kwargs):
        raise DockerException("Cannot connect to the Docker daemon")

    monkeypatch.setattr(ws_api, "stop_agent", explode)

    resp = client.delete(f"/api/v1/workspaces/{ws['id']}", headers=auth_headers(user_a["token"]))
    assert resp.status_code == 204

    resp = client.get(f"/api/v1/workspaces/{ws['id']}", headers=auth_headers(user_a["token"]))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Orphan reconciliation
# ---------------------------------------------------------------------------


class FakeContainer:
    def __init__(self, name, workspace_id):
        self.name = name
        self.labels = {"mai-tai.agent": "true", "mai-tai.workspace-id": workspace_id}
        self.removed = False

    def remove(self, force=False):
        self.removed = True


class FakeVolumes:
    def __init__(self):
        self.removed = []

    def get(self, name):
        volumes = self

        class _Vol:
            def remove(self, force=False):
                volumes.removed.append(name)

        return _Vol()


class FakeDocker:
    def __init__(self, containers):
        self._containers = containers
        self.volumes = FakeVolumes()

    @property
    def containers(self):
        outer = self

        class _Containers:
            def list(self, all=False, filters=None):
                return outer._containers

        return _Containers()


LIVE = "11111111-1111-1111-1111-111111111111"
DEAD = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def fake_docker(monkeypatch):
    from app.services.agents import spawner

    def _install(containers):
        client = FakeDocker(containers)
        monkeypatch.setattr(spawner, "_get_docker_client", lambda: client)
        return client

    return _install


def test_reaper_removes_containers_for_deleted_workspaces(fake_docker):
    from app.services.agents import reap_orphaned_agents

    live = FakeContainer("maitai-agent-11111111", LIVE)
    dead = FakeContainer("maitai-agent-22222222", DEAD)
    client = fake_docker([live, dead])

    reaped = reap_orphaned_agents({LIVE})

    assert reaped == ["maitai-agent-22222222"]
    assert dead.removed and not live.removed
    assert client.volumes.removed == [f"maitai-agent-memory-{DEAD}"]


def test_reaper_is_a_noop_when_every_workspace_is_live(fake_docker):
    from app.services.agents import reap_orphaned_agents

    live = FakeContainer("maitai-agent-11111111", LIVE)
    fake_docker([live])

    assert reap_orphaned_agents({LIVE, DEAD}) == []
    assert not live.removed


def test_reaper_ignores_containers_without_a_workspace_label(fake_docker):
    """Never remove something we can't positively identify as an orphan."""
    from app.services.agents import reap_orphaned_agents

    unlabelled = FakeContainer("maitai-agent-33333333", "")
    fake_docker([unlabelled])

    assert reap_orphaned_agents({LIVE}) == []
    assert not unlabelled.removed


def test_reaper_survives_docker_being_unavailable(monkeypatch):
    from app.services.agents import reap_orphaned_agents
    from app.services.agents import spawner

    def explode():
        raise DockerException("Cannot connect to the Docker daemon")

    monkeypatch.setattr(spawner, "_get_docker_client", explode)
    assert reap_orphaned_agents({LIVE}) == []
