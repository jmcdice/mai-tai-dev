"""Drop the vestigial agents table.

Agent state was never stored here — it lives in Docker container labels plus
workspace_agent_activity, and per-workspace agent settings live in
workspaces.agent_config. The table has been unused since the agent-workspace
feature shipped.

Revision ID: 014_drop_agents_table
Revises: 013_add_message_indexes
Create Date: 2026-07-16

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '014_drop_agents_table'
down_revision = '013_add_message_indexes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table('agents')


def downgrade() -> None:
    # Definition copied from 001_initial_schema
    op.create_table(
        'agents',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('instructions', sa.Text(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id']),
        sa.PrimaryKeyConstraint('id')
    )
