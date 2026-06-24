"""Add crm_sync_runs table for CRM sync status tracking.

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crm_sync_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("contacts_synced", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deals_synced", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("activities_synced", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rag_documents_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rag_chunks_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_crm_sync_runs_completed_at",
        "crm_sync_runs",
        ["completed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_crm_sync_runs_completed_at", table_name="crm_sync_runs")
    op.drop_table("crm_sync_runs")
