"""Add indexes for the hot message query paths.

Every chat load and every MCP agent poll filters messages by workspace_id and
orders by created_at; the unseen-message poll additionally filters on
seen_at IS NULL AND user_id IS NOT NULL. Without indexes these are sequential
scans that get slower as history grows.

Revision ID: 013_add_message_indexes
Revises: 012_add_stash_issue_number
Create Date: 2026-07-16

"""
from alembic import op

revision = '013_add_message_indexes'
down_revision = '012_add_stash_issue_number'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        'ix_messages_workspace_created',
        'messages',
        ['workspace_id', 'created_at'],
    )
    # Partial index for the MCP unseen-message poll
    op.execute("""
        CREATE INDEX ix_messages_workspace_unseen
        ON messages (workspace_id, created_at)
        WHERE seen_at IS NULL AND user_id IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_messages_workspace_unseen")
    op.drop_index('ix_messages_workspace_created', table_name='messages')
