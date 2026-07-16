"""Curated memory + journal file operations."""

from datetime import date

import pytest

from mai_tai_mcp import memory as m


@pytest.fixture
def mem_dir(tmp_path):
    return tmp_path / "memory"


def test_add_and_read(mem_dir):
    assert m.memory_add(mem_dir, "User prefers dark mode")["status"] == "ok"
    assert m.memory_add(mem_dir, "Deploys happen on Fridays")["status"] == "ok"
    content = m.read_memory(mem_dir)
    assert "dark mode" in content and "Fridays" in content


def test_cap_enforced_with_consolidation_hint(mem_dir):
    result = m.memory_add(mem_dir, "x" * (m.MEMORY_CHAR_LIMIT + 1))
    assert result["status"] == "error"
    assert "Consolidate" in result["error"]
    assert m.read_memory(mem_dir) == ""  # nothing written


def test_replace_by_substring(mem_dir):
    m.memory_add(mem_dir, "User prefers dark mode")
    result = m.memory_replace(mem_dir, "dark mode", "User prefers light mode")
    assert result["status"] == "ok"
    assert "light mode" in m.read_memory(mem_dir)
    assert "dark mode" not in m.read_memory(mem_dir)


def test_replace_missing_substring_errors(mem_dir):
    m.memory_add(mem_dir, "something")
    assert m.memory_replace(mem_dir, "not-there", "x")["status"] == "error"


def test_replace_respects_cap(mem_dir):
    m.memory_add(mem_dir, "short entry")
    result = m.memory_replace(mem_dir, "short entry", "y" * (m.MEMORY_CHAR_LIMIT + 1))
    assert result["status"] == "error"
    assert "short entry" in m.read_memory(mem_dir)  # unchanged


def test_remove(mem_dir):
    m.memory_add(mem_dir, "keep this")
    m.memory_add(mem_dir, "remove this")
    assert m.memory_remove(mem_dir, "remove this")["status"] == "ok"
    content = m.read_memory(mem_dir)
    assert "keep this" in content and "remove this" not in content


def test_journal_append_timestamped(mem_dir):
    assert m.journal_append(mem_dir, "fixed the websocket bug")["status"] == "ok"
    f = mem_dir / "journal" / f"{date.today().isoformat()}.md"
    content = f.read_text()
    assert "fixed the websocket bug" in content
    assert content.startswith("- [")  # timestamp prefix


def test_journal_entry_cap(mem_dir):
    result = m.journal_append(mem_dir, "x" * (m.JOURNAL_ENTRY_CHAR_LIMIT + 1))
    assert result["status"] == "error"


def test_session_context_assembly(mem_dir):
    m.memory_add(mem_dir, "User prefers light mode")
    m.journal_append(mem_dir, "started the caddy migration")
    lessons = mem_dir / "tasks"
    lessons.mkdir(parents=True)
    (lessons / "lessons.md").write_text("- LESSON: always run tests\n")

    ctx = m.build_session_context(mem_dir)
    assert "light mode" in ctx
    assert "caddy migration" in ctx
    assert "always run tests" in ctx


def test_session_context_empty(tmp_path):
    assert m.build_session_context(tmp_path / "nothing") == "(no persistent memory yet)"


def test_resolve_memory_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("MAI_TAI_MEMORY_DIR", str(tmp_path / "vol"))
    assert m.resolve_memory_dir("abc") == tmp_path / "vol"
    monkeypatch.delenv("MAI_TAI_MEMORY_DIR")
    assert str(m.resolve_memory_dir("abc")).endswith("mai-tai/memory/abc")
