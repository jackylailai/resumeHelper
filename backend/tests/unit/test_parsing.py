"""Unit tests for services/parsing.py — written BEFORE implementation changes.

Run: pytest backend/tests/unit/test_parsing.py -v
Expected initial state: PASS (parsing.py already exists from Phase 2)
"""

from __future__ import annotations

import io
import struct
import zipfile

import pytest

from backend.app.services.parsing import NoExtractableTextError, parse


# ---------------------------------------------------------------------------
# Helpers to build minimal valid file bytes
# ---------------------------------------------------------------------------

def make_minimal_pdf(text: str = "Hello World") -> bytes:
    """Build a minimal readable PDF with one text stream."""
    body = f"BT /F1 12 Tf 100 700 Td ({text}) Tj ET".encode()
    stream = b"stream\n" + body + b"\nendstream"
    obj4 = b"4 0 obj<</Length " + str(len(body)).encode() + b">>\n" + stream + b"\nendobj\n"

    parts = [
        b"%PDF-1.4\n",
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n",
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n",
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R"
        b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n",
        obj4,
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n",
        b"xref\n0 6\n0000000000 65535 f\n",
        b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n0\n%%EOF",
    ]
    return b"".join(parts)


def make_minimal_docx(text: str = "Hello World") -> bytes:
    """Build a minimal valid DOCX (ZIP with word/document.xml)."""
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>"
        + text
        + "</w:t></w:r></w:p></w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml",
            '<?xml version="1.0"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>")
        zf.writestr("_rels/.rels",
            '<?xml version="1.0"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/>'
            "</Relationships>")
        zf.writestr("word/_rels/document.xml.rels",
            '<?xml version="1.0"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
        zf.writestr("word/document.xml", xml)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------

def test_parse_pdf_returns_text():
    data = make_minimal_pdf("Senior Engineer Resume")
    result = parse(data, "pdf")
    assert "Senior Engineer Resume" in result or len(result) > 0


def test_parse_docx_returns_text():
    data = make_minimal_docx("Backend Developer Resume")
    result = parse(data, "docx")
    assert "Backend Developer Resume" in result


def test_parse_pdf_extension_case_insensitive():
    data = make_minimal_pdf("test")
    result = parse(data, "PDF")
    assert len(result) > 0


def test_parse_docx_extension_case_insensitive():
    data = make_minimal_docx("test")
    result = parse(data, "DOCX")
    assert "test" in result


# ---------------------------------------------------------------------------
# Magic byte validation
# ---------------------------------------------------------------------------

def test_pdf_magic_byte_mismatch_raises():
    bad_data = b"NOTPDF" + b"\x00" * 100
    with pytest.raises(ValueError, match="valid PDF"):
        parse(bad_data, "pdf")


def test_docx_magic_byte_mismatch_raises():
    bad_data = b"NOTZIP" + b"\x00" * 100
    with pytest.raises(ValueError, match="valid DOCX"):
        parse(bad_data, "docx")


# ---------------------------------------------------------------------------
# Unsupported format
# ---------------------------------------------------------------------------

def test_unsupported_format_raises():
    with pytest.raises(ValueError, match="Unsupported format"):
        parse(b"some content", "txt")


def test_unsupported_format_odt_raises():
    with pytest.raises(ValueError, match="Unsupported format"):
        parse(b"some content", "odt")


# ---------------------------------------------------------------------------
# No extractable text (FR-010)
# ---------------------------------------------------------------------------

def test_empty_pdf_raises_no_extractable_text():
    # A well-formed PDF with no text content
    empty_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f\n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n0\n%%EOF"
    )
    with pytest.raises(NoExtractableTextError):
        parse(empty_pdf, "pdf")


def test_empty_docx_raises_no_extractable_text():
    data = make_minimal_docx(text="")
    with pytest.raises(NoExtractableTextError):
        parse(data, "docx")
