"""Tests for the document ingestion pipeline (APP-116, APP-139, APP-140, APP-179).

Covers:
  1. Upload a valid .txt file — verify 201 + document metadata
  2. Upload a valid .md file — verify parsing and correct chunk order
  3. Upload a valid .pdf file — verify 201 + extracted metadata
  4. List documents — upload 2 documents, verify both returned
  5. Get document by id — fetch with chunks
  6. Reject invalid file type — upload .exe, verify error
  7. Reject oversized file via Content-Length pre-check — verify 413
  8. Reject oversized file post-read (spoofed Content-Length) — verify 413
  9. Reject upload with unsupported Content-Type header — verify 415
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_upload_txt_document(client: AsyncClient) -> None:
    """POST /documents/upload with a .txt file returns 201 + filename/content_type/file_size."""
    response = await client.post(
        "/documents/upload",
        files={"file": ("testfile.txt", b"Hello world. This is a test.\n\nSecond paragraph.")},
    )
    assert response.status_code == 201, response.text

    data = response.json()
    doc = data["document"]
    assert doc["filename"] == "testfile.txt"
    assert doc["content_type"] == "text/plain"
    assert doc["file_size"] > 0
    assert data["chunk_count"] > 0


@pytest.mark.asyncio
async def test_upload_md_document(client: AsyncClient) -> None:
    """POST /documents/upload with a .md file parses it and creates correctly ordered chunks."""
    md_content = (
        b"# Heading 1\n\n"
        b"Paragraph one with some text.\n\n"
        b"## Heading 2\n\n"
        b"Paragraph two with more text.\n\n"
        b"* List item one\n"
        b"* List item two\n"
    )

    response = await client.post(
        "/documents/upload",
        files={"file": ("readme.md", md_content)},
    )
    assert response.status_code == 201, response.text

    data = response.json()
    doc = data["document"]
    assert doc["filename"] == "readme.md"
    assert doc["content_type"] == "text/markdown"
    assert doc["file_size"] > 0
    assert data["chunk_count"] > 0
    assert len(doc["chunks"]) == data["chunk_count"]

    # Verify chunks are ordered and have content
    for i, chunk in enumerate(doc["chunks"]):
        assert chunk["chunk_index"] == i
        assert chunk["content"]
        assert chunk["document_id"] == doc["id"]


@pytest.mark.asyncio
async def test_upload_pdf_document(client: AsyncClient) -> None:
    """POST /documents/upload with a .pdf file returns 201 + extracted metadata."""
    import pathlib

    fixture_path = pathlib.Path(__file__).parent / "fixtures" / "sample.pdf"
    pdf_bytes = fixture_path.read_bytes()

    response = await client.post(
        "/documents/upload",
        files={"file": ("report.pdf", pdf_bytes)},
    )
    assert response.status_code == 201, response.text

    data = response.json()
    doc = data["document"]
    assert doc["filename"] == "report.pdf"
    assert doc["content_type"] == "application/pdf"
    assert doc["file_size"] > 0
    assert data["chunk_count"] >= 0


@pytest.mark.asyncio
async def test_list_documents(client: AsyncClient) -> None:
    """GET /documents returns all uploaded documents (without chunk content)."""
    # Upload two documents
    await client.post(
        "/documents/upload",
        files={"file": ("doc_a.txt", b"Content for document A.")},
    )
    await client.post(
        "/documents/upload",
        files={"file": ("doc_b.md", b"# Document B\n\nContent for B.")},
    )

    response = await client.get("/documents")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2

    filenames = {item["filename"] for item in data}
    assert filenames == {"doc_a.txt", "doc_b.md"}

    # List endpoint is compact — no chunks
    for item in data:
        assert "chunks" not in item


@pytest.mark.asyncio
async def test_get_document_by_id(client: AsyncClient) -> None:
    """GET /documents/{id} returns a single document with its chunks."""
    upload_resp = await client.post(
        "/documents/upload",
        files={"file": ("get_test.txt", b"Document for get-by-id test. More text here.")},
    )
    assert upload_resp.status_code == 201
    doc_id = upload_resp.json()["document"]["id"]

    response = await client.get(f"/documents/{doc_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == doc_id
    assert data["filename"] == "get_test.txt"
    assert data["content_type"] == "text/plain"
    assert len(data["chunks"]) > 0

    for i, chunk in enumerate(data["chunks"]):
        assert chunk["chunk_index"] == i
        assert chunk["document_id"] == doc_id


@pytest.mark.asyncio
async def test_upload_invalid_file_type(client: AsyncClient) -> None:
    """POST /documents/upload rejects files with unsupported extensions."""
    response = await client.post(
        "/documents/upload",
        files={"file": ("malware.exe", b"MZ\x00\x00 fake exe content")},
    )
    assert response.status_code == 415
    assert "Unsupported file type" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_size_limit_content_length(client: AsyncClient) -> None:
    """POST /documents/upload rejects oversized files via Content-Length pre-check (413).

    Sends a small body but a large Content-Length header to test the fast
    pre-check that runs before reading the request body.
    """
    # Default MAX_UPLOAD_SIZE_MB is 50 MB, so 51 MB Content-Length should be rejected.
    oversize_bytes = 51 * 1024 * 1024
    response = await client.post(
        "/documents/upload",
        files={"file": ("big.txt", b"small body")},
        headers={"Content-Length": str(oversize_bytes)},
    )
    assert response.status_code == 413
    detail = response.json()["detail"]
    assert "too large" in detail.lower()


@pytest.mark.asyncio
async def test_upload_content_type_whitelist_reject(client: AsyncClient) -> None:
    """POST /documents/upload rejects files with a non-whitelisted Content-Type.

    Uses a 3-tuple in httpx's ``files`` parameter to set the per-part
    content type to ``application/octet-stream``, which is not allowed.
    """
    response = await client.post(
        "/documents/upload",
        files={
            "file": (
                "data.txt",
                b"Hello world.",
                "application/octet-stream",
            )
        },
    )
    assert response.status_code == 415
    detail = response.json()["detail"]
    assert "Content-Type" in detail


@pytest.mark.asyncio
async def test_upload_valid_passes_content_type_check(client: AsyncClient) -> None:
    """POST /documents/upload accepts files with a valid Content-Type."""
    response = await client.post(
        "/documents/upload",
        files={"file": ("ok.txt", b"Valid content with proper type.")},
    )
    assert response.status_code == 201, response.text


# ── Unit tests for helper functions ─────────────────────────────────────────


class TestValidateUploadSize:
    """Unit tests for _validate_upload_size pre-check."""

    def test_rejects_oversized_content_length(self):
        """413 when Content-Length > max_bytes."""
        from unittest.mock import Mock

        from fastapi import HTTPException

        from app.api.documents import _validate_upload_size

        request = Mock()
        request.headers = {"Content-Length": "2000000"}

        with pytest.raises(HTTPException) as exc_info:
            _validate_upload_size(request, max_bytes=1000000)
        assert exc_info.value.status_code == 413

    def test_allows_valid_content_length(self):
        """No exception when Content-Length <= max_bytes."""
        from unittest.mock import Mock

        from app.api.documents import _validate_upload_size

        request = Mock()
        request.headers = {"Content-Length": "500000"}

        # Should not raise
        _validate_upload_size(request, max_bytes=1000000)

    def test_allows_missing_content_length(self):
        """No exception when Content-Length is missing."""
        from unittest.mock import Mock

        from app.api.documents import _validate_upload_size

        request = Mock()
        request.headers = {}

        # Should not raise — missing header falls through to post-read check
        _validate_upload_size(request, max_bytes=1000000)

    def test_rejects_invalid_content_length(self):
        """400 when Content-Length is not an integer."""
        from unittest.mock import Mock

        from fastapi import HTTPException

        from app.api.documents import _validate_upload_size

        request = Mock()
        request.headers = {"Content-Length": "not-a-number"}

        with pytest.raises(HTTPException) as exc_info:
            _validate_upload_size(request, max_bytes=1000000)
        assert exc_info.value.status_code == 400


class TestCheckSizeAfterRead:
    """Unit tests for _check_size_after_read post-read check."""

    def test_rejects_oversized_body(self):
        """413 when actual body size > max_bytes."""
        from fastapi import HTTPException

        from app.api.documents import _check_size_after_read

        with pytest.raises(HTTPException) as exc_info:
            _check_size_after_read(b"x" * 2000, max_bytes=1000, filename="test.txt")
        assert exc_info.value.status_code == 413

    def test_allows_valid_body(self):
        """No exception when body size <= max_bytes."""
        from app.api.documents import _check_size_after_read

        # Should not raise
        _check_size_after_read(b"x" * 500, max_bytes=1000, filename="test.txt")


class TestValidateContentType:
    """Unit tests for _validate_content_type whitelist check."""

    def test_rejects_unsupported_content_type(self):
        """415 when Content-Type is not in the whitelist."""
        from fastapi import HTTPException

        from app.api.documents import _validate_content_type

        with pytest.raises(HTTPException) as exc_info:
            _validate_content_type("application/octet-stream", "data.bin")
        assert exc_info.value.status_code == 415

    def test_allows_text_plain(self):
        """No exception for whitelisted Content-Type."""
        from app.api.documents import _validate_content_type

        _validate_content_type("text/plain", "data.txt")

    def test_allows_none_content_type(self):
        """No exception when Content-Type is None (not provided)."""
        from app.api.documents import _validate_content_type

        _validate_content_type(None, "data.txt")
