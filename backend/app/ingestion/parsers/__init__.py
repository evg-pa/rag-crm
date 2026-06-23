"""Document parsers: extract plain text from different file formats."""

from app.ingestion.parsers.docx_parser import DocxParser
from app.ingestion.parsers.html_parser import HtmlParser
from app.ingestion.parsers.pdf_parser import PdfParser
from app.ingestion.parsers.registry import (
    get_all_supported_extensions,
    get_ext_to_content_type_map,
    get_parser_for,
)
from app.ingestion.parsers.scraper import ScrapeResult, WebScraper
from app.ingestion.parsers.text_parser import TextParser

__all__ = [
    "TextParser",
    "PdfParser",
    "DocxParser",
    "HtmlParser",
    "WebScraper",
    "ScrapeResult",
    "get_parser_for",
    "get_all_supported_extensions",
    "get_ext_to_content_type_map",
]
