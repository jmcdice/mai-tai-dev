"""Encrypt existing plaintext secrets in users.settings.

API keys/tokens (anthropic_api_key, openai_api_key, github_token,
stash_llm_api_key) are now Fernet-encrypted at rest with an enc:v1: prefix.
This migration encrypts any plaintext values already stored; downgrade
decrypts them back.

Requires the same SECRET_KEY / ENCRYPTION_KEY the app runs with (the
migration runs inside the backend container, so it inherits them).

Revision ID: 016_encrypt_user_secrets
Revises: 015_add_message_fts_index
Create Date: 2026-07-16

"""
import json

from alembic import op
import sqlalchemy as sa

from app.core.crypto import (
    ENC_PREFIX,
    SENSITIVE_USER_SETTINGS,
    decrypt_value,
    encrypt_value,
)

revision = '016_encrypt_user_secrets'
down_revision = '015_add_message_fts_index'
branch_labels = None
depends_on = None


def _transform(transform) -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, settings FROM users WHERE settings IS NOT NULL")).fetchall()
    for user_id, settings in rows:
        if isinstance(settings, str):
            settings = json.loads(settings)
        if not isinstance(settings, dict):
            continue
        changed = False
        for key in SENSITIVE_USER_SETTINGS & settings.keys():
            value = settings[key]
            if isinstance(value, str) and value:
                new_value = transform(value)
                if new_value is not None and new_value != value:
                    settings[key] = new_value
                    changed = True
        if changed:
            conn.execute(
                sa.text("UPDATE users SET settings = :settings WHERE id = :id"),
                {"settings": json.dumps(settings), "id": user_id},
            )


def upgrade() -> None:
    _transform(lambda v: v if v.startswith(ENC_PREFIX) else encrypt_value(v))


def downgrade() -> None:
    _transform(lambda v: decrypt_value(v) if v.startswith(ENC_PREFIX) else v)
