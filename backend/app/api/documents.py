"""Document ingestion REST endpoints.

POST /documents/upload          — upload .md/.txt/.pdf/.docx/.html, parse → chunk → store
POST /documents/scrape          — scrape a URL, extract text → chunk → store
GET  /documents                 — list all documents
GET  /documents/supported       — list supported file extensions
GET  /documents/{id}            — get a single document with its chunks
"""

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.auth import get_current_user
from app.core.dependencies import get_db_session
from app.core.logging import get_logger
from app.ingestion import get_all_supported_extensions, ingest_document
from app.ingestion.parsers.registry import get_ext_to_content_type_map, get_parser_for
from app.ingestion.parsers.scraper import WebScraper
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.user import User
from app.retrieval.embeddings import get_embedding_model
from app.retrieval.keyword import BM25Index

logger = get_logger(__name__)

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
    metadata: dict[str, object] | None = Field(
        default=None, validation_alias="doc_metadata"
    )
    chunks: list[ChunkOut] = Field(default_factory=list)


class DocumentListOut(BaseModel):
    """List of documents (without chunks for brevity)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str
    file_size: int
    metadata: dict[str, object] | None = Field(
        default=None, validation_alias="doc_metadata"
    )


class UploadResponse(BaseModel):
    """Response after a successful upload."""

    document: DocumentOut
    chunk_count: int
    metadata: dict[str, object] | None = Field(
        default=None, validation_alias="doc_metadata"
    )


class ScrapeRequest(BaseModel):
    """Request body for web scraping."""

    url: str


class ScrapeResponse(BaseModel):
    """Response after a successful web scrape."""

    document: DocumentOut
    chunk_count: int
    source_url: str
    page_title: str | None = None


# ── Helpers ──────────────────────────────────────────────────────────────────

ALLOWED_EXTENSIONS: frozenset[str] = get_all_supported_extensions()
EXTENSION_TO_CONTENT_TYPE: dict[str, str] = get_ext_to_content_type_map()


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

    # Fall back to the declared type only when a parser supports it
    if declared_type:
        try:
            get_parser_for(filename)
            return declared_type
        except ValueError:
            pass

    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail=(
            f"Unsupported file type. Accepted extensions: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        ),
    )


def _validate_extension(filename: str) -> None:
    """Raise 415 if the filename extension is not supported by any parser."""
    import os

    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported file type '{ext}'. Accepted: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            ),
        )


async def _persist_and_embed(
    db: AsyncSession,
    *,
    filename: str,
    content_type: str,
    file_size: int,
    text: str,
    chunk_results: list,
    metadata: dict[str, Any] | None = None,
    user_id: uuid.UUID | None = None,
) -> Document:
    """Persist document + chunks, generate embeddings, rebuild BM25, trigger wiki.

    Shared between file upload and web scrape paths.
    """
    chunk_texts = [chunk_result.content for chunk_result in chunk_results]

    document = Document(
        filename=filename,
        content_type=content_type,
        file_size=file_size,
        metadata=metadata if metadata else None,
        user_id=user_id,
    )
    db.add(document)
    await db.flush()

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
        for (chunk_result, emb) in zip(chunk_results, embeddings, strict=True):
            await db.execute(
                Chunk.__table__.update()
                .where(Chunk.document_id == document.id)
                .where(Chunk.chunk_index == chunk_result.index)
                .values(embedding=emb)
            )
        await db.commit()
    except Exception as exc:
        logger.warning("Embedding generation failed: %s", exc)

    # Rebuild BM25 index so new chunks are searchable immediately
    await BM25Index.rebuild(db)

    # Trigger wiki generation as a background task
    from app.knowledge.wiki_service import WikiService

    async def _generate_wiki(doc_id: uuid.UUID) -> None:
        from app.core.dependencies import _session_factory

        async with _session_factory() as wiki_db:
            service = WikiService(wiki_db)
            try:
                await service.create_or_update_wiki(doc_id)
            except Exception as exc:
                logger.warning(
                    "Background wiki generation failed for document %s: %s", doc_id, exc
                )
            finally:
                await service.close()

    asyncio.create_task(_generate_wiki(document.id))

    await db.refresh(document, attribute_names=["chunks"])
    return document


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Upload a document file, parse it, split into chunks, and persist.

    Requires authentication. The document is owned by the authenticated user.
    Supported formats: .pdf, .docx, .html, .htm, .md, .txt
    The pipeline: raw bytes → plain text → chunks → DB rows.
    No LLM calls are made during ingestion.
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

    # Parse + chunk: bytes → text + metadata → chunks
    try:
        text, metadata, chunk_results = await ingest_document(raw_bytes, file.filename)
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

    document = await _persist_and_embed(
        db,
        filename=file.filename,
        content_type=content_type,
        file_size=file_size,
        text=text,
        chunk_results=chunk_results,
        metadata=metadata,
        user_id=current_user.id,
    )

    return UploadResponse(
        document=DocumentOut.model_validate(document),
        chunk_count=len(document.chunks),
        metadata=metadata if metadata else None,
    )


@router.post("/scrape", response_model=ScrapeResponse, status_code=status.HTTP_201_CREATED)
async def scrape_url(
    body: ScrapeRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Scrape a public web page, extract text, chunk, and store.

    Requires authentication. The document is owned by the authenticated user.
    Only HTTP/HTTPS URLs are allowed. Private network addresses are rejected.
    The page is fetched, HTML is stripped to plain text, then the text is
    chunked and stored like any other document.
    """
    try:
        result = await WebScraper.scrape(body.url)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from None
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch URL: {exc}",
        ) from None

    if not result.text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scraped page contains no processable text.",
        )

    # Generate a filename from the URL
    from urllib.parse import urlparse
    parsed = urlparse(body.url)
    safe_host = parsed.hostname.replace(".", "_") if parsed.hostname else "scraped"
    safe_path = parsed.path.strip("/").replace("/", "_") or "index"
    filename = f"{safe_host}__{safe_path}.html"[:255]

    # Chunk the extracted text
    from app.ingestion.chunkers.recursive import RecursiveChunker
    chunker = RecursiveChunker()
    chunk_results = chunker.chunk(result.text)

    if not chunk_results:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Chunking produced zero chunks — this should not happen.",
        )

    # Use a size estimate (content bytes not kept after parsing, so estimate from text)
    file_size = len(result.text.encode("utf-8"))

    # Extract metadata from the scraped page
    from app.ingestion.parsers.html_parser import HtmlParser
    html_meta = HtmlParser.extract_metadata(result.text.encode("utf-8"))
    metadata: dict[str, Any] = {}
    if result.title:
        metadata["title"] = result.title
    if html_meta.description:
        metadata["description"] = html_meta.description
    if html_meta.publish_date:
        metadata["publish_date"] = html_meta.publish_date

    document = await _persist_and_embed(
        db,
        filename=filename,
        content_type="text/html",
        file_size=file_size,
        text=result.text,
        chunk_results=chunk_results,
        metadata=metadata if metadata else None,
        user_id=current_user.id,
    )

    return ScrapeResponse(
        document=DocumentOut.model_validate(document),
        chunk_count=len(document.chunks),
        source_url=body.url,
        page_title=result.title,
    )


@router.get("/supported")
async def list_supported_extensions() -> dict[str, Any]:
    """Return the list of supported file extensions and their content types."""
    return {
        "extensions": sorted(ALLOWED_EXTENSIONS),
        "content_types": EXTENSION_TO_CONTENT_TYPE,
    }


@router.get("", response_model=list[DocumentListOut])
async def list_documents(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> Any:
    """List documents owned by the authenticated user (without chunk content for brevity)."""
    result = await db.execute(
        select(Document)
        .where(Document.user_id == current_user.id)
        .order_by(Document.created_at.desc())
    )
    documents = result.scalars().all()
    return documents


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Get a single document with its chunks, ordered by chunk_index.

    Only returns the document if it is owned by the authenticated user.
    """
    result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .where(Document.user_id == current_user.id)
        .options(selectinload(Document.chunks))
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found.",
        )

    return document


@router.delete("/{document_id}", status_code=status.HTTP_200_OK)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Delete a document, its chunks (ORM cascade), and wiki entry (DB cascade).

    Only allows deletion if the document is owned by the authenticated user.
    Rebuilds the BM25 index after deletion so removed chunks are no longer searchable.
    """
    result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .where(Document.user_id == current_user.id)
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found.",
        )

    await db.delete(document)
    await db.commit()

    # Rebuild BM25 index so deleted chunks are removed
    try:
        await BM25Index.rebuild(db)
    except Exception:
        pass

    return {"status": "deleted", "document_id": str(document_id)}
