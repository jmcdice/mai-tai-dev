"""The package version has exactly one source of truth.

It used to have two — a literal in `__init__.py` and the real one in
pyproject.toml — and they drifted on the very first release after the literal
was added. The number surfaces in the config-error banner, so a stale one costs
somebody an evening debugging a build they aren't running.
"""

import tomllib
from pathlib import Path

import mai_tai_mcp

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_version_matches_pyproject():
    declared = tomllib.loads(PYPROJECT.read_text())["project"]["version"]
    assert mai_tai_mcp.__version__ == declared, (
        f"__version__ is {mai_tai_mcp.__version__} but pyproject says {declared}. "
        "If these disagree, the installed build is stale — reinstall rather than "
        "hardcoding the number back into __init__.py."
    )


def test_version_is_not_the_source_tree_placeholder():
    """Guards the fallback: importable-but-not-installed reports 0.0.0+source,
    which is honest but useless in a bug report. Under test the package is
    installed, so seeing it here means packaging metadata went missing."""
    assert mai_tai_mcp.__version__ != "0.0.0+source"
