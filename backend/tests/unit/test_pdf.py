from __future__ import annotations

import uuid

from backend.app.services.pdf import render_text_pdf, write_generated_resume_pdf


def test_render_text_pdf_returns_pdf_bytes():
    pdf = render_text_pdf("# Tailored Resume\n\nPython backend engineer")

    assert pdf.startswith(b"%PDF-1.4")
    assert b"%%EOF" in pdf


def test_write_generated_resume_pdf_creates_file(tmp_path):
    resume_id = uuid.uuid4()

    path = write_generated_resume_pdf(tmp_path, resume_id, "Tailored resume text")

    assert path.exists()
    assert path.name == f"{resume_id}.pdf"
    assert path.read_bytes().startswith(b"%PDF-1.4")
