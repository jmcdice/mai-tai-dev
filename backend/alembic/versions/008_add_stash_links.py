"""Add stash_links table for StashAI plugin.

Revision ID: 008_add_stash_links
Revises: 007_add_message_type
Create Date: 2026-03-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '008_add_stash_links'
down_revision: Union[str, None] = '007_add_message_type'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'stash_links',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('thumbnail_url', sa.Text(), nullable=True),
        sa.Column('tags', postgresql.ARRAY(sa.String(length=100)), nullable=False, server_default='{}'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='unread'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_stash_links_user_id', 'stash_links', ['user_id'])
    op.create_index('ix_stash_links_created_at', 'stash_links', ['created_at'])
    op.create_index('ix_stash_links_status', 'stash_links', ['status'])


def downgrade() -> None:
    op.drop_index('ix_stash_links_status')
    op.drop_index('ix_stash_links_created_at')
    op.drop_index('ix_stash_links_user_id')
    op.drop_table('stash_links')
