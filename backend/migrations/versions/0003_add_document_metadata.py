"""add document metadata column

Revision ID: 0003_add_document_metadata
Revises: 0002_add_embedding_column
Create Date: 2026-06-23
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_add_document_metadata"
down_revision: str | None = "0002_add_embedding_column"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add doc_metadata column if it doesn't already exist (idempotent)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'documents' AND column_name = 'doc_metadata'
            ) THEN
                ALTER TABLE documents ADD COLUMN doc_metadata jsonb;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_column("documents", "doc_metadata")
