"""Tests for deployment bundles.

No docker and no postgres: the postgres boundary is monkeypatched, so what gets
asserted is the part that has consequences — what lands in the bundle, what is
refused, and what does *not* leak into a file marked safe to share.
"""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mai_tai_admin import bundle, cli, probes
from mai_tai_admin.probes import ProbeError

runner = CliRunner()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A fake repo root whose .env the module will read."""
    monkeypatch.setattr(bundle, "REPO_ROOT", tmp_path)
    return tmp_path


def write_env(repo: Path, body: str) -> None:
    (repo / ".env").write_text(body)


class TestEnvParsing:
    def test_comments_blanks_and_junk_are_ignored(self, repo):
        write_env(repo, "# a comment\n\nPOSTGRES_USER=maitai\nnot-an-assignment\n")
        assert bundle.env_values() == {"POSTGRES_USER": "maitai"}

    def test_values_may_contain_equals_signs(self, repo):
        write_env(repo, "SECRET_KEY=abc=def==\n")
        assert bundle.env_values()["SECRET_KEY"] == "abc=def=="

    def test_last_assignment_wins(self, repo):
        # Matches how docker-compose reads the file; picking the first would
        # fingerprint a key the stack isn't actually using.
        write_env(repo, "SECRET_KEY=old\nSECRET_KEY=new\n")
        assert bundle.env_values()["SECRET_KEY"] == "new"

    def test_missing_file_is_empty_not_an_error(self, repo):
        assert bundle.env_values() == {}


class TestCryptoFingerprint:
    def test_encryption_key_wins_over_secret_key(self):
        both = {"ENCRYPTION_KEY": "e", "SECRET_KEY": "s"}
        assert bundle.crypto_fingerprint(both) == bundle.crypto_fingerprint({"ENCRYPTION_KEY": "e"})
        assert bundle.crypto_fingerprint(both) != bundle.crypto_fingerprint({"SECRET_KEY": "s"})

    def test_same_value_under_different_keys_is_a_different_fingerprint(self):
        # The prefix matters: ENCRYPTION_KEY=x and SECRET_KEY=x produce different
        # Fernet keys, so they must not compare equal at import time.
        assert bundle.crypto_fingerprint({"ENCRYPTION_KEY": "x"}) != bundle.crypto_fingerprint(
            {"SECRET_KEY": "x"}
        )

    def test_no_keys_is_unknown(self):
        assert bundle.crypto_fingerprint({}) == "unknown"

    def test_fingerprint_does_not_contain_the_secret(self):
        secret = "super-secret-value"
        assert secret not in bundle.crypto_fingerprint({"SECRET_KEY": secret})


class TestEnvTemplate:
    VALUES = {
        "SECRET_KEY": "live-secret",
        "POSTGRES_PASSWORD": "live-password",
        "CLOUD_ML_REGION": "us-east5",
        "GITHUB_CLIENT_SECRET": "live-oauth-secret",
        "ENCRYPTION_KEY": "live-encryption-key",
    }

    def test_operational_values_are_carried_through(self):
        assert "CLOUD_ML_REGION=us-east5" in bundle.env_template("host", self.VALUES)

    def test_required_keys_are_listed_but_blank(self):
        template = bundle.env_template("host", self.VALUES)
        for key in bundle.REQUIRED_ENV_KEYS:
            assert f"{key}=\n" in template

    def test_no_credential_value_reaches_the_template(self):
        # env.template is the file an operator will happily paste into a ticket.
        template = bundle.env_template("host", self.VALUES)
        for secret in ("live-secret", "live-password", "live-oauth-secret", "live-encryption-key"):
            assert secret not in template

    def test_every_known_key_appears(self):
        template = bundle.env_template("host", {})
        for key in (*bundle.REQUIRED_ENV_KEYS, *bundle.OPTIONAL_ENV_KEYS):
            assert f"{key}=" in template


class TestManifest:
    def test_round_trips(self):
        original = bundle.Manifest(source_host="dev", counts={"users": 2})
        assert bundle.Manifest.from_json(original.to_json()) == original

    def test_unknown_fields_are_dropped_not_fatal(self):
        parsed = bundle.Manifest.from_json('{"source_host": "dev", "future_field": 1}')
        assert parsed.source_host == "dev"

    def test_garbage_falls_back_to_defaults(self):
        # An unreadable manifest must not block a restore; database.sql is the
        # part that matters and it is checked separately.
        assert bundle.Manifest.from_json("not json at all").bundle_version == bundle.BUNDLE_VERSION

    def test_missing_schedule_count_is_none_not_zero(self):
        # A v2 bundle from the shell script has no schedules_enabled key. "We
        # don't know" and "there are none" call for different warnings.
        assert bundle.Manifest(counts={"users": 1}).enabled_schedules is None
        assert bundle.Manifest(counts={"schedules_enabled": 0}).enabled_schedules == 0
        assert bundle.Manifest(counts={"schedules_enabled": 3}).enabled_schedules == 3


class TestVersionGate:
    def test_current_and_older_formats_are_accepted(self):
        bundle.check_version(bundle.Manifest(bundle_version=bundle.BUNDLE_VERSION))
        bundle.check_version(bundle.Manifest(bundle_version=1))

    def test_newer_format_is_refused(self):
        with pytest.raises(ProbeError, match="newer than this CLI"):
            bundle.check_version(bundle.Manifest(bundle_version=bundle.BUNDLE_VERSION + 1))


class TestFingerprintWarning:
    def test_matching_keys_are_silent(self):
        manifest = bundle.Manifest(crypto_fingerprint="abc123")
        assert bundle.fingerprint_warning(manifest, local="abc123") is None

    def test_mismatch_names_both_sides(self):
        manifest = bundle.Manifest(crypto_fingerprint="source99")
        warning = bundle.fingerprint_warning(manifest, local="target11")
        assert warning is not None
        assert "source99" in warning and "target11" in warning

    def test_unknown_source_key_does_not_warn(self):
        # The source simply had no .env to read. Nothing useful to say.
        assert bundle.fingerprint_warning(bundle.Manifest(), local="target11") is None


def make_bundle(path: Path, stage: Path, manifest: bundle.Manifest, extra: list[str] | None = None):
    """Build a real tar.gz the way export does, plus any extra member names."""
    stage.mkdir(parents=True, exist_ok=True)
    (stage / "manifest.json").write_text(manifest.to_json())
    (stage / "database.sql").write_text("-- dump\n")
    (stage / "env.template").write_text("SECRET_KEY=\n")
    members = ["manifest.json", "database.sql", "env.template"]
    bundle.write_bundle(path, stage, members)
    if extra:
        # Re-pack, appending members with arbitrary (possibly hostile) names.
        with tarfile.open(path, "w:gz") as tar:
            for name in members:
                tar.add(stage / name, arcname=name)
            for name in extra:
                tar.add(stage / "database.sql", arcname=name)
    return path


class TestUnpack:
    def test_round_trips_a_real_bundle(self, tmp_path):
        made = make_bundle(
            tmp_path / "b.tar.gz",
            tmp_path / "stage",
            bundle.Manifest(source_host="dev", counts={"users": 2}),
        )
        manifest, notes = bundle.unpack(made, tmp_path / "out")
        assert manifest.source_host == "dev"
        assert manifest.counts == {"users": 2}
        assert (tmp_path / "out/database.sql").read_text() == "-- dump\n"
        assert notes == []

    def test_traversal_member_is_never_written(self, tmp_path):
        made = make_bundle(
            tmp_path / "b.tar.gz",
            tmp_path / "stage",
            bundle.Manifest(),
            extra=["../escaped.sql"],
        )
        _, notes = bundle.unpack(made, tmp_path / "out")
        assert not (tmp_path / "escaped.sql").exists()
        assert any("escaped.sql" in note for note in notes)

    def test_unexpected_member_is_reported_not_unpacked(self, tmp_path):
        made = make_bundle(
            tmp_path / "b.tar.gz", tmp_path / "stage", bundle.Manifest(), extra=["surprise.sh"]
        )
        _, notes = bundle.unpack(made, tmp_path / "out")
        assert not (tmp_path / "out/surprise.sh").exists()
        assert any("surprise.sh" in note for note in notes)

    def test_missing_bundle_is_a_clear_error(self, tmp_path):
        with pytest.raises(ProbeError, match="no such bundle"):
            bundle.unpack(tmp_path / "nope.tar.gz", tmp_path / "out")

    def test_a_non_tarball_is_a_clear_error(self, tmp_path):
        junk = tmp_path / "junk.tar.gz"
        junk.write_text("this is not a tarball")
        with pytest.raises(ProbeError, match="not a readable bundle"):
            bundle.unpack(junk, tmp_path / "out")

    def test_bundle_with_no_manifest_still_unpacks(self, tmp_path):
        stage = tmp_path / "stage"
        stage.mkdir()
        (stage / "database.sql").write_text("-- dump\n")
        bundle.write_bundle(tmp_path / "b.tar.gz", stage, ["database.sql"])
        manifest, _ = bundle.unpack(tmp_path / "b.tar.gz", tmp_path / "out")
        assert manifest.bundle_version == bundle.BUNDLE_VERSION


class TestBundlePermissions:
    def test_archive_is_created_private(self, tmp_path):
        stage = tmp_path / "stage"
        stage.mkdir()
        (stage / "database.sql").write_text("-- dump\n")
        out = tmp_path / "b.tar.gz"
        bundle.write_bundle(out, stage, ["database.sql"])
        assert out.stat().st_mode & 0o777 == 0o600

    def test_overwriting_an_existing_world_readable_file_still_ends_private(self, tmp_path):
        out = tmp_path / "b.tar.gz"
        out.write_text("stale")
        out.chmod(0o644)
        stage = tmp_path / "stage"
        stage.mkdir()
        (stage / "database.sql").write_text("-- dump\n")
        bundle.write_bundle(out, stage, ["database.sql"])
        assert out.stat().st_mode & 0o777 == 0o600


class TestScrubSql:
    def test_every_secret_key_is_removed(self):
        sql = bundle.scrub_sql()
        for key in bundle.SECRET_SETTINGS_KEYS:
            assert f"- '{key}'" in sql

    def test_the_residue_check_looks_for_every_key(self):
        sql = bundle.residue_sql()
        for key in bundle.SECRET_SETTINGS_KEYS:
            assert f"'{key}'" in sql

    def test_scratch_database_is_not_the_live_one(self):
        assert bundle.SCRATCH_DB != probes.PG_DB


class TestSecretScan:
    def scan(self, tmp_path, body: str) -> dict[str, int]:
        dump = tmp_path / "database.sql"
        dump.write_text(body)
        return bundle.scan_for_secrets(dump)

    def test_finds_an_anthropic_key_pasted_into_chat(self, tmp_path):
        body = "here's the key man: sk-ant-api03-" + "A" * 40 + "\n"
        assert self.scan(tmp_path, body) == {"Anthropic API key": 1}

    def test_finds_a_github_token(self, tmp_path):
        assert self.scan(tmp_path, "ghp_" + "b" * 36) == {"GitHub token": 1}

    def test_finds_a_private_key_block(self, tmp_path):
        assert self.scan(tmp_path, "-----BEGIN OPENSSH PRIVATE KEY-----\n") == {
            "private key block": 1
        }

    def test_counts_repeats(self, tmp_path):
        line = "ghp_" + "c" * 36
        assert self.scan(tmp_path, f"{line}\n{line}\n")["GitHub token"] == 2

    def test_prose_about_credentials_is_not_a_hit(self, tmp_path):
        # The scrubbed dump is full of bots saying "anthropic_api_key". Flagging
        # the word would make the warning noise and it would get ignored.
        body = "You never filled in anthropic_api_key or github_token in Settings > AI.\n"
        assert self.scan(tmp_path, body) == {}

    def test_a_clean_dump_reports_nothing(self, tmp_path):
        assert self.scan(tmp_path, "COPY messages (id, content) FROM stdin;\nhello\n") == {}

    def test_undecodable_bytes_do_not_crash_the_scan(self, tmp_path):
        # Dumps carry arbitrary message content, including broken encodings.
        dump = tmp_path / "database.sql"
        dump.write_bytes(b"\xff\xfe binary junk\nghp_" + b"d" * 36 + b"\n")
        assert bundle.scan_for_secrets(dump) == {"GitHub token": 1}

    def test_the_scan_never_returns_the_secret(self, tmp_path):
        secret = "ghp_" + "e" * 36
        assert secret not in str(self.scan(tmp_path, secret))


class FakePg:
    """Stands in for the postgres container.

    Records every psql/dropdb/createdb the code runs so a test can assert on
    ordering — the scrub path is only safe if the scratch DB is dropped no
    matter how the export ends.
    """

    def __init__(self, monkeypatch, *, residue="0", counts=None):
        self.calls: list[list[str]] = []
        self.dumped: list[str] = []
        self.residue = residue
        self.counts = counts or {"users": 1, "workspaces": 2, "schedules_enabled": 0}
        monkeypatch.setattr(bundle, "require_pg", lambda: None)
        monkeypatch.setattr(bundle, "_pg_exec", self.pg_exec)
        monkeypatch.setattr(bundle, "query", self.query)
        monkeypatch.setattr(bundle, "_pg_dump_to", self.dump)

    def pg_exec(self, args, timeout=120):
        self.calls.append(list(args))
        return ""

    def query(self, sql, database=None):
        self.calls.append(["query", sql, database or ""])
        if "alembic_version" in sql:
            return "a1b2c3"
        if "settings ?|" in sql:
            return self.residue
        if "json_build_object" in sql:
            return json.dumps(self.counts)
        return "0"

    def dump(self, dest, database):
        self.dumped.append(database)
        Path(dest).write_text(f"-- dump of {database}\n")


class TestExport:
    def test_plain_export_packs_three_members(self, tmp_path, repo, monkeypatch):
        FakePg(monkeypatch)
        out = tmp_path / "b.tar.gz"
        manifest, notes, _ = bundle.export_bundle(out, stage=tmp_path / "stage")
        with tarfile.open(out) as tar:
            assert sorted(tar.getnames()) == ["database.sql", "env.template", "manifest.json"]
        assert manifest.contains_secrets is True
        assert manifest.includes_env is False
        assert manifest.alembic_revision == "a1b2c3"
        assert notes == []

    def test_scrubbed_export_dumps_the_scratch_copy(self, tmp_path, repo, monkeypatch):
        pg = FakePg(monkeypatch)
        manifest, *_ = bundle.export_bundle(
            tmp_path / "b.tar.gz", stage=tmp_path / "stage", scrub=True
        )
        assert pg.dumped == [bundle.SCRATCH_DB]
        assert manifest.contains_secrets is False

    def test_scrubbed_export_always_drops_the_scratch_database(self, tmp_path, repo, monkeypatch):
        pg = FakePg(monkeypatch)
        bundle.export_bundle(tmp_path / "b.tar.gz", stage=tmp_path / "stage", scrub=True)
        drops = [c for c in pg.calls if c and c[0] == "dropdb"]
        assert len(drops) == 2  # once before creating it, once after dumping

    def test_a_failed_scrub_still_drops_the_scratch_database(self, tmp_path, repo, monkeypatch):
        # Left behind, it holds unscrubbed live data under a name nobody would
        # think to look at.
        pg = FakePg(monkeypatch, residue="3")
        with pytest.raises(ProbeError, match="scrub did not take"):
            bundle.export_bundle(tmp_path / "b.tar.gz", stage=tmp_path / "stage", scrub=True)
        assert [c for c in pg.calls if c and c[0] == "dropdb"]

    def test_a_failed_scrub_writes_no_bundle(self, tmp_path, repo, monkeypatch):
        FakePg(monkeypatch, residue="3")
        out = tmp_path / "b.tar.gz"
        with pytest.raises(ProbeError):
            bundle.export_bundle(out, stage=tmp_path / "stage", scrub=True)
        assert not out.exists()

    def test_with_env_includes_and_records_it(self, tmp_path, repo, monkeypatch):
        FakePg(monkeypatch)
        write_env(repo, "SECRET_KEY=s\n")
        out = tmp_path / "b.tar.gz"
        manifest, *_ = bundle.export_bundle(out, stage=tmp_path / "stage", with_env=True)
        with tarfile.open(out) as tar:
            assert "env" in tar.getnames()
        assert manifest.includes_env is True

    def test_with_env_and_no_env_file_warns_instead_of_failing(self, tmp_path, repo, monkeypatch):
        FakePg(monkeypatch)
        out = tmp_path / "b.tar.gz"
        manifest, notes, _ = bundle.export_bundle(out, stage=tmp_path / "stage", with_env=True)
        assert manifest.includes_env is False
        assert any("no .env" in note for note in notes)
        with tarfile.open(out) as tar:
            assert "env" not in tar.getnames()

    def test_env_is_never_bundled_by_default(self, tmp_path, repo, monkeypatch):
        FakePg(monkeypatch)
        write_env(repo, "SECRET_KEY=s\n")
        out = tmp_path / "b.tar.gz"
        bundle.export_bundle(out, stage=tmp_path / "stage")
        with tarfile.open(out) as tar:
            assert "env" not in tar.getnames()


class TestPlaceImportedEnv:
    def test_never_overwrites_the_live_env(self, tmp_path, repo):
        write_env(repo, "SECRET_KEY=mine\n")
        stage = tmp_path / "stage"
        stage.mkdir()
        (stage / "env").write_text("SECRET_KEY=theirs\n")
        dest = bundle.place_imported_env(stage)
        assert dest == repo / ".env.imported"
        assert (repo / ".env").read_text() == "SECRET_KEY=mine\n"

    def test_lands_private(self, tmp_path, repo):
        stage = tmp_path / "stage"
        stage.mkdir()
        (stage / "env").write_text("SECRET_KEY=theirs\n")
        # A world-readable source must not carry its mode across.
        (stage / "env").chmod(0o644)
        dest = bundle.place_imported_env(stage)
        assert dest.stat().st_mode & 0o777 == 0o600

    def test_no_bundled_env_is_a_no_op(self, tmp_path, repo):
        stage = tmp_path / "stage"
        stage.mkdir()
        assert bundle.place_imported_env(stage) is None


class TestCheckEnv:
    def test_missing_file_is_an_error(self, repo):
        with pytest.raises(ProbeError, match="no .env at"):
            bundle.check_env()

    def test_reports_required_and_optional_separately(self, repo):
        write_env(repo, "POSTGRES_USER=maitai\nCLOUD_ML_REGION=us-east5\n")
        results = {check.key: check for check in bundle.check_env()}
        assert results["POSTGRES_USER"].present and results["POSTGRES_USER"].required
        assert not results["SECRET_KEY"].present and results["SECRET_KEY"].required
        assert results["CLOUD_ML_REGION"].present and not results["CLOUD_ML_REGION"].required

    def test_an_empty_value_counts_as_missing(self, repo):
        # `SECRET_KEY=` in a .env is the classic half-copied file, and the stack
        # comes up far enough to look fine.
        write_env(repo, "SECRET_KEY=\n")
        results = {check.key: check for check in bundle.check_env()}
        assert not results["SECRET_KEY"].present


class TestCheckEnvCommand:
    def test_exits_one_when_a_required_key_is_missing(self, repo):
        write_env(repo, "POSTGRES_USER=maitai\n")
        result = runner.invoke(cli.app, ["config", "check-env"])
        assert result.exit_code == 1
        assert "SECRET_KEY" in result.output

    def test_exits_zero_when_complete(self, repo):
        write_env(repo, "".join(f"{key}=x\n" for key in bundle.REQUIRED_ENV_KEYS))
        result = runner.invoke(cli.app, ["config", "check-env"])
        assert result.exit_code == 0
        assert "All required keys present" in result.output


class TestImportCommand:
    @pytest.fixture
    def staged(self, tmp_path, repo, monkeypatch):
        """A restorable bundle, with every destructive call stubbed out."""
        made = make_bundle(
            tmp_path / "b.tar.gz",
            tmp_path / "stage",
            bundle.Manifest(source_host="dev", counts={"users": 1, "schedules_enabled": 4}),
        )
        self.restored: list[Path] = []
        self.disabled = 0
        monkeypatch.setattr(bundle, "require_pg", lambda: None)
        monkeypatch.setattr(bundle, "restore", lambda stage: self.restored.append(stage))
        monkeypatch.setattr(bundle, "disable_all_schedules", self._disable)
        monkeypatch.setattr(probes, "psql", lambda sql: [["7"]])
        return made

    def _disable(self):
        self.disabled = 4
        return 4

    def test_typing_anything_else_changes_nothing(self, staged):
        result = runner.invoke(cli.app, ["config", "import", str(staged)], input="yes\n")
        assert result.exit_code == 0
        assert self.restored == []
        assert "Nothing changed" in result.output

    def test_no_stdin_aborts_rather_than_wiping(self, staged):
        # cron and CI have no tty. Failing closed is the whole point.
        result = runner.invoke(cli.app, ["config", "import", str(staged)], input="")
        assert result.exit_code == 1
        assert self.restored == []

    def test_typing_replace_restores(self, staged):
        result = runner.invoke(cli.app, ["config", "import", str(staged)], input="replace\n")
        assert result.exit_code == 0
        assert len(self.restored) == 1
        assert "Import complete" in result.output

    def test_the_existing_workspace_count_is_shown_before_the_prompt(self, staged):
        result = runner.invoke(cli.app, ["config", "import", str(staged)], input="no\n")
        assert "7 workspace(s)" in result.output

    def test_enabled_schedules_in_the_bundle_are_called_out(self, staged):
        # A restored clone otherwise starts firing real work on the next tick.
        result = runner.invoke(cli.app, ["config", "import", str(staged)], input="no\n")
        assert "4 ENABLED schedule" in result.output
        assert "--disable-schedules" in result.output

    def test_disable_schedules_turns_them_off_after_restoring(self, staged):
        result = runner.invoke(
            cli.app, ["config", "import", str(staged), "--disable-schedules"], input="replace\n"
        )
        assert result.exit_code == 0
        assert self.disabled == 4
        assert "disabled 4 schedule" in result.output

    def test_disable_schedules_suppresses_the_warning(self, staged):
        result = runner.invoke(
            cli.app, ["config", "import", str(staged), "--disable-schedules"], input="no\n"
        )
        assert "ENABLED schedule" not in result.output

    def test_a_newer_bundle_is_refused_before_the_prompt(self, tmp_path, repo, monkeypatch):
        made = make_bundle(
            tmp_path / "b.tar.gz",
            tmp_path / "stage",
            bundle.Manifest(bundle_version=bundle.BUNDLE_VERSION + 1),
        )
        called = []
        monkeypatch.setattr(bundle, "require_pg", lambda: None)
        monkeypatch.setattr(bundle, "restore", lambda stage: called.append(stage))
        result = runner.invoke(cli.app, ["config", "import", str(made)], input="replace\n")
        assert result.exit_code == 2
        assert called == []

    def test_a_missing_bundle_exits_cleanly(self, tmp_path, repo):
        result = runner.invoke(cli.app, ["config", "import", str(tmp_path / "nope.tar.gz")])
        assert result.exit_code == 2


class TestInspectCommand:
    def test_flags_a_bundle_that_carries_credentials(self, tmp_path, repo):
        made = make_bundle(
            tmp_path / "b.tar.gz",
            tmp_path / "stage",
            bundle.Manifest(contains_secrets=True, counts={"users": 3}),
        )
        result = runner.invoke(cli.app, ["config", "inspect", str(made)])
        assert result.exit_code == 0
        assert "credential material" in result.output
        assert "users" in result.output

    def test_marks_a_scrubbed_bundle_as_scrubbed(self, tmp_path, repo):
        made = make_bundle(
            tmp_path / "b.tar.gz", tmp_path / "stage", bundle.Manifest(contains_secrets=False)
        )
        result = runner.invoke(cli.app, ["config", "inspect", str(made)])
        assert "scrubbed" in result.output

    def test_inspect_restores_nothing(self, tmp_path, repo, monkeypatch):
        called = []
        monkeypatch.setattr(bundle, "restore", lambda stage: called.append(stage))
        made = make_bundle(tmp_path / "b.tar.gz", tmp_path / "stage", bundle.Manifest())
        runner.invoke(cli.app, ["config", "inspect", str(made)])
        assert called == []


class TestStaging:
    def test_the_scratch_directory_is_removed(self):
        with cli._staging() as stage:
            (stage / "database.sql").write_text("-- secrets\n")
            path = stage
        assert not path.exists()

    def test_it_is_removed_even_when_the_body_raises(self):
        path = None
        with pytest.raises(RuntimeError), cli._staging() as stage:
            path = stage
            raise RuntimeError("boom")
        assert path is not None and not path.exists()

    def test_it_is_not_world_readable(self):
        with cli._staging() as stage:
            assert stage.stat().st_mode & 0o077 == 0
