"""Backfill api_keys.scopes before enforcement begins.

Revision ID: 018_backfill_api_key_scopes
Revises: 017_add_scheduled_tasks
Create Date: 2026-08-10

The scopes column has been written since the table existed but never read, so
nothing ever failed when a row ended up with an empty array. Now that
deps.require_scope enforces it, an empty array means "denied everything" —
which for a key minted before this migration would be an upgrade that silently
disconnects a running agent.

Backfill first, enforce second. After this runs, an empty scopes array is a
deliberate choice rather than an artifact, so the check needs no legacy branch.
"""
from alembic import op

revision = '018_backfill_api_key_scopes'
down_revision = '017_add_scheduled_tasks'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE api_keys
           SET scopes = ARRAY['read', 'write']
         WHERE scopes IS NULL
            OR cardinality(scopes) = 0
        """
    )


def downgrade() -> None:
    # Irreversible by design: the pre-migration state was "empty or populated,
    # indistinguishable", and guessing which rows to blank would revoke access
    # from keys that legitimately carry these scopes.
    pass
