"""Full-text search index on message content.

Backs the agents' search_history tool: workspace-scoped recall over the
entire message history ("did we discuss X last week?") without embeddings
or extra infrastructure — the messages table is already the transcript store.

Revision ID: 015_add_message_fts_index
Revises: 014_drop_agents_table
Create Date: 2026-07-16

"""
from alembic import op

revision = '015_add_message_fts_index'
down_revision = '014_drop_agents_table'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX ix_messages_content_fts
        ON messages USING GIN (to_tsvector('english', content))
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_messages_content_fts")
