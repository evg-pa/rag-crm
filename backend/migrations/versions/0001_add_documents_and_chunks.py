"""add documents and chunks tables

Revision ID: 0001_add_documents_and_chunks
Revises:
Create Date: 2026-06-22
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_add_documents_and_chunks"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Documents table (idempotent) ─────────────────────────────────────
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'documents'
            ) THEN
                CREATE TABLE documents (
                    id UUID PRIMARY KEY,
                    filename VARCHAR(255) NOT NULL,
                    content_type VARCHAR(50) NOT NULL,
                    file_size INTEGER NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
            END IF;
        END $$;
    """)

    # ── Chunks table (idempotent) ────────────────────────────────────────
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'chunks'
            ) THEN
                CREATE TABLE chunks (
                    id UUID PRIMARY KEY,
                    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
            END IF;
        END $$;
    """)

    # Create index on document_id if it doesn't exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE indexname = 'ix_chunks_document_id'
            ) THEN
                CREATE INDEX ix_chunks_document_id ON chunks (document_id);
            END IF;
        END $$;
    """)

    # Add pgvector extension and the embedding column (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
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
    op.drop_index("ix_chunks_document_id", table_name="chunks")
    op.drop_table("chunks")
    op.drop_table("documents")
    # Intentionally do NOT drop the vector extension — it may be used by
    # other tables in the same database.
    # The embedding column is dropped implicitly with the chunks table.
