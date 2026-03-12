"""Add issue_number to stash_links.

Revision ID: 012_add_stash_issue_number
Revises: 011_add_system_settings
Create Date: 2026-03-12

"""
from alembic import op
import sqlalchemy as sa

revision = '012_add_stash_issue_number'
down_revision = '011_add_system_settings'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('stash_links', sa.Column('issue_number', sa.Integer(), nullable=False, server_default='0'))

    # Backfill existing rows: assign sequential numbers per user ordered by created_at
    op.execute("""
        UPDATE stash_links sl
        SET issue_number = sub.row_num
        FROM (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at) AS row_num
            FROM stash_links
        ) sub
        WHERE sl.id = sub.id
    """)


def downgrade() -> None:
    op.drop_column('stash_links', 'issue_number')
