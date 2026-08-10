"""Watchdog bookkeeping on workspace_agent_activity.

Revision ID: 019_add_agent_watchdog_columns
Revises: 018_backfill_api_key_scopes
Create Date: 2026-08-10

last_restart_at is not a statistic. The watchdog refuses to restart a
workspace again until last_activity_at has moved past last_restart_at — that
is the whole loop guard, so it has to survive a backend restart. Keeping it in
memory would mean a wedged agent gets restarted forever every time the backend
comes back up.
"""
import sqlalchemy as sa
from alembic import op

revision = '019_add_agent_watchdog_columns'
down_revision = '018_backfill_api_key_scopes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'workspace_agent_activity',
        sa.Column('last_restart_at', sa.DateTime(), nullable=True),
    )
    op.add_column(
        'workspace_agent_activity',
        sa.Column('restart_count', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('workspace_agent_activity', 'restart_count')
    op.drop_column('workspace_agent_activity', 'last_restart_at')
