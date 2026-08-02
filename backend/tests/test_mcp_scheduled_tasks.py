"""Agent-facing scheduled tasks — the API-key half of the schedule surface.

What's worth testing here isn't CRUD; it's the three ways giving an agent
write access to a cron table could go wrong: reaching another workspace,
retiming a job without the scheduler noticing, and creating schedules without
bound.
"""

DENVER = "America/Denver"


def mcp_headers(user: dict) -> dict:
    return {"X-API-Key": user["api_key"], "X-Workspace-ID": user["workspace_id"]}


def create(client, user: dict, **overrides) -> dict:
    payload = {
        "name": "Morning build check",
        "prompt": "Check last night's CI on main and report failures.",
        "cron_expression": "0 5 * * *",
        "timezone": DENVER,
        **overrides,
    }
    return client.post("/api/v1/mcp/scheduled-tasks", json=payload, headers=mcp_headers(user))


def test_agent_creates_and_lists(client, user_a):
    resp = create(client, user_a)
    assert resp.status_code == 201, resp.text
    task = resp.json()
    assert task["timezone"] == DENVER
    assert task["next_run_at"] is not None
    # The preview is what the agent reads back to the human, so it has to be there
    assert len(task["next_runs"]) == 3

    resp = client.get("/api/v1/mcp/scheduled-tasks", headers=mcp_headers(user_a))
    assert resp.status_code == 200
    listed = resp.json()["tasks"]
    assert [t["id"] for t in listed] == [task["id"]]
    # "What do I have scheduled?" is the question most likely to be answered
    # out loud, so list must carry the times too — not just create and patch.
    assert len(listed[0]["next_runs"]) == 3


def test_fire_times_carry_the_task_timezone(client, user_a):
    """Naive UTC is fine for the web form — the browser localises it. An agent
    has no such step, so an unlabelled 11:00 on a Denver task becomes "11am"
    when it reports back. Every agent-facing time has to carry its offset."""
    from datetime import datetime

    created = create(client, user_a).json()
    listed = client.get(
        "/api/v1/mcp/scheduled-tasks", headers=mcp_headers(user_a)
    ).json()["tasks"][0]
    previewed = client.post(
        "/api/v1/mcp/schedule-preview",
        json={"cron_expression": "0 5 * * *", "timezone": DENVER},
        headers=mcp_headers(user_a),
    ).json()

    for source, runs in (
        ("create", created["next_runs"]),
        ("list", listed["next_runs"]),
        ("preview", previewed["next_runs"]),
    ):
        for raw in runs:
            when = datetime.fromisoformat(raw)
            assert when.utcoffset() is not None, f"{source} returned a naive time"
            # The cron says 5am and the zone is Denver; local wall-clock must
            # read 5, not the 11 or 12 it would be in UTC.
            assert when.hour == 5, f"{source} gave {raw}, expected 05:00 local"


def test_timezone_is_required(client, user_a):
    """The UTC default is fine for a human with a dropdown; for an agent it's a
    silent seven-hour error, so the agent surface makes it mandatory."""
    resp = client.post(
        "/api/v1/mcp/scheduled-tasks",
        json={"name": "n", "prompt": "p", "cron_expression": "0 5 * * *"},
        headers=mcp_headers(user_a),
    )
    assert resp.status_code == 422
    assert "timezone" in resp.text


def test_bad_cron_is_rejected(client, user_a):
    resp = create(client, user_a, cron_expression="every morning please")
    assert resp.status_code == 422


def test_agent_cannot_reach_another_workspace(client, user_a, user_b):
    """The workspace comes from the key, not the payload — there's no parameter
    to tamper with, so this asserts the absence of a back door."""
    created = create(client, user_b).json()

    # A's key sees none of B's tasks...
    resp = client.get("/api/v1/mcp/scheduled-tasks", headers=mcp_headers(user_a))
    assert resp.json()["tasks"] == []

    # ...and cannot address one by id, even a valid one.
    for method in ("patch", "delete"):
        resp = getattr(client, method)(
            f"/api/v1/mcp/scheduled-tasks/{created['id']}",
            headers=mcp_headers(user_a),
            **({"json": {"enabled": False}} if method == "patch" else {}),
        )
        assert resp.status_code == 404, f"{method} leaked across workspaces"


def test_retiming_recomputes_next_run(client, user_a):
    """The scheduler only ever reads next_run_at. An update that changed the
    cron but left next_run_at stale would fire at the old time forever."""
    task = create(client, user_a).json()
    before = task["next_run_at"]

    resp = client.patch(
        f"/api/v1/mcp/scheduled-tasks/{task['id']}",
        json={"cron_expression": "30 22 * * *"},
        headers=mcp_headers(user_a),
    )
    assert resp.status_code == 200
    assert resp.json()["next_run_at"] != before


def test_disabling_clears_next_run_and_preview(client, user_a):
    task = create(client, user_a).json()
    resp = client.patch(
        f"/api/v1/mcp/scheduled-tasks/{task['id']}",
        json={"enabled": False},
        headers=mcp_headers(user_a),
    )
    assert resp.status_code == 200
    paused = resp.json()
    assert paused["next_run_at"] is None
    # A paused job has no upcoming fires; reporting the times it *would* have
    # run is how an agent tells the human a stopped job runs tomorrow.
    assert paused["next_runs"] == []

    # Re-enabling gets a fresh time rather than the expired one it had
    resp = client.patch(
        f"/api/v1/mcp/scheduled-tasks/{task['id']}",
        json={"enabled": True},
        headers=mcp_headers(user_a),
    )
    assert resp.json()["next_run_at"] is not None


def test_delete_removes_it(client, user_a):
    task = create(client, user_a).json()
    resp = client.delete(
        f"/api/v1/mcp/scheduled-tasks/{task['id']}", headers=mcp_headers(user_a)
    )
    assert resp.status_code == 204
    assert client.get("/api/v1/mcp/scheduled-tasks", headers=mcp_headers(user_a)).json()[
        "tasks"
    ] == []


def test_task_count_is_capped(client, user_a):
    """An agent that can schedule can schedule a job that wakes it to schedule
    more. The cap makes that a bounded mistake instead of a runaway one."""
    from app.services.scheduled_tasks import MAX_TASKS_PER_WORKSPACE

    for i in range(MAX_TASKS_PER_WORKSPACE):
        assert create(client, user_a, name=f"task-{i}").status_code == 201

    resp = create(client, user_a, name="one too many")
    assert resp.status_code == 409
    assert str(MAX_TASKS_PER_WORKSPACE) in resp.json()["detail"]


def test_preview_creates_nothing(client, user_a):
    resp = client.post(
        "/api/v1/mcp/schedule-preview",
        json={"cron_expression": "0 5 * * *", "timezone": DENVER},
        headers=mcp_headers(user_a),
    )
    assert resp.status_code == 200
    assert len(resp.json()["next_runs"]) == 3
    assert client.get("/api/v1/mcp/scheduled-tasks", headers=mcp_headers(user_a)).json()[
        "total"
    ] == 0


def test_unauthenticated_is_rejected(client, user_a):
    assert client.get("/api/v1/mcp/scheduled-tasks").status_code in (401, 403)
    assert (
        client.get(
            "/api/v1/mcp/scheduled-tasks",
            headers={"X-API-Key": "mt_bogus", "X-Workspace-ID": user_a["workspace_id"]},
        ).status_code
        == 401
    )
