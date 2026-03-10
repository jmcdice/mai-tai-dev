"""Add agent workspace fields.

Revision ID: 010_add_agent_workspace_fields
Revises: 009_add_stash_summary
Create Date: 2026-03-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = '010_add_agent_workspace_fields'
down_revision: Union[str, None] = '009_add_stash_summary'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("workspaces", sa.Column("workspace_type", sa.String(20), server_default="chat", nullable=False))
    op.add_column("workspaces", sa.Column("agent_purpose", sa.Text(), nullable=True))
    op.add_column("workspaces", sa.Column("agent_config", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("workspaces", "agent_config")
    op.drop_column("workspaces", "agent_purpose")
    op.drop_column("workspaces", "workspace_type")
