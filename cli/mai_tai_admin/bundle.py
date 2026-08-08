"""Deployment bundles: export a whole Mai-Tai, restore it somewhere else.

A bundle is a tar.gz holding four files at the top level:

    manifest.json   what's inside, where it came from, and which key encrypts it
    database.sql    pg_dump --clean --if-exists --no-owner --no-privileges
    env.template    blank .env skeleton, with the non-credential values filled in
    env             the source .env, only when --with-env was given

THE BUNDLE IS A SECRET. By default the dump is byte-for-byte complete, so the
credentials in users.settings (Anthropic key, GitHub token, LLM keys) travel
with it. That is deliberate — it makes the target a working copy with no
re-entry hoops — but it means the .tar.gz is credential material. It is written
mode 0600 and should be deleted once the move is done. `--scrub` produces a
credential-free bundle instead.

Ported from scripts/mai-tai-config.sh, which this replaces. The format is
unchanged and the version is deliberately still 2, so bundles written here still
restore on a host that only has the old shell script.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import shlex
import socket
import subprocess
import tarfile
from dataclasses import dataclass, field
from pathlib import Path

from . import probes
from .probes import ProbeError

BUNDLE_VERSION = 2

# The repo whose .env we read and write. Resolved from this file so an editable
# install keeps working; overridable for tests and odd layouts.
REPO_ROOT = Path(os.environ.get("MAI_TAI_REPO_ROOT", str(Path(__file__).resolve().parents[2])))

# Throwaway database used to scrub secrets without touching the live one.
SCRATCH_DB = f"{probes.PG_DB}_export_scrub"

# Keys in users.settings that hold credentials (Fernet-encrypted at rest since
# backend/app/core/crypto.py landed). Stripped by --scrub. Keep in sync with
# SENSITIVE_USER_SETTINGS there.
SECRET_SETTINGS_KEYS = (
    "anthropic_api_key",
    "openai_api_key",
    "github_token",
    "stash_llm_api_key",
)

# .env keys a target deployment needs to actually run.
#
# ENCRYPTION_KEY is optional in the sense that crypto.py derives a key from
# SECRET_KEY when it is unset — but if the source host set it, the target must
# use the same value or every stored credential in the dump decrypts to
# nothing. Same for SECRET_KEY under the fallback. check-env flags both.
REQUIRED_ENV_KEYS = (
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "SECRET_KEY",
    "NEXTAUTH_SECRET",
)
OPTIONAL_ENV_KEYS = (
    "ENCRYPTION_KEY",
    "CLAUDE_CODE_USE_VERTEX",
    "ANTHROPIC_VERTEX_PROJECT_ID",
    "CLOUD_ML_REGION",
    "AGENT_MODEL",
    "AGENT_IMAGE",
    "GITHUB_CLIENT_ID",
    "GITHUB_CLIENT_SECRET",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
)

# Optional keys whose values are operational, not secret, so env.template can
# carry them through. Everything else in OPTIONAL_ENV_KEYS is left blank.
CARRIED_ENV_KEYS = (
    "CLAUDE_CODE_USE_VERTEX",
    "ANTHROPIC_VERTEX_PROJECT_ID",
    "CLOUD_ML_REGION",
    "AGENT_MODEL",
    "AGENT_IMAGE",
)

# Everything a bundle is allowed to contain. Extraction only ever writes these
# exact names, which makes path traversal and symlink attacks impossible by
# construction rather than by validation — a tarball is not a trusted input just
# because you were the one who made it.
BUNDLE_MEMBERS = ("manifest.json", "database.sql", "env.template", "env")

# Belt to the allowlist's braces, and it silences the 3.14 deprecation warning.
# Guarded because the `filter` argument only landed in 3.11.4 and we support 3.11.
_EXTRACT_KWARGS = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}

# pg_dump/restore on a real deployment is minutes, not seconds.
DB_TIMEOUT = 1800


# ---------------------------------------------------------------------------
# .env
# ---------------------------------------------------------------------------


def env_path() -> Path:
    return REPO_ROOT / ".env"


def env_values() -> dict[str, str]:
    """Parse the repo's .env into a dict. Missing file reads as empty."""
    path = env_path()
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        # Last assignment wins, matching how docker-compose reads the file.
        values[key.strip()] = value.strip()
    return values


def crypto_fingerprint(values: dict[str, str] | None = None) -> str:
    """Identify the key that Fernet-encrypts users.settings, without revealing it.

    crypto.py uses ENCRYPTION_KEY when set and otherwise derives one from
    SECRET_KEY, so only the effective key is fingerprinted. Import compares this
    against the target's own: a mismatch means every credential in the dump
    decrypts to nothing, which is otherwise silent until an agent fails to start.
    """
    values = env_values() if values is None else values
    if values.get("ENCRYPTION_KEY"):
        material = f"enc:{values['ENCRYPTION_KEY']}"
    elif values.get("SECRET_KEY"):
        material = f"sec:{values['SECRET_KEY']}"
    else:
        return "unknown"
    return hashlib.sha256(material.encode()).hexdigest()[:16]


def env_template(source_host: str, values: dict[str, str]) -> str:
    """A blank .env skeleton so a fresh target knows what to fill in."""
    lines = [
        f"# Generated by `mai-tai config export` from {source_host}",
        "# Credential values are intentionally blank -- fill them in on the target.",
        "",
        "# --- Required ---",
        *[f"{key}=" for key in REQUIRED_ENV_KEYS],
        "",
        "# --- Optional (blank = feature off) ---",
        *[
            f"{key}={values.get(key, '') if key in CARRIED_ENV_KEYS else ''}"
            for key in OPTIONAL_ENV_KEYS
        ],
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# postgres
# ---------------------------------------------------------------------------


def require_pg() -> None:
    container = probes.containers().get(probes.PG_CONTAINER)
    if container is None or not container.running:
        raise ProbeError(
            f"Postgres container {probes.PG_CONTAINER!r} is not running. "
            "Start the stack first: ./dev.sh local up"
        )


def _pg_exec(args: list[str], timeout: int = 120) -> str:
    """Run something inside the postgres container and return its stdout.

    No `docker exec -i` — see probes.psql. Attaching stdin here would make the
    exec'd process swallow the operator's answer to the import prompt.
    """
    proc = probes._run(["docker", "exec", probes.PG_CONTAINER, *args], timeout=timeout)
    if proc.returncode != 0:
        raise ProbeError(f"{args[0]} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip()


def query(sql: str, database: str | None = None) -> str:
    """One scalar out of any database in the container."""
    return _pg_exec(["psql", "-U", probes.PG_USER, "-d", database or probes.PG_DB, "-tAc", sql])


def _pg_dump_to(dest: Path, database: str) -> None:
    """Stream pg_dump straight to a file — dumps are too big to hold in memory."""
    args = [
        "docker", "exec", probes.PG_CONTAINER,
        "pg_dump", "-U", probes.PG_USER, "-d", database,
        "--clean", "--if-exists", "--no-owner", "--no-privileges",
    ]
    try:
        with dest.open("wb") as handle:
            proc = subprocess.run(
                args, stdout=handle, stderr=subprocess.PIPE, timeout=DB_TIMEOUT, check=False
            )
    except FileNotFoundError as e:
        raise ProbeError("docker not found on PATH") from e
    except subprocess.TimeoutExpired as e:
        raise ProbeError(f"pg_dump timed out after {DB_TIMEOUT}s") from e
    if proc.returncode != 0:
        raise ProbeError(f"pg_dump failed: {proc.stderr.decode(errors='replace').strip()}")


def _psql_restore(source: Path, database: str) -> None:
    """Feed a dump back in.

    `-i` is required here and safe: stdin is the dump file, not the terminal.
    The rule against it applies to the query helpers, which would otherwise eat
    input the caller still needs.

    ON_ERROR_STOP so a partial restore fails loudly instead of leaving a
    half-populated database that looks fine until something queries it.
    """
    args = [
        "docker", "exec", "-i", probes.PG_CONTAINER,
        "psql", "-U", probes.PG_USER, "-d", database,
        "-v", "ON_ERROR_STOP=1", "--quiet", "-o", "/dev/null",
    ]
    try:
        with source.open("rb") as handle:
            proc = subprocess.run(
                args, stdin=handle, capture_output=True, timeout=DB_TIMEOUT, check=False
            )
    except FileNotFoundError as e:
        raise ProbeError("docker not found on PATH") from e
    except subprocess.TimeoutExpired as e:
        raise ProbeError(f"restore timed out after {DB_TIMEOUT}s") from e
    if proc.returncode != 0:
        raise ProbeError(f"restore failed: {proc.stderr.decode(errors='replace').strip()}")


# Credential shapes that turn up in *message bodies*, which --scrub does not
# touch: it only strips users.settings. Agents paste keys into chat, operators
# paste them back, and a "credential-free" bundle built from that history is
# nothing of the sort. This is a smoke alarm, not a guarantee — it catches the
# well-known prefixed formats and says nothing about the rest.
SECRET_PATTERNS = {
    "Anthropic API key": r"sk-ant-[A-Za-z0-9_\-]{24,}",
    "OpenAI API key": r"sk-(?:proj-)?[A-Za-z0-9_\-]{32,}",
    "GitHub token": r"gh[pousr]_[A-Za-z0-9]{36,}",
    "GitHub fine-grained PAT": r"github_pat_[A-Za-z0-9_]{50,}",
    "Google API key": r"AIza[A-Za-z0-9_\-]{35}",
    "Slack token": r"xox[baprs]-[A-Za-z0-9\-]{12,}",
    "Mai-Tai agent key": r"\bmt_[A-Za-z0-9_\-]{24,}",
    "private key block": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
}

_SECRET_RE = re.compile(
    "|".join(
        f"(?P<{re.sub(r'[^a-z]', '', name.lower())}>{pattern})"
        for name, pattern in SECRET_PATTERNS.items()
    )
)
_GROUP_NAMES = {re.sub(r"[^a-z]", "", name.lower()): name for name in SECRET_PATTERNS}


def scan_for_secrets(dump: Path) -> dict[str, int]:
    """Count credential-shaped strings in a dump. Never returns what it found.

    Streamed line by line: a real deployment's dump does not fit comfortably in
    memory, and the whole point is to run this on the big ones.
    """
    hits: dict[str, int] = {}
    with dump.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            for match in _SECRET_RE.finditer(line):
                label = _GROUP_NAMES[match.lastgroup]
                hits[label] = hits.get(label, 0) + 1
    return hits


def scrub_sql() -> str:
    """Drop every credential key from users.settings."""
    removals = "".join(f" - '{key}'" for key in SECRET_SETTINGS_KEYS)
    return f"UPDATE users SET settings = settings{removals} WHERE settings IS NOT NULL;"


def residue_sql() -> str:
    """Count users still carrying any credential key."""
    keys = ",".join(f"'{key}'" for key in SECRET_SETTINGS_KEYS)
    return f"select count(*) from users where settings ?| array[{keys}]"


def dump_scrubbed(dest: Path) -> None:
    """Scrub in a scratch copy of the database, then dump that.

    Not in the dump text and not by appending an UPDATE to the restore. A
    trailing UPDATE would leave the plaintext secrets sitting in the bundle's
    COPY blocks, and COPY blocks are not safely regex-editable. Copy -> scrub ->
    dump is the only version that guarantees the bytes on disk never held a
    credential.

    CREATE DATABASE ... TEMPLATE would be faster, but it needs zero other
    sessions on the source — and the backend is always connected — so it never
    actually wins here. Straight dump-and-reload instead.
    """
    user = shlex.quote(probes.PG_USER)
    live = shlex.quote(probes.PG_DB)
    scratch = shlex.quote(SCRATCH_DB)
    try:
        _pg_exec(["dropdb", "-U", probes.PG_USER, "--if-exists", SCRATCH_DB])
        _pg_exec(["createdb", "-U", probes.PG_USER, SCRATCH_DB])
        _pg_exec(
            [
                "sh", "-c",
                f"pg_dump -U {user} -d {live} | "
                f"psql -q -o /dev/null -U {user} -d {scratch} -v ON_ERROR_STOP=1",
            ],
            timeout=DB_TIMEOUT,
        )
        _pg_exec(
            ["psql", "-q", "-U", probes.PG_USER, "-d", SCRATCH_DB,
             "-v", "ON_ERROR_STOP=1", "-c", scrub_sql()]
        )

        # Assert the scrub landed before anything reaches disk.
        residue = query(residue_sql(), database=SCRATCH_DB)
        if residue != "0":
            raise ProbeError(
                f"scrub did not take — {residue} user(s) still carry secret settings keys"
            )

        _pg_dump_to(dest, SCRATCH_DB)
    finally:
        # A scratch DB left behind holds unscrubbed live data under a name
        # nobody would think to look at. Always drop it, even on failure.
        try:
            _pg_exec(["dropdb", "-U", probes.PG_USER, "--if-exists", SCRATCH_DB])
        except ProbeError:
            pass


_COUNTS_SQL = """
select json_build_object(
  'users', (select count(*) from users),
  'workspaces', (select count(*) from workspaces),
  'agent_workspaces', (select count(*) from workspaces where workspace_type='agent'),
  'messages', (select count(*) from messages),
  'api_keys', (select count(*) from api_keys),
  'stash_links', (select count(*) from stash_links),
  'schedules_enabled', (select count(*) from scheduled_tasks where enabled)
)
"""


def counts() -> dict:
    raw = query(_COUNTS_SQL)
    try:
        return json.loads(raw)
    except (TypeError, ValueError) as e:
        raise ProbeError(f"could not read counts from postgres: {raw!r}") from e


# ---------------------------------------------------------------------------
# manifest
# ---------------------------------------------------------------------------


@dataclass
class Manifest:
    bundle_version: int = BUNDLE_VERSION
    exported_at: str = ""
    source_host: str = ""
    alembic_revision: str = "unknown"
    contains_secrets: bool = True
    includes_env: bool = False
    crypto_fingerprint: str = "unknown"
    counts: dict = field(default_factory=dict)

    @classmethod
    def from_json(cls, raw: str) -> Manifest:
        """Tolerant on purpose: an unreadable manifest must not block a restore."""
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        known = {f: data[f] for f in cls.__dataclass_fields__ if f in data}
        return cls(**known)

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=2) + "\n"

    @property
    def enabled_schedules(self) -> int | None:
        """None when the bundle predates the field, which is not the same as 0."""
        value = self.counts.get("schedules_enabled")
        return int(value) if isinstance(value, (int, str)) and str(value).isdigit() else None


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


def default_bundle_name(host: str | None = None) -> str:
    return f"mai-tai-export-{host or short_hostname()}.tar.gz"


def short_hostname() -> str:
    return socket.gethostname().split(".")[0]


def write_bundle(out: Path, stage: Path, members: list[str]) -> None:
    """Pack the staged files.

    The archive is created 0600 *before* anything is written into it, so its
    contents are never briefly world-readable on a shared box.
    """
    out.unlink(missing_ok=True)
    out.touch(mode=0o600)
    with tarfile.open(out, "w:gz") as tar:
        for name in members:
            tar.add(stage / name, arcname=name)
    out.chmod(0o600)


def export_bundle(
    out: Path,
    *,
    stage: Path,
    scrub: bool = False,
    with_env: bool = False,
) -> tuple[Manifest, list[str], dict[str, int]]:
    """Build a bundle at `out`, staging its contents in `stage`.

    Returns the manifest, any notes worth showing the operator, and whatever
    credential-shaped strings survived in the dump.
    """
    require_pg()
    notes: list[str] = []
    stage.mkdir(parents=True, exist_ok=True)
    stage.chmod(0o700)

    if scrub:
        dump_scrubbed(stage / "database.sql")
    else:
        _pg_dump_to(stage / "database.sql", probes.PG_DB)
    leaks = scan_for_secrets(stage / "database.sql")

    # Optionally carry .env. Off by default so a bundle cannot leak infra
    # credentials nobody realised were in scope.
    includes_env = False
    if with_env:
        if env_path().exists():
            (stage / "env").write_bytes(env_path().read_bytes())
            (stage / "env").chmod(0o600)
            includes_env = True
        else:
            notes.append(f"--with-env given but no .env at {env_path()} — skipping.")

    values = env_values()
    manifest = Manifest(
        exported_at=datetime.datetime.now().astimezone().isoformat(),
        source_host=short_hostname(),
        alembic_revision=query("select version_num from alembic_version limit 1") or "unknown",
        contains_secrets=not scrub,
        includes_env=includes_env,
        crypto_fingerprint=crypto_fingerprint(values),
        counts=counts(),
    )
    (stage / "manifest.json").write_text(manifest.to_json())
    (stage / "env.template").write_text(env_template(manifest.source_host, values))

    members = ["manifest.json", "database.sql", "env.template"]
    if includes_env:
        members.append("env")
    write_bundle(out, stage, members)
    return manifest, notes, leaks


# ---------------------------------------------------------------------------
# read / import
# ---------------------------------------------------------------------------


def unpack(bundle: Path, dest: Path) -> tuple[Manifest, list[str]]:
    """Extract a bundle's known members into `dest`.

    Only names in BUNDLE_MEMBERS are ever written, and only if they are plain
    files. Anything else in the archive is returned as a note rather than
    unpacked: a bundle you were handed is still an untrusted tarball.
    """
    if not bundle.is_file():
        raise ProbeError(f"no such bundle: {bundle}")
    dest.mkdir(parents=True, exist_ok=True)

    skipped: list[str] = []
    try:
        with tarfile.open(bundle, "r:gz") as tar:
            for member in tar.getmembers():
                if member.name in BUNDLE_MEMBERS and member.isfile():
                    tar.extract(member, dest, **_EXTRACT_KWARGS)
                else:
                    skipped.append(member.name)
    except tarfile.TarError as e:
        raise ProbeError(f"{bundle} is not a readable bundle: {e}") from e

    manifest_file = dest / "manifest.json"
    manifest = Manifest.from_json(manifest_file.read_text()) if manifest_file.exists() else Manifest()
    notes = [f"ignored unexpected bundle member: {name}" for name in skipped]
    return manifest, notes


def check_version(manifest: Manifest) -> None:
    """Refuse a bundle from a newer format than we understand.

    Better to stop than to silently restore something whose layout has changed.
    """
    if manifest.bundle_version > BUNDLE_VERSION:
        raise ProbeError(
            f"bundle format v{manifest.bundle_version} is newer than this CLI "
            f"(v{BUNDLE_VERSION}) — upgrade mai-tai-admin on this host first"
        )


def fingerprint_warning(manifest: Manifest, local: str | None = None) -> str | None:
    """Warn when the target cannot decrypt what the bundle carries.

    users.settings credentials are Fernet-encrypted with a key derived from the
    source's .env. If the target's key differs they restore as undecryptable
    noise — and nothing surfaces that until an agent refuses to start.
    """
    source = manifest.crypto_fingerprint
    if not source or source == "unknown":
        return None
    local = crypto_fingerprint() if local is None else local
    if local == source:
        return None
    return (
        f"Encryption key mismatch (source {source}, here {local}). "
        "Stored credentials will not decrypt on this host. Copy ENCRYPTION_KEY and "
        "SECRET_KEY from the source .env before importing, or plan to re-enter every "
        "key in Settings > AI afterwards."
    )


def restore(stage: Path) -> None:
    database_sql = stage / "database.sql"
    if not database_sql.exists():
        raise ProbeError("bundle has no database.sql")
    _psql_restore(database_sql, probes.PG_DB)


def disable_all_schedules() -> int:
    """Turn off every scheduled task and report how many were on.

    A restored clone is otherwise LIVE: the schedules come across enabled, and
    on the next tick it starts waking agents and doing real work — from a host
    that was only ever meant to be a copy.
    """
    was_on = query("select count(*) from scheduled_tasks where enabled")
    _pg_exec(
        ["psql", "-q", "-U", probes.PG_USER, "-d", probes.PG_DB, "-v", "ON_ERROR_STOP=1",
         "-c", "update scheduled_tasks set enabled = false where enabled"]
    )
    return int(was_on or 0)


def place_imported_env(stage: Path) -> Path | None:
    """Write a bundled .env alongside the real one, never over it.

    Clobbering a working .env on the target is not something to do silently.
    """
    source = stage / "env"
    if not source.exists():
        return None
    dest = REPO_ROOT / ".env.imported"
    # chmod after the copy, not umask before it: a copy carries the source
    # file's mode across, and on some hosts (Synology w/ ACLs) that is
    # world-readable.
    dest.write_bytes(source.read_bytes())
    dest.chmod(0o600)
    return dest


# ---------------------------------------------------------------------------
# check-env
# ---------------------------------------------------------------------------


@dataclass
class EnvCheck:
    key: str
    present: bool
    required: bool


def check_env() -> list[EnvCheck]:
    if not env_path().exists():
        raise ProbeError(f"no .env at {env_path()} — copy one over, or start from .env.example")
    values = env_values()
    return [
        *[EnvCheck(key, bool(values.get(key)), True) for key in REQUIRED_ENV_KEYS],
        *[EnvCheck(key, bool(values.get(key)), False) for key in OPTIONAL_ENV_KEYS],
    ]
