"""Unit tests for scripts/claude-trust-folder.py.

The script lives in scripts/ because the supervisor calls it, but it is tested
from here because cli/tests is what CI actually runs. It is loaded by path
since its filename has a hyphen and cannot be imported normally.

What matters about this script is not that it sets a flag — it is that it
edits ~/.claude.json, a file every Claude process on the box rewrites from its
own in-memory copy. So the tests are mostly about restraint: don't write when
there is nothing to change, don't lose the other keys, don't leave a torn file
or a stray temp behind, and never fail in a way that stops a bot from booting.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "claude-trust-folder.py"


def load(config: Path):
    """Fresh module instance pointed at a throwaway config file."""
    os.environ["CLAUDE_CONFIG_JSON"] = str(config)
    spec = importlib.util.spec_from_file_location("claude_trust_folder", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def config(tmp_path):
    return tmp_path / ".claude.json"


def write(config: Path, data: dict) -> None:
    config.write_text(json.dumps(data))
    config.chmod(0o600)


def read(config: Path) -> dict:
    return json.loads(config.read_text())


class TestSetsTheFlag:
    def test_flips_false_to_true(self, config):
        write(config, {"projects": {"/repos/rando": {"hasTrustDialogAccepted": False}}})
        assert load(config).main(["/repos/rando"]) == 0
        assert read(config)["projects"]["/repos/rando"]["hasTrustDialogAccepted"] is True

    def test_creates_an_entry_for_an_unseen_repo(self, config):
        write(config, {"projects": {}})
        assert load(config).main(["/repos/brand-new"]) == 0
        assert read(config)["projects"]["/repos/brand-new"] == {"hasTrustDialogAccepted": True}

    def test_accepts_several_repos_at_once(self, config):
        write(config, {"projects": {}})
        load(config).main(["/repos/a", "/repos/b"])
        projects = read(config)["projects"]
        assert projects["/repos/a"]["hasTrustDialogAccepted"] is True
        assert projects["/repos/b"]["hasTrustDialogAccepted"] is True

    def test_normalises_the_path_to_the_key_claude_uses(self, config, tmp_path):
        """Claude keys projects by the resolved cwd, so a trailing slash or a
        '..' in the supervisor's argument must not create a second entry."""
        real = tmp_path / "repo"
        real.mkdir()
        write(config, {"projects": {}})
        load(config).main([f"{real}/sub/.."])
        assert list(read(config)["projects"]) == [str(real)]


class TestRestraint:
    def test_already_trusted_does_not_touch_the_file(self, config):
        """The common case. Every rewrite is a chance to clobber another
        process's state, so the steady state must be a pure no-op."""
        write(config, {"projects": {"/repos/rando": {"hasTrustDialogAccepted": True}}})
        before = config.stat().st_mtime_ns
        assert load(config).main(["/repos/rando"]) == 0
        assert config.stat().st_mtime_ns == before

    def test_preserves_every_other_key(self, config):
        write(
            config,
            {
                "numStartups": 42,
                "oauthAccount": {"emailAddress": "joey@example.com"},
                "projects": {
                    "/repos/rando": {"hasTrustDialogAccepted": False, "allowedTools": ["Bash"]},
                    "/repos/folio": {"hasTrustDialogAccepted": True, "history": [1, 2]},
                },
            },
        )
        load(config).main(["/repos/rando"])
        data = read(config)
        assert data["numStartups"] == 42
        assert data["oauthAccount"] == {"emailAddress": "joey@example.com"}
        assert data["projects"]["/repos/rando"]["allowedTools"] == ["Bash"]
        assert data["projects"]["/repos/folio"] == {"hasTrustDialogAccepted": True, "history": [1, 2]}

    def test_keeps_the_file_mode(self, config):
        write(config, {"projects": {"/repos/rando": {"hasTrustDialogAccepted": False}}})
        config.chmod(0o600)
        load(config).main(["/repos/rando"])
        assert config.stat().st_mode & 0o777 == 0o600

    def test_keeps_a_backup_of_what_it_replaced(self, config):
        write(config, {"projects": {"/repos/rando": {"hasTrustDialogAccepted": False}}})
        module = load(config)
        module.main(["/repos/rando"])
        assert json.loads(module.BACKUP.read_text())["projects"]["/repos/rando"][
            "hasTrustDialogAccepted"
        ] is False

    def test_leaves_no_temp_files(self, config, tmp_path):
        write(config, {"projects": {}})
        load(config).main(["/repos/rando"])
        strays = [p.name for p in tmp_path.iterdir() if ".mai-tai." in p.name and "bak" not in p.name]
        assert strays == []


class TestNeverBlocksABoot:
    """A trust preflight that fails a bot's launch is worse than the dialog it
    prevents, so every recoverable problem exits 0 and changes nothing."""

    def test_missing_config_is_a_skip(self, config):
        assert load(config).main(["/repos/rando"]) == 0
        assert not config.exists()

    def test_corrupt_json_is_a_skip(self, config):
        config.write_text("{ this is not json")
        assert load(config).main(["/repos/rando"]) == 0
        assert config.read_text() == "{ this is not json"

    def test_config_that_is_not_an_object_is_a_skip(self, config):
        config.write_text("[1, 2, 3]")
        assert load(config).main(["/repos/rando"]) == 0
        assert config.read_text() == "[1, 2, 3]"

    def test_projects_that_is_not_an_object_is_a_skip(self, config):
        config.write_text(json.dumps({"projects": ["nope"]}))
        assert load(config).main(["/repos/rando"]) == 0
        assert read(config) == {"projects": ["nope"]}

    def test_project_entry_of_the_wrong_shape_is_replaced_not_crashed(self, config):
        write(config, {"projects": {"/repos/rando": "somehow a string"}})
        assert load(config).main(["/repos/rando"]) == 0
        assert read(config)["projects"]["/repos/rando"] == {"hasTrustDialogAccepted": True}

    def test_unwritable_config_is_a_skip(self, config, tmp_path):
        write(config, {"projects": {"/repos/rando": {"hasTrustDialogAccepted": False}}})
        tmp_path.chmod(0o500)  # can't create the temp file next to it
        try:
            assert load(config).main(["/repos/rando"]) == 0
        finally:
            tmp_path.chmod(0o700)

    def test_no_arguments_is_a_usage_error(self, config):
        assert load(config).main([]) == 2
