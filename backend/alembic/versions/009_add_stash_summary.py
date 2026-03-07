"""Add summary and ai_generated columns to stash_links.

Revision ID: 009_add_stash_summary
Revises: 008_add_stash_links
Create Date: 2026-03-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '009_add_stash_summary'
down_revision: Union[str, None] = '008_add_stash_links'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('stash_links', sa.Column('summary', sa.Text(), nullable=True))
    op.add_column('stash_links', sa.Column('ai_title', sa.String(length=500), nullable=True))
    op.add_column('stash_links', sa.Column('ai_tags', sa.ARRAY(sa.String(length=100)), nullable=True))


def downgrade() -> None:
    op.drop_column('stash_links', 'ai_tags')
    op.drop_column('stash_links', 'ai_title')
    op.drop_column('stash_links', 'summary')
