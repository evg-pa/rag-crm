"""Add embedding vector(384) column to chunks table (idempotent).

Revision ID: 0002_add_embedding_column
Revises: 0001_add_documents_and_chunks
Create Date: 2026-06-22

The column may already exist if 0001 ran with the raw-SQL ALTER TABLE.
This migration is idempotent: it checks for the column before adding.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_add_embedding_column"
down_revision: str | None = "0001_add_documents_and_chunks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Enable the pgvector extension (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Add embedding column only if it doesn't already exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'chunks' AND column_name = 'embedding'
            ) THEN
                ALTER TABLE chunks ADD COLUMN embedding vector(384);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # Drop the embedding column if it exists (reversible)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'chunks' AND column_name = 'embedding'
            ) THEN
                ALTER TABLE chunks DROP COLUMN embedding;
            END IF;
        END $$;
    """)
