"""Runtime auth resolution — the shared path both agent-start callers use.

Regression cover for a Vertex-only deployment: users there store no
credential at all, and a caller that resolved credentials on its own (the
scheduler's wake path did) would silently decide the agent couldn't start.

Fixture values below are deliberately not credential-shaped. Realistic dummies
train secret scanners to cry wolf, and a repo whose scanner is always red is a
repo where nobody reads the scanner.
"""

import json

import pytest

from app.core.crypto import encrypt_value
from app.services.agents import RUNTIMES, resolve_auth_env
from app.services.agents import spawner
from app.services.agents.spawner import OAUTH_TOKEN_PREFIX

CLAUDE = RUNTIMES["claude-code"]
CODEX = RUNTIMES["codex"]

ADC_JSON = json.dumps({"type": "authorized_user", "refresh_token": "placeholder"})
STORED_API_KEY = "placeholder-anthropic-key"
STORED_OAUTH_TOKEN = f"{OAUTH_TOKEN_PREFIX}-placeholder"
STORED_OPENAI_KEY = "placeholder-openai-key"


@pytest.fixture
def vertex_host(monkeypatch, tmp_path):
    """A host configured for Vertex, with readable ADC on disk."""
    adc = tmp_path / "application_default_credentials.json"
    adc.write_text(ADC_JSON)
    monkeypatch.setattr(spawner, "HOST_ADC_PATH", adc)
    monkeypatch.setenv("CLAUDE_CODE_USE_VERTEX", "1")
    monkeypatch.setenv("ANTHROPIC_VERTEX_PROJECT_ID", "test-project")
    monkeypatch.setenv("CLOUD_ML_REGION", "us-east5")
    return adc


@pytest.fixture
def bare_host(monkeypatch, tmp_path):
    """No Vertex, no ADC — the plain API-key deployment."""
    monkeypatch.setattr(spawner, "HOST_ADC_PATH", tmp_path / "missing.json")
    monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)


def test_api_key_wins_over_vertex(vertex_host):
    settings = {"anthropic_api_key": encrypt_value(STORED_API_KEY)}
    assert resolve_auth_env(CLAUDE, settings) == {"ANTHROPIC_API_KEY": STORED_API_KEY}


def test_oauth_token_uses_its_own_var(vertex_host):
    settings = {"anthropic_api_key": encrypt_value(STORED_OAUTH_TOKEN)}
    assert resolve_auth_env(CLAUDE, settings) == {"CLAUDE_CODE_OAUTH_TOKEN": STORED_OAUTH_TOKEN}


def test_no_credential_falls_back_to_host_vertex(vertex_host):
    """The case the scheduler used to get wrong: settings hold no key at all."""
    env = resolve_auth_env(CLAUDE, {"theme": "dark", "palette": "terminal-tide"})
    assert env == {
        "CLAUDE_CODE_USE_VERTEX": "1",
        "ANTHROPIC_VERTEX_PROJECT_ID": "test-project",
        "CLOUD_ML_REGION": "us-east5",
        "GOOGLE_ADC_JSON": ADC_JSON,
    }


def test_no_credential_and_no_vertex_is_unresolvable(bare_host):
    assert resolve_auth_env(CLAUDE, {}) is None
    assert resolve_auth_env(CLAUDE, None) is None


def test_codex_never_falls_back_to_vertex(vertex_host):
    """Vertex serves Claude; a Codex agent still needs its own key."""
    assert resolve_auth_env(CODEX, {}) is None
    settings = {"openai_api_key": encrypt_value(STORED_OPENAI_KEY)}
    assert resolve_auth_env(CODEX, settings) == {"OPENAI_API_KEY": STORED_OPENAI_KEY}
