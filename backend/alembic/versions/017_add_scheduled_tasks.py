"""Scheduled tasks: per-workspace recurring prompts.

Revision ID: 017_add_scheduled_tasks
Revises: 016_encrypt_user_secrets
Create Date: 2026-07-16

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '017_add_scheduled_tasks'
down_revision = '016_encrypt_user_secrets'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'scheduled_tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('workspaces.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('cron_expression', sa.String(length=100), nullable=False),
        sa.Column('timezone', sa.String(length=64), nullable=False, server_default='UTC'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('wake_agent', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('next_run_at', sa.DateTime(), nullable=True),
        sa.Column('last_run_at', sa.DateTime(), nullable=True),
        sa.Column('last_status', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_scheduled_tasks_workspace_id', 'scheduled_tasks', ['workspace_id'])
    op.create_index('ix_scheduled_tasks_next_run_at', 'scheduled_tasks', ['next_run_at'])


def downgrade() -> None:
    op.drop_index('ix_scheduled_tasks_next_run_at', table_name='scheduled_tasks')
    op.drop_index('ix_scheduled_tasks_workspace_id', table_name='scheduled_tasks')
    op.drop_table('scheduled_tasks')
