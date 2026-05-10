from __future__ import annotations

import logging
import uuid
from pathlib import Path
from textwrap import wrap

logger = logging.getLogger(__name__)

_PAGE_WIDTH = 612
_PAGE_HEIGHT = 792
_LEFT = 50
_TOP = 760
_FONT_SIZE = 10
_LINE_HEIGHT = 14
_WRAP_WIDTH = 92
_LINES_PER_PAGE = 50


def generated_resume_pdf_path(storage_dir: Path, resume_id: uuid.UUID) -> Path:
    return storage_dir / "generated_resumes" / f"{resume_id}.pdf"


def write_generated_resume_pdf(
    storage_dir: Path,
    resume_id: uuid.UUID,
    resume_text: str,
) -> Path:
    path = generated_resume_pdf_path(storage_dir, resume_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render_text_pdf(resume_text))
    return path


# ---------------------------------------------------------------------------
# Beautified resumes (HTML + matching PDF, rendered by WeasyPrint)
# ---------------------------------------------------------------------------


def beautified_html_path(storage_dir: Path, beautification_id: uuid.UUID) -> Path:
    return storage_dir / "beautifications" / f"{beautification_id}.html"


def beautified_pdf_path(storage_dir: Path, beautification_id: uuid.UUID) -> Path:
    return storage_dir / "beautifications" / f"{beautification_id}.pdf"


def write_beautified_artifacts(
    storage_dir: Path,
    beautification_id: uuid.UUID,
    html_content: str,
) -> tuple[Path, Path]:
    """Persist the LLM-produced HTML alongside the WeasyPrint-rendered PDF.

    Both files come from the **same HTML source**, so the browser preview and
    the downloaded PDF stay in sync. Returns (html_path, pdf_path).
    """
    html_path = beautified_html_path(storage_dir, beautification_id)
    pdf_path = beautified_pdf_path(storage_dir, beautification_id)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html_content, encoding="utf-8")

    try:
        from weasyprint import HTML  # local import — heavy native deps
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "weasyprint is required for beautified PDF rendering — install "
            "system deps (libpango-1.0-0 libpangoft2-1.0-0) and the python "
            "package."
        ) from exc

    HTML(string=html_content).write_pdf(target=str(pdf_path))
    logger.info(
        "beautified_pdf_rendered id=%s html_bytes=%d pdf_bytes=%d",
        beautification_id,
        html_path.stat().st_size,
        pdf_path.stat().st_size,
    )
    return html_path, pdf_path


def render_text_pdf(resume_text: str) -> bytes:
    lines = _prepare_lines(resume_text)
    pages = [
        lines[index:index + _LINES_PER_PAGE]
        for index in range(0, len(lines), _LINES_PER_PAGE)
    ] or [[""]]

    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    kids = []
    for page_index, page_lines in enumerate(pages):
        page_obj = 4 + page_index * 2
        content_obj = page_obj + 1
        kids.append(f"{page_obj} 0 R")
        objects[page_obj] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_PAGE_WIDTH} {_PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj} 0 R >>"
        ).encode("ascii")
        stream = _content_stream(page_lines)
        objects[content_obj] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"\nendstream"
        )

    objects[2] = (
        f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>"
    ).encode("ascii")

    return _assemble_pdf(objects)


def _prepare_lines(text: str) -> list[str]:
    prepared: list[str] = []
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = _markdown_to_plain_text(raw_line.rstrip())
        if not line:
            prepared.append("")
            continue
        wrapped = wrap(
            line,
            width=_WRAP_WIDTH,
            break_long_words=False,
            replace_whitespace=False,
        )
        prepared.extend(wrapped or [""])
    return prepared


def _markdown_to_plain_text(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith("#"):
        return stripped.lstrip("#").strip().upper()
    return stripped.replace("**", "").replace("__", "")


def _content_stream(lines: list[str]) -> bytes:
    commands = [
        "BT",
        f"/F1 {_FONT_SIZE} Tf",
        f"{_LEFT} {_TOP} Td",
        f"{_LINE_HEIGHT} TL",
    ]
    for line in lines:
        commands.append(f"{_pdf_text(line)} Tj")
        commands.append("T*")
    commands.append("ET")
    return "\n".join(commands).encode("latin-1", "replace")


def _pdf_text(value: str) -> str:
    safe = value.encode("latin-1", "replace").decode("latin-1")
    safe = safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return f"({safe})"


def _assemble_pdf(objects: dict[int, bytes]) -> bytes:
    highest = max(objects)
    pdf = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    offsets = [0]
    for number in range(1, highest + 1):
        offsets.append(len(pdf))
        pdf += f"{number} 0 obj\n".encode("ascii")
        pdf += objects[number]
        pdf += b"\nendobj\n"

    xref_start = len(pdf)
    pdf += f"xref\n0 {highest + 1}\n".encode("ascii")
    pdf += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        pdf += f"{offset:010d} 00000 n \n".encode("ascii")
    pdf += (
        f"trailer\n<< /Size {highest + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_start}\n%%EOF\n"
    ).encode("ascii")
    return pdf
