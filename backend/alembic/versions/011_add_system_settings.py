"""Add system_settings table for admin-configurable settings.

Revision ID: 011
Revises: 010
"""

from alembic import op
import sqlalchemy as sa

revision = "011_add_system_settings"
down_revision = "010_add_agent_workspace_fields"


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(255), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False, server_default=""),
    )
    # Seed the default registration setting
    op.execute(
        "INSERT INTO system_settings (key, value) VALUES ('registration_enabled', 'true')"
    )


def downgrade() -> None:
    op.drop_table("system_settings")
