from __future__ import annotations

import io


class NoExtractableTextError(ValueError):
    """Raised when a file yields zero parseable text (e.g. scanned-image PDF)."""


_PDF_MAGIC = b"%PDF-"
_DOCX_MAGIC = b"PK\x03\x04"


def _verify_magic(data: bytes, ext: str) -> None:
    if ext == "pdf" and not data.startswith(_PDF_MAGIC):
        raise ValueError("File does not appear to be a valid PDF.")
    if ext == "docx" and not data.startswith(_DOCX_MAGIC):
        raise ValueError("File does not appear to be a valid DOCX.")


def parse(data: bytes, ext: str) -> str:
    """Extract plain text from PDF or DOCX bytes.

    Raises:
        ValueError: unsupported extension or magic-byte mismatch.
        NoExtractableTextError: file yields no parseable text.
    """
    ext = ext.lower().lstrip(".")
    if ext not in ("pdf", "docx"):
        raise ValueError(f"Unsupported format: {ext!r}. Only pdf and docx are accepted.")
    _verify_magic(data, ext)

    if ext == "pdf":
        return _parse_pdf(data)
    return _parse_docx(data)


def _parse_pdf(data: bytes) -> str:
    from pypdf import PdfReader  # deferred import for test isolation

    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        parts.append(text)
    text = "\n".join(parts).strip()
    if not text:
        raise NoExtractableTextError(
            "No extractable text found in PDF. Scanned-image PDFs are not supported."
        )
    return text


def _parse_docx(data: bytes) -> str:
    from docx import Document  # deferred import for test isolation

    doc = Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    text = "\n".join(parts).strip()
    if not text:
        raise NoExtractableTextError("No extractable text found in DOCX.")
    return text
