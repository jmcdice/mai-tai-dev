"""Encryption at rest + masking for sensitive user settings."""

import json

from sqlalchemy import text

from app.core import crypto
from tests.conftest import auth_headers, sync_engine


def _stored_settings(email: str) -> dict:
    with sync_engine.begin() as conn:
        row = conn.execute(
            text("SELECT settings FROM users WHERE email = :email"), {"email": email}
        ).fetchone()
    value = row[0]
    return value if isinstance(value, dict) else json.loads(value)


# --- crypto unit tests -----------------------------------------------------


def test_encrypt_decrypt_roundtrip():
    token = crypto.encrypt_value("sk-ant-api03-supersecret")
    assert token.startswith(crypto.ENC_PREFIX)
    assert crypto.decrypt_value(token) == "sk-ant-api03-supersecret"
    # Idempotent: encrypting ciphertext doesn't double-wrap
    assert crypto.encrypt_value(token) == token


def test_decrypt_passes_legacy_plaintext_through():
    assert crypto.decrypt_value("sk-plain-legacy") == "sk-plain-legacy"


def test_mask_keeps_last_four():
    token = crypto.encrypt_value("sk-ant-api03-abcd1234")
    assert crypto.mask_value(token) == f"{crypto.MASK}1234"
    # Short secrets are fully masked
    assert crypto.mask_value(crypto.encrypt_value("tiny")) == crypto.MASK


def test_is_masked_echo():
    stored = crypto.encrypt_value("sk-ant-api03-abcd1234")
    mask = crypto.mask_value(stored)
    assert crypto.is_masked_echo(mask, stored) is True
    assert crypto.is_masked_echo("sk-new-real-key", stored) is False
    assert crypto.is_masked_echo(crypto.MASK, None) is True


# --- API behavior ----------------------------------------------------------


def test_settings_encrypted_at_rest_and_masked_in_response(client, user_a):
    resp = client.put(
        "/api/v1/auth/me",
        json={"settings": {"anthropic_api_key": "sk-ant-api03-secret9999", "timezone": "UTC"}},
        headers=auth_headers(user_a["token"]),
    )
    assert resp.status_code == 200
    returned = resp.json()["settings"]

    # Response is masked, non-sensitive settings untouched
    assert returned["anthropic_api_key"] == f"{crypto.MASK}9999"
    assert returned["timezone"] == "UTC"

    # GET /me masked too
    resp = client.get("/api/v1/auth/me", headers=auth_headers(user_a["token"]))
    assert resp.json()["settings"]["anthropic_api_key"] == f"{crypto.MASK}9999"

    # At rest: encrypted, and decrypts to the original
    stored = _stored_settings("a@example.com")
    assert stored["anthropic_api_key"].startswith(crypto.ENC_PREFIX)
    assert crypto.get_user_secret(stored, "anthropic_api_key") == "sk-ant-api03-secret9999"


def test_masked_echo_does_not_overwrite_secret(client, user_a):
    headers = auth_headers(user_a["token"])
    client.put(
        "/api/v1/auth/me",
        json={"settings": {"openai_api_key": "sk-openai-original-key1"}},
        headers=headers,
    )
    masked = client.get("/api/v1/auth/me", headers=headers).json()["settings"]["openai_api_key"]

    # Simulate the settings UI saving the whole form with the mask unchanged
    resp = client.put(
        "/api/v1/auth/me",
        json={"settings": {"openai_api_key": masked, "timezone": "America/Denver"}},
        headers=headers,
    )
    assert resp.status_code == 200

    stored = _stored_settings("a@example.com")
    assert crypto.get_user_secret(stored, "openai_api_key") == "sk-openai-original-key1"
    assert stored["timezone"] == "America/Denver"


def test_new_value_replaces_secret(client, user_a):
    headers = auth_headers(user_a["token"])
    client.put(
        "/api/v1/auth/me",
        json={"settings": {"github_token": "ghp_oldtoken0001"}},
        headers=headers,
    )
    client.put(
        "/api/v1/auth/me",
        json={"settings": {"github_token": "ghp_newtoken0002"}},
        headers=headers,
    )
    stored = _stored_settings("a@example.com")
    assert crypto.get_user_secret(stored, "github_token") == "ghp_newtoken0002"


def test_start_agent_reads_encrypted_credential(client, user_a):
    """The credential check must decrypt — an encrypted key counts as configured."""
    headers = auth_headers(user_a["token"])
    client.put(
        "/api/v1/auth/me",
        json={"settings": {"anthropic_api_key": "sk-ant-api03-agentkey1"}},
        headers=headers,
    )
    resp = client.post(
        "/api/v1/workspaces",
        json={"name": "A", "workspace_type": "agent", "agent_config": {"runtime": "claude-code"}},
        headers=headers,
    )
    ws_id = resp.json()["id"]

    resp = client.post(f"/api/v1/workspaces/{ws_id}/agent/start", headers=headers)
    # Must get PAST the 400 credential check; docker isn't available in tests,
    # so anything except "key not configured" proves decryption worked.
    assert "not configured" not in resp.text
