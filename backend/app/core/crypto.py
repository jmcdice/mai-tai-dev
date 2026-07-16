"""Encryption at rest for sensitive user settings.

API keys and tokens in users.settings (Anthropic, OpenAI, GitHub, StashAI)
are Fernet-encrypted before hitting the database and only decrypted
server-side at the point of use (agent spawn, stash enrichment). API
responses carry masked values (`••••••••abcd`), never the secret.

Key material comes from ENCRYPTION_KEY (a Fernet key; generate with
`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`),
falling back to a key derived from SECRET_KEY so encryption works out of the
box. Note the coupling under the fallback: rotating SECRET_KEY then also
re-keys stored secrets — set ENCRYPTION_KEY explicitly in production.

Stored ciphertext is prefixed `enc:v1:` so plaintext (legacy) and encrypted
values coexist; decrypt_value passes legacy plaintext through unchanged.
"""

import base64
import hashlib
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

logger = logging.getLogger(__name__)

ENC_PREFIX = "enc:v1:"

# users.settings keys that hold secrets
SENSITIVE_USER_SETTINGS = frozenset(
    {"anthropic_api_key", "openai_api_key", "github_token", "stash_llm_api_key"}
)

MASK = "••••••••"


@lru_cache
def _fernet() -> Fernet:
    settings = get_settings()
    if settings.encryption_key:
        return Fernet(settings.encryption_key.encode())
    # Derive a stable Fernet key from SECRET_KEY (sha256 -> urlsafe base64)
    digest = hashlib.sha256(f"mai-tai-enc:{settings.secret_key}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_value(value: str) -> str:
    """Encrypt a secret for storage. Idempotent on already-encrypted values."""
    if value.startswith(ENC_PREFIX):
        return value
    token = _fernet().encrypt(value.encode()).decode()
    return f"{ENC_PREFIX}{token}"


def decrypt_value(value: str) -> str | None:
    """Decrypt a stored secret. Legacy plaintext passes through unchanged.

    Returns None if the value is encrypted but cannot be decrypted (wrong
    key) — callers treat that as "not configured" rather than crashing.
    """
    if not value.startswith(ENC_PREFIX):
        return value
    try:
        return _fernet().decrypt(value[len(ENC_PREFIX):].encode()).decode()
    except (InvalidToken, ValueError):
        logger.error("Failed to decrypt a stored secret (ENCRYPTION_KEY changed?)")
        return None


def mask_value(value: str) -> str:
    """Mask a secret for API responses, keeping the last 4 chars for identification."""
    plain = decrypt_value(value)
    if not plain:
        return MASK
    return f"{MASK}{plain[-4:]}" if len(plain) > 8 else MASK


def encrypt_user_settings(settings_dict: dict) -> dict:
    """Return a copy with all sensitive keys encrypted."""
    result = dict(settings_dict)
    for key in SENSITIVE_USER_SETTINGS & result.keys():
        value = result[key]
        if isinstance(value, str) and value:
            result[key] = encrypt_value(value)
    return result


def masked_user_settings(settings_dict: dict | None) -> dict | None:
    """Return a copy with all sensitive keys masked (for API responses)."""
    if settings_dict is None:
        return None
    result = dict(settings_dict)
    for key in SENSITIVE_USER_SETTINGS & result.keys():
        value = result[key]
        if isinstance(value, str) and value:
            result[key] = mask_value(value)
    return result


def is_masked_echo(submitted: str, stored: str | None) -> bool:
    """True if a submitted value is just the mask of the stored secret.

    The settings UI round-trips whatever it displays; when the user saves
    without changing a key field, the masked value comes back and must not
    overwrite the real secret.
    """
    if not submitted.startswith(MASK):
        return False
    if stored is None:
        return True  # a bare mask with nothing stored means "no change" too
    return submitted == mask_value(stored)


def get_user_secret(user_settings: dict | None, key: str) -> str | None:
    """Read + decrypt a sensitive setting at point of use."""
    value = (user_settings or {}).get(key)
    if not isinstance(value, str) or not value:
        return None
    return decrypt_value(value)
