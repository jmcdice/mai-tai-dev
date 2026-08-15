"""Agent container lifecycle: teardown on delete, and orphan reconciliation.

Regression cover for issue #42 — deleting a workspace returned 204 and dropped
the row while leaving the container running under `restart: unless-stopped`,
polling a workspace that no longer existed at ~1,260 requests an hour, forever,
with nothing in the UI to reveal it.
"""

import pytest
from docker.errors import DockerException, NotFound

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
        self.stopped = False

    def stop(self, timeout=None):
        self.stopped = True

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

            def get(self, name):
                for container in outer._containers:
                    if container.name == name:
                        return container
                raise NotFound(name)

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


# ---------------------------------------------------------------------------
# Archive tears the agent down, but keeps its memory
# ---------------------------------------------------------------------------
#
# Archiving used to touch only the row. Halo Craft sat archived for weeks with
# a live bot still rotating against it, and nothing showed it: every workspace
# listing filters archived rows out, so `bots list` rendered it "unmapped"
# rather than "archived". An archived workspace is precisely the one whose
# runaway agent nobody is looking at.
#
# The rule these tests pin down: archive stops the container and KEEPS the
# memory volume, because unarchive restores from it. Only delete takes it.


def archive(client, token, workspace_id, archived=True):
    return client.patch(
        f"/api/v1/workspaces/{workspace_id}",
        json={"archived": archived},
        headers=auth_headers(token),
    )


def test_archiving_agent_workspace_stops_its_container(client, user_a, monkeypatch):
    from app.api.v1 import workspaces as ws_api

    ws = make_agent_workspace(client, user_a["token"])
    calls = []
    monkeypatch.setattr(
        ws_api, "stop_agent", lambda wid, **kw: calls.append((str(wid), kw)) or {"status": "stopped"}
    )

    resp = archive(client, user_a["token"], ws["id"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["archived"] is True
    assert calls == [(ws["id"], {})], (
        "archive must stop the agent and must NOT pass remove_memory — "
        "that volume is what unarchive restores from"
    )


def test_archiving_never_removes_the_memory_volume(client, user_a, monkeypatch):
    """The distinction from delete, asserted at the spawner boundary."""
    from app.api.v1 import workspaces as ws_api
    from app.services.agents import spawner

    ws = make_agent_workspace(client, user_a["token"])
    volumes_removed = []
    monkeypatch.setattr(
        spawner, "_remove_memory_volume", lambda c, wid: volumes_removed.append(str(wid)) or True
    )
    monkeypatch.setattr(ws_api, "stop_agent", spawner.stop_agent)
    monkeypatch.setattr(spawner, "_get_docker_client", lambda: FakeDocker([]))

    assert archive(client, user_a["token"], ws["id"]).status_code == 200
    assert volumes_removed == []


def test_archiving_chat_workspace_does_not_touch_docker(client, user_a, monkeypatch):
    from app.api.v1 import workspaces as ws_api

    resp = client.post(
        "/api/v1/workspaces",
        json={"name": "Just Chat", "workspace_type": "chat"},
        headers=auth_headers(user_a["token"]),
    )
    assert resp.status_code == 201, resp.text
    ws = resp.json()

    def boom(*args, **kwargs):
        raise AssertionError("a chat workspace has no container to stop")

    monkeypatch.setattr(ws_api, "stop_agent", boom)
    assert archive(client, user_a["token"], ws["id"]).status_code == 200


def test_patch_without_archived_leaves_the_container_alone(client, user_a, monkeypatch):
    """Renaming a workspace must not take its agent down."""
    from app.api.v1 import workspaces as ws_api

    ws = make_agent_workspace(client, user_a["token"])

    def boom(*args, **kwargs):
        raise AssertionError("only an archived transition may stop the agent")

    monkeypatch.setattr(ws_api, "stop_agent", boom)
    resp = client.patch(
        f"/api/v1/workspaces/{ws['id']}",
        json={"name": "Renamed"},
        headers=auth_headers(user_a["token"]),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Renamed"


def test_archiving_an_already_archived_workspace_does_not_stop_again(
    client, user_a, monkeypatch
):
    """It is a transition, not a state. A UI that re-sends archived=true on
    every save must not keep issuing 30-second container stops."""
    from app.api.v1 import workspaces as ws_api

    ws = make_agent_workspace(client, user_a["token"])
    calls = []
    monkeypatch.setattr(
        ws_api, "stop_agent", lambda wid, **kw: calls.append(str(wid)) or {"status": "stopped"}
    )

    assert archive(client, user_a["token"], ws["id"]).status_code == 200
    assert archive(client, user_a["token"], ws["id"]).status_code == 200
    assert calls == [ws["id"]]


def test_archive_refuses_when_the_agent_cannot_be_stopped(client, user_a, monkeypatch):
    """The opposite choice from delete, on purpose.

    Delete degrades gracefully because the user wants the row gone regardless.
    An archive that 'succeeds' while the container keeps running gives you a
    workspace you cannot see and a bot you are still paying for, so this one
    refuses and says why.
    """
    from app.api.v1 import workspaces as ws_api

    ws = make_agent_workspace(client, user_a["token"])

    def down(*args, **kwargs):
        raise DockerException("Cannot connect to the Docker daemon")

    monkeypatch.setattr(ws_api, "stop_agent", down)

    resp = archive(client, user_a["token"], ws["id"])
    assert resp.status_code == 503, resp.text
    assert "not archived" in resp.json()["detail"]

    # And the row really did not move -- the point is that the two stay in sync.
    got = client.get(f"/api/v1/workspaces/{ws['id']}", headers=auth_headers(user_a["token"]))
    assert got.json()["archived"] is False


# ---------------------------------------------------------------------------
# Unarchive brings it back, with its memory
# ---------------------------------------------------------------------------


def test_unarchiving_restarts_the_agent(client, user_a, monkeypatch):
    from app.api.v1 import workspaces as ws_api

    ws = make_agent_workspace(client, user_a["token"])
    monkeypatch.setattr(ws_api, "stop_agent", lambda wid, **kw: {"status": "stopped"})
    assert archive(client, user_a["token"], ws["id"]).status_code == 200

    started = []
    monkeypatch.setattr(
        ws_api,
        "plan_agent_start",
        lambda workspace, user: type("P", (), {"kwargs": {"workspace_id": workspace.id}})(),
    )
    monkeypatch.setattr(
        ws_api,
        "start_agent",
        lambda **kw: started.append(str(kw["workspace_id"])) or {"status": "started"},
    )

    resp = archive(client, user_a["token"], ws["id"], archived=False)
    assert resp.status_code == 200, resp.text
    assert resp.json()["archived"] is False
    assert started == [ws["id"]]


def test_unarchive_survives_the_agent_failing_to_start(client, user_a, monkeypatch):
    """Best-effort by design: the row is already visible, and the UI's start
    button reports the real reason. Failing the request would hide the
    workspace again with no way to reach that button."""
    from app.api.v1 import workspaces as ws_api

    ws = make_agent_workspace(client, user_a["token"])
    monkeypatch.setattr(ws_api, "stop_agent", lambda wid, **kw: {"status": "stopped"})
    assert archive(client, user_a["token"], ws["id"]).status_code == 200

    def down(*args, **kwargs):
        raise DockerException("Cannot connect to the Docker daemon")

    monkeypatch.setattr(ws_api, "plan_agent_start", down)

    resp = archive(client, user_a["token"], ws["id"], archived=False)
    assert resp.status_code == 200, resp.text
    assert resp.json()["archived"] is False


def test_unarchive_tolerates_a_blocked_start(client, user_a, monkeypatch):
    """No credential / disabled runtime returns StartBlocked rather than raising."""
    from app.api.v1 import workspaces as ws_api
    from app.services.agents import StartBlocked

    ws = make_agent_workspace(client, user_a["token"])
    monkeypatch.setattr(ws_api, "stop_agent", lambda wid, **kw: {"status": "stopped"})
    assert archive(client, user_a["token"], ws["id"]).status_code == 200

    blocked = StartBlocked(
        code="no_credential", detail="no credential configured", runtime_id="claude-code"
    )
    monkeypatch.setattr(ws_api, "plan_agent_start", lambda workspace, user: blocked)

    def boom(**kwargs):
        raise AssertionError("a blocked plan must never reach start_agent")

    monkeypatch.setattr(ws_api, "start_agent", boom)

    assert archive(client, user_a["token"], ws["id"], archived=False).status_code == 200


# ---------------------------------------------------------------------------
# Startup sweep for archived workspaces
# ---------------------------------------------------------------------------


ARCHIVED = "33333333-3333-3333-3333-333333333333"


def test_sweep_stops_containers_for_archived_workspaces(fake_docker):
    from app.services.agents import stop_archived_agents

    live = FakeContainer("maitai-agent-11111111", LIVE)
    archived = FakeContainer("maitai-agent-33333333", ARCHIVED)
    client = fake_docker([live, archived])

    stopped = stop_archived_agents({ARCHIVED})

    assert stopped == ["maitai-agent-33333333"]
    assert archived.stopped and archived.removed
    assert not live.stopped and not live.removed
    assert client.volumes.removed == [], "archive must never reclaim the memory volume"


def test_sweep_is_a_noop_when_nothing_is_archived(fake_docker):
    from app.services.agents import stop_archived_agents

    live = FakeContainer("maitai-agent-11111111", LIVE)
    fake_docker([live])
    assert stop_archived_agents(set()) == []
    assert not live.stopped


def test_sweep_ignores_containers_without_a_workspace_label(fake_docker):
    from app.services.agents import stop_archived_agents

    stray = FakeContainer("maitai-agent-weird", ARCHIVED)
    stray.labels.pop("mai-tai.workspace-id")
    fake_docker([stray])
    assert stop_archived_agents({ARCHIVED}) == []
    assert not stray.stopped


def test_sweep_survives_docker_being_unavailable(monkeypatch):
    from app.services.agents import spawner, stop_archived_agents

    def down():
        raise DockerException("Cannot connect to the Docker daemon")

    monkeypatch.setattr(spawner, "_get_docker_client", down)
    assert stop_archived_agents({ARCHIVED}) == []
