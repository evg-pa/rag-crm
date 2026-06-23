"""Unit tests for PdfParser (APP-140).

Covers:
  1. Parse a valid minimal PDF — returns text + metadata
  2. Parse a PDF with metadata (title, author) — extracts all fields
  3. Reject non-PDF file extension
  4. Reject corrupted PDF bytes
  5. Empty PDF produces empty text
"""

import pytest
from app.ingestion.parsers.pdf_parser import PdfParser


def _minimal_pdf_bytes() -> bytes:
    """Build a minimal valid PDF with one page and no text."""
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
        b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
        b"0000000058 00000 n \n0000000115 00000 n \n"
        b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n190\n%%EOF\n"
    )


def _pdf_with_metadata() -> bytes:
    """Build a minimal PDF with Info metadata and a text stream."""
    # This is a hand-crafted minimal PDF with a content stream and metadata.
    # page content stream (obj 5) contains "Hello PDF World" text
    content_stream = (
        b"BT /F1 12 Tf 100 700 Td (Hello PDF World) Tj ET"
    )
    obj5 = (
        b"5 0 obj\n<< /Length %d >>\nstream\n" % len(content_stream)
        + content_stream
        + b"\nendstream\nendobj\n"
    )

    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 5 0 R /Resources << /Font << /F1 6 0 R >> >> >>\nendobj\n"
        b"4 0 obj\n<< /Title (Test Document) /Author (Alice) "
        b"/Subject (Testing) /Keywords (pdf, test) "
        b"/Creator (pytest) /Producer (UnitTest 1.0) "
        b"/CreationDate (D:20260101120000+00'00') >>\nendobj\n"
    )
    pdf += obj5
    pdf += (
        b"6 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"xref\n0 7\n0000000000 65535 f \n0000000009 00000 n \n"
        b"0000000058 00000 n \n0000000115 00000 n \n0000000210 00000 n \n"
        b"0000000342 00000 n \n0000000450 00000 n \n"
        b"trailer\n<< /Size 7 /Root 1 0 R /Info 4 0 R >>\nstartxref\n520\n%%EOF\n"
    )
    return pdf


@pytest.mark.asyncio
async def test_parse_minimal_pdf() -> None:
    """Parse a minimal PDF with no text — returns empty text + page_count."""
    text, metadata = await PdfParser.parse(_minimal_pdf_bytes(), "doc.pdf")
    assert text == ""
    assert metadata["page_count"] == 1


@pytest.mark.asyncio
async def test_parse_pdf_with_metadata() -> None:
    """Parse a PDF with metadata — extracts title, author, subject, keywords, etc."""
    text, metadata = await PdfParser.parse(_pdf_with_metadata(), "report.pdf")
    assert "Hello PDF World" in text
    assert metadata["title"] == "Test Document"
    assert metadata["author"] == "Alice"
    assert metadata["subject"] == "Testing"
    assert metadata["keywords"] == "pdf, test"
    assert metadata["creator"] == "pytest"
    assert metadata["producer"] == "UnitTest 1.0"
    assert "creation_date" in metadata
    assert metadata["page_count"] == 1


@pytest.mark.asyncio
async def test_reject_invalid_extension() -> None:
    """PdfParser.parse raises ValueError for non-.pdf filenames."""
    with pytest.raises(ValueError, match="Unsupported file extension"):
        await PdfParser.parse(b"not a pdf", "file.txt")


@pytest.mark.asyncio
async def test_reject_corrupted_pdf() -> None:
    """PdfParser.parse raises ValueError for corrupted/empty PDF bytes."""
    with pytest.raises(ValueError, match="Failed to read PDF"):
        await PdfParser.parse(b"this is not a pdf at all", "bad.pdf")


@pytest.mark.asyncio
async def test_supports_method() -> None:
    """PdfParser.supports correctly identifies .pdf files."""
    assert PdfParser.supports("report.pdf") is True
    assert PdfParser.supports("report.PDF") is True
    assert PdfParser.supports("report.txt") is False
    assert PdfParser.supports("report.md") is False
    assert PdfParser.supports("report.docx") is False
