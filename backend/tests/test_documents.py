"""Tests for the document ingestion pipeline (APP-116, APP-139, APP-140).

Covers:
  1. Upload a valid .txt file — verify 201 + document metadata
  2. Upload a valid .md file — verify parsing and correct chunk order
  3. Upload a valid .pdf file — verify 201 + extracted metadata
  4. List documents — upload 2 documents, verify both returned
  5. Get document by id — fetch with chunks
  6. Reject invalid file type — upload .exe, verify error
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
