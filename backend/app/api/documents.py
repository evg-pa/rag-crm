"""Document ingestion REST endpoints.

POST /documents/upload  — upload .md/.txt, parse → chunk → store
GET  /documents          — list all documents
GET  /documents/{id}     — get a single document with its chunks
"""

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_db_session
from app.ingestion import ingest_document
from app.ingestion.parsers.text_parser import TextParser
from app.models.chunk import Chunk
from app.models.document import Document
from app.retrieval.embeddings import get_embedding_model
from app.retrieval.keyword import BM25Index

router = APIRouter(prefix="/documents", tags=["documents"])


# ── Pydantic schemas ────────────────────────────────────────────────────────


class ChunkOut(BaseModel):
    """Chunk in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    content: str


class DocumentOut(BaseModel):
    """Document in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str
    file_size: int
    chunks: list[ChunkOut] = Field(default_factory=list)


class DocumentListOut(BaseModel):
    """List of documents (without chunks for brevity)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str
    file_size: int


class UploadResponse(BaseModel):
    """Response after a successful upload."""

    document: DocumentOut
    chunk_count: int


# ── Helpers ──────────────────────────────────────────────────────────────────

ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".md", ".txt"})
EXTENSION_TO_CONTENT_TYPE: dict[str, str] = {
    ".md": "text/markdown",
    ".txt": "text/plain",
}


def _detect_content_type(filename: str, declared_type: str | None) -> str:
    """Determine the MIME content-type from filename extension and/or
    the client-declared Content-Type header.

    Precedence: filename extension trumps the declared header so that
    files with misleading Content-Type are caught.
    """
    import os

    ext = os.path.splitext(filename)[1].lower()
    if ext in EXTENSION_TO_CONTENT_TYPE:
        return EXTENSION_TO_CONTENT_TYPE[ext]

    # Fall back to the declared type only when it's something we accept
    if declared_type and declared_type in TextParser.SUPPORTED_TYPES:
        return declared_type

    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail=(
            f"Unsupported file type. Accepted extensions: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        ),
    )


def _validate_extension(filename: str) -> None:
    """Raise 415 if the filename extension is not allowed."""
    import os

    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported file type '{ext}'. Accepted: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            ),
        )


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile,
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    """Upload a .md or .txt file, parse it, split into chunks, and persist.

    The pipeline: raw bytes → UTF-8 text → chunks → DB rows.
    No LLM calls are made.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required.",
        )

    _validate_extension(file.filename)

    # Read file content
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file: nothing to ingest.",
        )

    file_size = len(raw_bytes)

    # Determine content type
    content_type = _detect_content_type(file.filename, file.content_type)

    # Parse + chunk: bytes → text → chunks (orchestrated by ingest_document)
    try:
        text, chunk_results = await ingest_document(raw_bytes, file.filename)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from None

    if not text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File contains no processable text.",
        )

    if not chunk_results:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Chunking produced zero chunks — this should not happen.",
        )

    # Persist: document + chunks in a single transaction
    # Capture chunk contents for embedding (before DB operations complete)
    chunk_texts = [chunk_result.content for chunk_result in chunk_results]

    document = Document(
        filename=file.filename,
        content_type=content_type,
        file_size=file_size,
    )
    db.add(document)
    await db.flush()  # populate document.id

    for chunk_result in chunk_results:
        chunk = Chunk(
            document_id=document.id,
            chunk_index=chunk_result.index,
            content=chunk_result.content,
        )
        db.add(chunk)

    await db.commit()

    # Generate embeddings outside the DB session (no greenlet conflict)
    try:
        model = get_embedding_model()
        embeddings = await asyncio.gather(*[model.embed(t) for t in chunk_texts])
        # Update chunks in a new transaction
        for (chunk_result, emb) in zip(chunk_results, embeddings):
            await db.execute(
                Chunk.__table__.update()
                .where(Chunk.document_id == document.id)
                .where(Chunk.chunk_index == chunk_result.index)
                .values(embedding=emb)
            )
        await db.commit()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Embedding generation failed: %s", exc)

    # Rebuild BM25 index so new chunks are searchable immediately
    await BM25Index.rebuild(db)

    # Trigger wiki generation as a background task (fire and forget —
    # do not block the upload response).
    import asyncio
    from app.knowledge.wiki_service import WikiService

    async def _generate_wiki(doc_id: uuid.UUID) -> None:
        """Background task: generate a wiki entry for the uploaded document."""
        from app.core.dependencies import _session_factory

        async with _session_factory() as wiki_db:
            service = WikiService(wiki_db)
            try:
                await service.create_or_update_wiki(doc_id)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning(
                    "Background wiki generation failed for document %s: %s", doc_id, exc
                )
            finally:
                await service.close()

    asyncio.create_task(_generate_wiki(document.id))

    # Refresh so relationship children are loaded
    await db.refresh(document, attribute_names=["chunks"])

    return UploadResponse(
        document=DocumentOut.model_validate(document),
        chunk_count=len(document.chunks),
    )


@router.get("", response_model=list[DocumentListOut])
async def list_documents(
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    """List all ingested documents (without chunk content for brevity)."""
    result = await db.execute(select(Document).order_by(Document.created_at.desc()))
    documents = result.scalars().all()
    return documents


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    """Get a single document with its chunks, ordered by chunk_index."""
    result = await db.execute(
        select(Document).where(Document.id == document_id).options(selectinload(Document.chunks))
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found.",
        )

    return document
