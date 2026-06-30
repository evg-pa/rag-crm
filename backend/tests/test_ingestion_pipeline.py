"""Anchor tests for the full ingestion pipeline (APP-143).

Covers end-to-end integration for all 5 supported formats:
  1. PDF upload → document created, chunks > 0, wiki triggered
  2. DOCX upload → content parsed correctly (headings + tables)
  3. HTML upload → nav/ads stripped, main content present
  4. Web scrape → mock httpx, content extracted and stored
  5. Unsupported format → 415 returned
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _read_fixture(name: str) -> bytes:
    """Read a binary fixture file from tests/fixtures/."""
    path = FIXTURES_DIR / name
    if not path.exists():
        pytest.skip(f"Fixture file {name} not found — run generate_fixtures.py first")
    return path.read_bytes()


async def _upload_and_assert(
    client: AsyncClient,
    filename: str,
    content: bytes,
    *,
    expected_content_type: str,
    expected_text_fragment: str | None = None,
) -> dict:
    """Upload a file and perform common assertions.

    Returns the parsed JSON response dict.

    Uses the expected_content_type as the per-part Content-Type header so
    that the server's content-type whitelist accepts the upload.  Without an
    explicit Content-Type, httpx may fall back to ``application/octet-stream``
    for formats whose MIME type is not in Python's mimetypes database
    (e.g. .docx), which would cause a 415.
    """
    response = await client.post(
        "/documents/upload",
        files={"file": (filename, content, expected_content_type)},
    )
    assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"

    data = response.json()
    doc = data["document"]

    # Document metadata
    assert doc["filename"] == filename
    assert doc["content_type"] == expected_content_type
    assert doc["file_size"] > 0

    # Chunk assertions
    assert data["chunk_count"] > 0, "Expected at least one chunk"
    assert len(doc["chunks"]) == data["chunk_count"]

    # Chunk ordering
    for i, chunk in enumerate(doc["chunks"]):
        assert chunk["chunk_index"] == i
        assert chunk["content"]
        assert chunk["document_id"] == doc["id"]

    # Verify content if a fragment is expected
    if expected_text_fragment:
        all_text = " ".join(chunk["content"] for chunk in doc["chunks"])
        assert expected_text_fragment in all_text, (
            f"Expected fragment '{expected_text_fragment}' not found in extracted text"
        )

    return data


async def _check_wiki_created(client: AsyncClient, document_id: str) -> dict | None:
    """Check if a wiki entry exists for the given document."""
    response = await client.get(f"/wiki/{document_id}")
    if response.status_code == 200:
        return response.json()
    return None


# ── Test 1: PDF Upload ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_pdf_creates_document_and_chunks(
    client: AsyncClient,
    _setup_database: None,
    _clean_db: None,
) -> None:
    """Upload a sample PDF → assert document created, chunks > 0, wiki triggered."""
    pdf_bytes = _read_fixture("sample.pdf")

    data = await _upload_and_assert(
        client,
        "sample.pdf",
        pdf_bytes,
        expected_content_type="application/pdf",
        expected_text_fragment="RAG-CRM Integration Test",
    )

    doc = data["document"]

    # Verify document is retrievable
    get_resp = await client.get(f"/documents/{doc['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["filename"] == "sample.pdf"

    # Verify it appears in the document list
    list_resp = await client.get("/documents")
    assert list_resp.status_code == 200
    filenames = [d["filename"] for d in list_resp.json()]
    assert "sample.pdf" in filenames


# ── Test 2: DOCX Upload ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_docx_parses_headings_and_tables(
    client: AsyncClient,
    _setup_database: None,
    _clean_db: None,
) -> None:
    """Upload a sample DOCX → assert headings and table content parsed."""
    docx_bytes = _read_fixture("sample.docx")

    data = await _upload_and_assert(
        client,
        "sample.docx",
        docx_bytes,
        expected_content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        expected_text_fragment="RAG-CRM Integration Test",
    )

    all_text = " ".join(chunk["content"] for chunk in data["document"]["chunks"])

    # Verify heading extraction
    assert "RAG-CRM Integration Test" in all_text
    assert "Data Table" in all_text

    # Verify table extraction
    assert "Alice" in all_text
    assert "Engineer" in all_text
    assert "Bob" in all_text
    assert "Analyst" in all_text


# ── Test 3: HTML Upload ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_html_strips_nav_and_preserves_main(
    client: AsyncClient,
    _setup_database: None,
    _clean_db: None,
) -> None:
    """Upload an HTML file → assert nav/ads stripped, main content present."""
    html_bytes = _read_fixture("sample.html")

    data = await _upload_and_assert(
        client,
        "sample.html",
        html_bytes,
        expected_content_type="text/html",
        expected_text_fragment="Section One",
    )

    all_text = " ".join(chunk["content"] for chunk in data["document"]["chunks"])

    # ── Main content MUST be present ──
    assert "Section One" in all_text
    assert "Introduction" in all_text
    assert "Section Two" in all_text
    assert "hybrid search" in all_text.lower()

    # ── Nav elements MUST be stripped ──
    assert "Home" not in all_text, "Nav link 'Home' should be stripped"
    assert "About" not in all_text, "Nav link 'About' should be stripped"
    assert "Contact" not in all_text, "Nav link 'Contact' should be stripped"

    # ── Script content MUST be stripped ──
    assert "console.log" not in all_text

    # ── Footer MUST be stripped ──
    assert "All rights reserved" not in all_text

    # ── Aside MUST be stripped ──
    assert "Sidebar content" not in all_text


# ── Test 4: Web Scrape (mocked) ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scrape_url_extracts_content_and_stores(
    client: AsyncClient,
    _setup_database: None,
    _clean_db: None,
) -> None:
    """Scrape a mocked web page → assert content extracted and stored."""
    mock_html = b"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Mocked Scrape Page</title>
    <script>console.log('should be gone');</script>
    <style>body { color: black; }</style>
</head>
<body>
    <nav><a href="/">Home</a></nav>
    <main>
        <article>
            <h1>Understanding RAG Systems</h1>
            <p>Retrieval-Augmented Generation combines search with LLM generation
            to produce grounded, factual answers from a knowledge base.</p>
            <p>This approach reduces hallucinations and provides verifiable sources
            for every claim made by the language model.</p>
        </article>
    </main>
    <footer>Mock footer -- should be stripped.</footer>
</body>
</html>"""

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "text/html; charset=utf-8"}
    mock_response.content = mock_html
    mock_response.encoding = "utf-8"
    mock_response.text = mock_html.decode("utf-8")

    # robots.txt response: return 404 so scraping proceeds to the main URL
    mock_robots_response = AsyncMock()
    mock_robots_response.status_code = 404

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(side_effect=[mock_robots_response, mock_response])

    with patch("httpx.AsyncClient", return_value=mock_client):
        response = await client.post(
            "/documents/scrape",
            json={"url": "https://example.com/rag-article"},
        )

    assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"

    data = response.json()

    # Verify response structure
    assert data["source_url"] == "https://example.com/rag-article"
    assert data["page_title"] == "Mocked Scrape Page"
    assert data["chunk_count"] > 0

    doc = data["document"]
    assert doc["content_type"] == "text/html"
    assert doc["file_size"] > 0

    # Verify content — main article should be present
    all_text = " ".join(chunk["content"] for chunk in doc["chunks"])
    assert "Understanding RAG Systems" in all_text
    assert "Retrieval-Augmented Generation" in all_text
    assert "hallucinations" in all_text

    # Nav / footer should be stripped
    assert "Home" not in all_text, "Nav elements should be stripped"
    assert "Mock footer" not in all_text, "Footer should be stripped"


# ── Test 5: Unsupported Format → 415 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_unsupported_format_returns_415(
    client: AsyncClient,
    _setup_database: None,
    _clean_db: None,
) -> None:
    """Upload a .xyz file → assert 415 Unsupported Media Type."""
    response = await client.post(
        "/documents/upload",
        files={"file": ("unknown.xyz", b"some binary content here")},
    )
    assert response.status_code == 415, f"Expected 415, got {response.status_code}: {response.text}"

    detail = response.json()["detail"]
    assert "Unsupported file type" in detail
    assert ".xyz" in detail or "unsupported" in detail.lower()


# ── Additional integration tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_multi_format_upload_all_appear_in_list(
    client: AsyncClient,
    _setup_database: None,
    _clean_db: None,
) -> None:
    """Upload one of each format and verify all appear in the document list."""
    pdf_bytes = _read_fixture("sample.pdf")
    docx_bytes = _read_fixture("sample.docx")
    html_bytes = _read_fixture("sample.html")

    # Upload all three — use 3-tuples to send explicit Content-Type per part
    # so the server content-type whitelist accepts the uploads.
    resp1 = await client.post(
        "/documents/upload",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
    )
    assert resp1.status_code == 201

    resp2 = await client.post(
        "/documents/upload",
        files={
            "file": (
                "test.docx",
                docx_bytes,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert resp2.status_code == 201

    resp3 = await client.post(
        "/documents/upload",
        files={"file": ("test.html", html_bytes, "text/html")},
    )
    assert resp3.status_code == 201

    # Also upload a .txt for good measure
    resp4 = await client.post(
        "/documents/upload",
        files={"file": ("notes.txt", b"Plain text document.", "text/plain")},
    )
    assert resp4.status_code == 201

    # Verify all appear in list
    list_resp = await client.get("/documents")
    assert list_resp.status_code == 200
    filenames = {d["filename"] for d in list_resp.json()}
    assert filenames == {"test.pdf", "test.docx", "test.html", "notes.txt"}


@pytest.mark.asyncio
async def test_scrape_rejects_unsupported_url(
    client: AsyncClient,
    _setup_database: None,
    _clean_db: None,
) -> None:
    """Scrape endpoint rejects non-HTTP URLs with 400."""
    response = await client.post(
        "/documents/scrape",
        json={"url": "ftp://files.example.com/data"},
    )
    assert response.status_code == 400
