"""Unit tests for the agent driver's pure logic (no docker, no network)."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

DRIVER_PATH = Path(__file__).parent.parent / "common" / "driver.py"


@pytest.fixture
def driver(tmp_path, monkeypatch):
    """Import driver.py with a sandboxed environment."""
    monkeypatch.setenv("MAI_TAI_API_URL", "http://backend:8000")
    monkeypatch.setenv("MAI_TAI_API_KEY", "mt_test")
    monkeypatch.setenv("MAI_TAI_WORKSPACE_ID", "ws-123")
    monkeypatch.setenv("MAI_TAI_MEMORY_DIR", str(tmp_path / "memory"))
    monkeypatch.setenv("AGENT_WORKDIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("AGENT_MODEL", "opus")

    spec = importlib.util.spec_from_file_location("driver", DRIVER_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["driver"] = mod
    spec.loader.exec_module(mod)
    yield mod
    del sys.modules["driver"]


def test_parse_turn_output_extracts_result_and_session(driver):
    stdout = json.dumps(
        {"type": "result", "result": "All done!", "session_id": "sess-1", "is_error": False}
    )
    result, session_id = driver.parse_turn_output(stdout)
    assert result == "All done!"
    assert session_id == "sess-1"


def test_parse_turn_output_skips_noise_lines(driver):
    stdout = "some log line\n" + json.dumps({"result": "ok", "session_id": "s2"}) + "\ntrailing"
    result, session_id = driver.parse_turn_output(stdout)
    assert result == "ok"
    assert session_id == "s2"


def test_parse_turn_output_garbage_returns_none(driver):
    result, session_id = driver.parse_turn_output("not json at all")
    assert result is None and session_id is None


def test_build_turn_cmd_claude_code(driver):
    cmd = driver.build_turn_cmd("hello", None)
    assert cmd[0] == "claude"
    assert "--resume" not in cmd
    assert cmd[cmd.index("--model") + 1] == "opus"

    cmd = driver.build_turn_cmd("hello", "sess-9")
    assert cmd[cmd.index("--resume") + 1] == "sess-9"


def test_build_turn_cmd_codex(driver, monkeypatch):
    monkeypatch.setattr(driver, "AGENT_RUNTIME", "codex")
    assert driver.build_turn_cmd("hello", None) == ["codex", "exec", "hello"]
    assert driver.build_turn_cmd("more", "last") == ["codex", "exec", "resume", "--last", "more"]


def test_parse_turn_output_codex_stdout_verbatim(driver, monkeypatch):
    monkeypatch.setattr(driver, "AGENT_RUNTIME", "codex")
    result, session_id = driver.parse_turn_output("Here is my final answer.\n")
    assert result == "Here is my final answer."
    assert session_id == "last"

    result, session_id = driver.parse_turn_output("   \n")
    assert result is None


def test_build_turn_cmd_unknown_runtime(driver, monkeypatch):
    monkeypatch.setattr(driver, "AGENT_RUNTIME", "gemini-cli")
    with pytest.raises(RuntimeError):
        driver.build_turn_cmd("hello", None)


def test_state_roundtrip(driver):
    state = {"session_id": "sess-3", "turns": 7}
    driver.save_state(state)
    assert driver.load_state() == state


def test_state_missing_file_defaults(driver):
    assert driver.load_state() == {"session_id": None, "turns": 0}


def test_memory_context_assembly(driver):
    mem = driver.MEMORY_DIR
    mem.mkdir(parents=True)
    (mem / "MEMORY.md").write_text("User prefers light mode\n")
    (mem / "journal").mkdir()
    (mem / "journal" / "2026-07-15.md").write_text("- [09:00] started caddy migration\n")
    (mem / "tasks").mkdir()
    (mem / "tasks" / "lessons.md").write_text("- LESSON: always run tests\n")

    ctx = driver.build_memory_context()
    assert "light mode" in ctx
    assert "caddy migration" in ctx
    assert "always run tests" in ctx

    preamble = driver.session_start_preamble()
    assert preamble.startswith("[NEW SESSION]")
    assert "light mode" in preamble


def test_memory_context_empty(driver):
    assert driver.build_memory_context() == "(no persistent memory yet)"
