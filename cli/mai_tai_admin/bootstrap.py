"""First-run provisioning for `mai-tai init`.

`./dev.sh local up` gives you a stack. It does not give you an agent you can
talk to, and the distance between those two is four undocumented steps: the
agent image, a model credential, a Mai-Tai API key, and that key written into
the host's `~/.config/mai-tai/config`.

That last one is the one that hurts. `spawner.py:_get_host_mai_tai_key` reads
the agent's Mai-Tai credential from that file — mounted read-only into the
backend — so with no file every single agent start dies on
"No Mai-Tai API key available", after the user has done everything the README
told them to. This module exists to make that impossible.

Everything here is idempotent by construction: each step first asks whether it
has already been done. Re-running `init` on a provisioned host reports what it
found and changes nothing.

HTTP goes through urllib rather than httpx for the same reason `probes` shells
out to `docker` instead of importing the SDK: this runs on deployment hosts,
and the fewer things that must be installed first, the better.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import bundle, probes
from .probes import ProbeError

# Where init talks to the backend from the host's point of view. Agents use a
# different URL (http://backend:8000, resolved inside the docker network) —
# that one is the spawner's business, not ours.
DEFAULT_API_URL = os.environ.get("MAI_TAI_API_URL", "http://localhost:8000")

# The file the backend reads to find the agents' Mai-Tai credential. Must be
# the same HOME that `docker compose` interpolates into the bind mount.
HOST_CONFIG_PATH = Path(
    os.environ.get("MAI_TAI_HOST_CONFIG", str(Path.home() / ".config/mai-tai/config"))
)

# Host ADC, the Vertex fallback that lets agents run with no per-user key.
GCLOUD_ADC_PATH = Path(
    os.environ.get(
        "MAI_TAI_GCLOUD_ADC",
        str(Path.home() / ".config/gcloud/application_default_credentials.json"),
    )
)

DEFAULT_AGENT_IMAGE = "mai-tai-agent:latest"
AGENT_DOCKERFILE = "agents/claude-code/Dockerfile"

DEFAULT_WORKSPACE_NAME = "Supervisor"
DEFAULT_TEMPLATE = "assistant"
DEFAULT_PURPOSE = (
    "Supervisor for this Mai-Tai deployment. Answer the operator's questions, "
    "keep an eye on the other workspaces, and flag anything that looks wrong."
)

# A cold `docker build` of the agent image pulls a base image and installs a
# Node toolchain. Minutes, not seconds.
BUILD_TIMEOUT = 3600
STACK_UP_TIMEOUT = 900


class ApiError(ProbeError):
    """The backend answered, and the answer was an error."""

    def __init__(self, status: int, detail: str, path: str) -> None:
        super().__init__(f"{path} -> HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def _error_detail(body: str) -> str:
    """FastAPI puts the useful part in `detail`; fall back to the raw body."""
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        return body.strip()[:300] or "(empty response)"
    detail = parsed.get("detail") if isinstance(parsed, dict) else None
    if isinstance(detail, list):  # pydantic validation errors
        return "; ".join(str(d.get("msg", d)) for d in detail)
    return str(detail) if detail else body.strip()[:300]


def api(
    method: str,
    path: str,
    *,
    api_url: str = DEFAULT_API_URL,
    token: str | None = None,
    json_body: dict | None = None,
    form: dict | None = None,
    timeout: int = 30,
) -> Any:
    """One JSON call against the backend. Returns None for empty bodies."""
    url = api_url.rstrip("/") + path
    headers = {"Accept": "application/json"}
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"
    elif form is not None:
        # /auth/login is an OAuth2PasswordRequestForm, so it wants a form body
        # with `username`, not JSON with `email`. Sending JSON gets a 422 that
        # reads like a wrong password.
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = response.read().decode()
    except urllib.error.HTTPError as e:
        raise ApiError(e.code, _error_detail(e.read().decode(errors="replace")), path) from None
    except urllib.error.URLError as e:
        raise ProbeError(f"cannot reach the backend at {url}: {e.reason}") from None
    except TimeoutError:
        raise ProbeError(f"backend timed out after {timeout}s: {url}") from None
    except (http.client.HTTPException, OSError) as e:
        # RemoteDisconnected lands here, not in URLError: urllib only wraps
        # errors from sending the request, and this one comes from reading the
        # response. Uncaught it reaches the user as a 60-line rich traceback.
        raise ProbeError(f"backend dropped the connection ({type(e).__name__}): {url}") from None
    return json.loads(body) if body.strip() else None


def backend_healthy(api_url: str = DEFAULT_API_URL) -> bool:
    try:
        api("GET", "/health", api_url=api_url, timeout=5)
    except (ProbeError, ApiError):
        return False
    return True


def wait_for_backend(api_url: str = DEFAULT_API_URL, timeout: int = 180, stable: int = 3) -> bool:
    """Poll /health until it answers `stable` times running.

    One success is not enough during a recreate. Docker keeps the published
    port bound while it swaps containers, so a request can be accepted and then
    closed with no response — the old container answers /health, the next call
    hits a dead socket and raises RemoteDisconnected. Requiring consecutive
    successes waits for the *new* container instead of the tail of the old one.
    """
    deadline = time.monotonic() + timeout
    consecutive = 0
    while time.monotonic() < deadline:
        if backend_healthy(api_url):
            consecutive += 1
            if consecutive >= stable:
                return True
        else:
            consecutive = 0
        time.sleep(1)
    return False


# ---------------------------------------------------------------------------
# Host config (~/.config/mai-tai/config)
# ---------------------------------------------------------------------------


def read_host_config(path: Path | None = None) -> dict[str, str]:
    """Parse the host config into a dict. A missing file reads as empty."""
    target = path or HOST_CONFIG_PATH
    if not target.exists():
        return {}
    values: dict[str, str] = {}
    for line in target.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def ensure_host_config_dir(path: Path | None = None) -> Path:
    """Create the config directory before the stack ever starts.

    Order matters and the failure is nasty: compose bind-mounts
    `${HOME}/.config/mai-tai` into the backend, and Docker creates a missing
    bind-mount source itself — as root. Do this after `up` and the operator
    owns neither the directory nor the ability to write the config into it.
    """
    target = (path or HOST_CONFIG_PATH).parent
    target.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):  # exFAT and friends don't do modes
        target.chmod(0o700)
    return target


def write_host_config(updates: dict[str, str], path: Path | None = None) -> Path:
    """Merge `updates` into the host config, preserving every other line.

    The MCP server reads this same file for host-run Claude sessions, so it may
    already hold MAI_TAI_API_URL or a workspace id that is none of our business.
    Rewriting it wholesale would silently break those.
    """
    target = path or HOST_CONFIG_PATH
    ensure_host_config_dir(target)

    lines = target.read_text().splitlines() if target.exists() else []
    remaining = dict(updates)
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        key = stripped.partition("=")[0].strip()
        if stripped and not stripped.startswith("#") and key in remaining:
            out.append(f"{key}={remaining.pop(key)}")
        else:
            out.append(line)
    for key, value in remaining.items():
        out.append(f"{key}={value}")

    target.write_text("\n".join(out).rstrip("\n") + "\n")
    target.chmod(0o600)
    return target


def host_config_has_key(path: Path | None = None) -> bool:
    return bool(read_host_config(path).get("MAI_TAI_API_KEY"))


# ---------------------------------------------------------------------------
# Docker / stack
# ---------------------------------------------------------------------------


def stack_running() -> bool:
    """True when all three core containers are up."""
    try:
        found = probes.containers()
    except ProbeError:
        return False
    return all(
        name in found and found[name].running for name in probes.CORE_CONTAINERS
    )


def agent_image_exists(image: str = DEFAULT_AGENT_IMAGE) -> bool:
    proc = probes._run(["docker", "image", "inspect", image])
    return proc.returncode == 0


def build_agent_image(
    image: str = DEFAULT_AGENT_IMAGE, repo_root: Path | None = None
) -> None:
    """Build the agent image from the repo root.

    The root is not a detail: the Dockerfile copies `mcp-server/` into the
    image, so building from `agents/` puts it outside the context and the
    build fails halfway through with a confusing COPY error.
    """
    root = repo_root or bundle.REPO_ROOT
    dockerfile = root / AGENT_DOCKERFILE
    if not dockerfile.exists():
        raise ProbeError(f"{dockerfile} not found — is {root} the mai-tai repo?")
    proc = probes._run(
        ["docker", "build", "-t", image, "-f", str(dockerfile), str(root)],
        timeout=BUILD_TIMEOUT,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-15:]
        raise ProbeError("docker build failed:\n  " + "\n  ".join(tail))


def stack_up(repo_root: Path | None = None) -> None:
    """`./dev.sh local up` — it already generates secrets and migrates."""
    root = repo_root or bundle.REPO_ROOT
    script = root / "dev.sh"
    if not script.exists():
        raise ProbeError(f"{script} not found — is {root} the mai-tai repo?")
    proc = subprocess.run(  # noqa: S603
        ["bash", str(script), "local", "up"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=STACK_UP_TIMEOUT,
        check=False,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-15:]
        raise ProbeError("./dev.sh local up failed:\n  " + "\n  ".join(tail))


# ---------------------------------------------------------------------------
# Accounts, keys, credentials
# ---------------------------------------------------------------------------


def user_count() -> int | None:
    """How many accounts exist. None when the question can't be answered yet."""
    try:
        rows = probes.psql("select count(*) from users")
    except ProbeError:
        return None
    return int(rows[0][0]) if rows and rows[0] else 0


@dataclass
class Account:
    """The outcome of getting hold of an authenticated user."""

    email: str
    token: str
    created: bool
    raw_api_key: str | None = None  # only ever present on a fresh register


def register(
    email: str, name: str, password: str, api_url: str = DEFAULT_API_URL
) -> dict:
    return api(
        "POST",
        "/api/v1/auth/register",
        api_url=api_url,
        json_body={"email": email, "name": name, "password": password},
    )


def login(email: str, password: str, api_url: str = DEFAULT_API_URL) -> str:
    result = api(
        "POST",
        "/api/v1/auth/login",
        api_url=api_url,
        form={"username": email, "password": password},
    )
    return result["access_token"]


def create_user_api_key(
    token: str, name: str = "Default Agent Key", api_url: str = DEFAULT_API_URL
) -> str:
    """Mint a fresh user-level key. The raw value is returned exactly once."""
    result = api(
        "POST",
        "/api/v1/users/me/api-keys",
        api_url=api_url,
        token=token,
        json_body={"name": name},
    )
    return result["key"]


def write_env_values(updates: dict[str, str], path: Path | None = None) -> Path:
    """Set keys in the repo's .env, preserving everything else.

    Same merge-in-place rule as `write_host_config`, and for a sharper reason:
    .env holds POSTGRES_PASSWORD and SECRET_KEY for a database that already
    exists. Rewriting the file wholesale would lock the deployment out of its
    own data.
    """
    target = path or bundle.env_path()
    lines = target.read_text().splitlines() if target.exists() else []
    remaining = dict(updates)
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        key = stripped.partition("=")[0].strip()
        if stripped and not stripped.startswith("#") and key in remaining:
            out.append(f"{key}={remaining.pop(key)}")
        else:
            out.append(line)
    out.extend(f"{k}={v}" for k, v in remaining.items())
    target.write_text("\n".join(out) + "\n")
    with contextlib.suppress(OSError):
        target.chmod(0o600)
    return target


def configure_vertex(project: str, region: str = "global") -> Path:
    """Point .env at Vertex so agents can auth off the host's ADC.

    `.env.example` ships these blank, so a fresh install has no Vertex config
    even on a host whose ADC is sitting right there — which is how a correctly
    provisioned machine ends up being asked for an Anthropic key it does not
    need.
    """
    return write_env_values(
        {
            "CLAUDE_CODE_USE_VERTEX": "1",
            "ANTHROPIC_VERTEX_PROJECT_ID": project,
            "CLOUD_ML_REGION": region,
        }
    )


def adc_present() -> bool:
    """Whether host ADC exists, regardless of what .env says about Vertex."""
    return GCLOUD_ADC_PATH.exists()


def restart_backend(repo_root: Path | None = None) -> None:
    """Recreate the backend so it re-reads .env.

    A plain `restart` is not enough: compose passes environment at *create*
    time, so a restarted container keeps the values it was born with. Editing
    .env and restarting looks like it worked and changes nothing.
    """
    root = repo_root or bundle.REPO_ROOT
    proc = subprocess.run(  # noqa: S603
        ["docker", "compose", "-f", "docker-compose.yml", "up", "-d", "--force-recreate", "backend"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-10:]
        raise ProbeError("could not recreate the backend:\n  " + "\n  ".join(tail))


def repo_root_found() -> bool:
    """Whether we actually resolved a checkout, rather than guessing.

    See `bundle._find_repo_root`. A non-editable install cannot locate the repo
    from its own path, so this is False when `init` is run from outside one.
    """
    return bundle._looks_like_repo(bundle.REPO_ROOT)


def vertex_configured(env: dict[str, str] | None = None) -> bool:
    """True when the host can auth agents through Vertex with no user key.

    Mirrors `spawner.get_host_vertex_config`: the flag and the project have to
    be in .env *and* the ADC file has to actually be on disk. Two of three is
    the state that produces an agent which starts and then dies on its first
    turn.
    """
    values = env if env is not None else bundle.env_values()
    enabled = values.get("CLAUDE_CODE_USE_VERTEX", "").strip() in ("1", "true", "True")
    project = values.get("ANTHROPIC_VERTEX_PROJECT_ID", "").strip()
    return bool(enabled and project and GCLOUD_ADC_PATH.exists())


def set_anthropic_key(token: str, key: str, api_url: str = DEFAULT_API_URL) -> None:
    """Store the user's Anthropic key. The backend encrypts it at rest."""
    api(
        "PUT",
        "/api/v1/auth/me",
        api_url=api_url,
        token=token,
        json_body={"settings": {"anthropic_api_key": key}},
    )


def has_anthropic_key(token: str, api_url: str = DEFAULT_API_URL) -> bool:
    """Whether the user already has a stored model credential.

    `/auth/me` returns secrets masked, never raw — a non-empty value here means
    "something is stored", which is all we need to decide whether to prompt.
    """
    me = api("GET", "/api/v1/auth/me", api_url=api_url, token=token)
    settings = (me or {}).get("settings") or {}
    return bool(settings.get("anthropic_api_key"))


# ---------------------------------------------------------------------------
# Workspace + agent
# ---------------------------------------------------------------------------


def find_workspace(
    token: str, name: str, api_url: str = DEFAULT_API_URL
) -> dict | None:
    result = api("GET", "/api/v1/workspaces", api_url=api_url, token=token)
    items = result if isinstance(result, list) else (result or {}).get("workspaces", [])
    for workspace in items:
        if workspace.get("name") == name:
            return workspace
    return None


def create_agent_workspace(
    token: str,
    name: str = DEFAULT_WORKSPACE_NAME,
    template: str = DEFAULT_TEMPLATE,
    purpose: str = DEFAULT_PURPOSE,
    model: str | None = None,
    runtime: str = "claude-code",
    api_url: str = DEFAULT_API_URL,
) -> dict:
    config: dict[str, Any] = {"runtime": runtime, "template": template}
    if model:
        config["model"] = model
    return api(
        "POST",
        "/api/v1/workspaces",
        api_url=api_url,
        token=token,
        json_body={
            "name": name,
            "workspace_type": "agent",
            "agent_purpose": purpose,
            "agent_config": config,
        },
    )


def start_agent(token: str, workspace_id: str, api_url: str = DEFAULT_API_URL) -> dict:
    return api(
        "POST",
        f"/api/v1/workspaces/{workspace_id}/agent/start",
        api_url=api_url,
        token=token,
        timeout=120,
    )


def agent_container_running(workspace_id: str) -> bool:
    name = probes.agent_container_name(workspace_id)
    try:
        container = probes.containers().get(name)
    except ProbeError:
        return False
    return bool(container and container.running)


def wait_for_checkin(workspace_id: str, timeout: int = 300) -> int | None:
    """Wait for the agent to phone home; returns its heartbeat age in seconds.

    A running container is not a working agent — that is the whole lesson of
    the watchdog. The proof is a row in `workspace_agent_activity`, which only
    appears once the container has booted, resolved a credential, connected to
    MCP, and made a call. Anything less and we would be reporting success for
    a container that is about to die.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            age = probes.heartbeat_secs(workspace_id)
        except ProbeError:
            age = None
        if age is not None:
            return age
        if not agent_container_running(workspace_id):
            return None
        time.sleep(5)
    return None
