from __future__ import annotations

import inspect
import logging
import time
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from backend.app.api.envelope import error, success
from backend.app.config import get_settings
from backend.app.db import get_db
from backend.app.models.generated_resume import GeneratedResume
from backend.app.models.resume_beautification import ResumeBeautification
from backend.app.schemas.evaluate import BeautificationOut, BeautifyIn
from backend.app.services.llm import LLMUnavailableError
from backend.app.services.llm.audit import (
    STATUS_FAILED,
    STATUS_SUCCEEDED,
    error_code_for_exception,
    error_message_for_exception,
    llm_metadata,
    record_llm_audit_log,
    stable_payload_hash,
)
from backend.app.services.llm.contracts import validate_beautify_result
from backend.app.services.llm.prompt_registry import (
    STEP_BEAUTIFY,
    prompt_version_for_step,
)
from backend.app.services.pdf import (
    beautified_html_path,
    beautified_pdf_path,
    write_beautified_artifacts,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _llm_client(request: Request):
    return request.app.state.llm_client


def _beautification_payload(b: ResumeBeautification) -> dict:
    item = BeautificationOut.model_validate(b).model_dump(mode="json")
    item["html_url"] = f"/api/beautifications/{b.id}/html"
    item["pdf_url"] = f"/api/beautifications/{b.id}/pdf"
    return item


@router.post("/generated-resumes/{resume_id}/beautify")
def beautify_resume(
    resume_id: uuid.UUID,
    body: BeautifyIn,
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    resume = db.get(GeneratedResume, resume_id)
    if resume is None:
        return error(
            "not_found",
            f"generated_resume {resume_id} not found",
            status_code=404,
        )

    llm = _llm_client(request)
    if not hasattr(llm, "beautify"):
        return error(
            "not_available",
            "Active LLM backend does not implement beautify().",
            status_code=503,
        )

    backend, model = llm_metadata(llm)
    prompt_version = prompt_version_for_step(STEP_BEAUTIFY)
    input_hash = stable_payload_hash(
        {
            "step": STEP_BEAUTIFY,
            "generated_resume_id": resume_id,
            "resume_text": resume.resume_text,
            "style": body.style,
            "prompt_version": prompt_version,
        }
    )
    started = time.perf_counter()
    try:
        beautify = llm.beautify
        kwargs: dict[str, object] = {"style": body.style}
        if "prompt_version" in inspect.signature(beautify).parameters:
            kwargs["prompt_version"] = prompt_version
        raw_result = dict(beautify(resume.resume_text, **kwargs))
        raw_result["prompt_version"] = prompt_version
        result = validate_beautify_result(
            raw_result,
            source=llm.__class__.__name__,
            source_markdown=resume.resume_text,
        )
    except LLMUnavailableError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        record_llm_audit_log(
            db,
            workflow_step=STEP_BEAUTIFY,
            backend=backend,
            model=model,
            prompt_version=prompt_version,
            input_hash=input_hash,
            latency_ms=latency_ms,
            status=STATUS_FAILED,
            error_code=error_code_for_exception(exc),
            error_message=error_message_for_exception(exc),
            request_id=getattr(request.state, "request_id", None),
            generated_resume_id=resume_id,
        )
        return error("llm_unavailable", str(exc), status_code=503)
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        record_llm_audit_log(
            db,
            workflow_step=STEP_BEAUTIFY,
            backend=backend,
            model=model,
            prompt_version=prompt_version,
            input_hash=input_hash,
            latency_ms=latency_ms,
            status=STATUS_FAILED,
            error_code=error_code_for_exception(exc),
            error_message=error_message_for_exception(exc),
            request_id=getattr(request.state, "request_id", None),
            generated_resume_id=resume_id,
        )
        logger.exception("beautify_llm_failed resume_id=%s", resume_id)
        return error("llm_invalid_output", str(exc), status_code=502)
    latency_ms = int((time.perf_counter() - started) * 1000)
    prompt_version = result.get("prompt_version", prompt_version)

    settings = get_settings()
    beautification = ResumeBeautification(
        generated_resume_id=resume_id,
        style=body.style,
        html_content=result["html_content"],
        prompt_version=prompt_version,
        llm_backend=backend,
        llm_model=model,
    )
    db.add(beautification)
    db.flush()

    try:
        _, pdf_path = write_beautified_artifacts(
            settings.storage_dir,
            beautification.id,
            beautification.html_content,
        )
    except RuntimeError as exc:
        # weasyprint missing — keep HTML, surface the error to the user
        logger.error("beautify_pdf_failed id=%s error=%s", beautification.id, exc)
        db.commit()
        record_llm_audit_log(
            db,
            workflow_step=STEP_BEAUTIFY,
            backend=backend,
            model=model,
            prompt_version=prompt_version,
            input_hash=input_hash,
            output_hash=stable_payload_hash(result["html_content"]),
            latency_ms=latency_ms,
            token_count_input=result.get("token_count_input"),
            token_count_output=result.get("token_count_output"),
            status=STATUS_SUCCEEDED,
            request_id=getattr(request.state, "request_id", None),
            generated_resume_id=resume_id,
            resume_beautification_id=beautification.id,
        )
        return error(
            "pdf_render_failed",
            "HTML was saved but PDF rendering failed (weasyprint not installed?).",
            status_code=500,
            details={"beautification_id": str(beautification.id)},
        )

    beautification.pdf_path = str(pdf_path)
    db.commit()
    db.refresh(beautification)
    record_llm_audit_log(
        db,
        workflow_step=STEP_BEAUTIFY,
        backend=backend,
        model=model,
        prompt_version=prompt_version,
        input_hash=input_hash,
        output_hash=stable_payload_hash(result["html_content"]),
        latency_ms=latency_ms,
        token_count_input=result.get("token_count_input"),
        token_count_output=result.get("token_count_output"),
        status=STATUS_SUCCEEDED,
        request_id=getattr(request.state, "request_id", None),
        generated_resume_id=resume_id,
        resume_beautification_id=beautification.id,
    )

    return success(_beautification_payload(beautification))


@router.get("/beautifications/{beautification_id}/pdf", response_model=None)
def download_beautified_pdf(
    beautification_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> FileResponse | JSONResponse:
    beautification = db.get(ResumeBeautification, beautification_id)
    if beautification is None:
        return error(
            "not_found",
            f"beautification {beautification_id} not found",
            status_code=404,
        )

    settings = get_settings()
    path = beautified_pdf_path(settings.storage_dir, beautification.id)
    if not path.exists():
        return error(
            "not_found",
            "Beautified PDF file is missing on disk.",
            status_code=404,
        )

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"beautified-resume-{beautification.id}.pdf",
    )


@router.get("/beautifications/{beautification_id}/html", response_model=None)
def view_beautified_html(
    beautification_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> FileResponse | JSONResponse:
    beautification = db.get(ResumeBeautification, beautification_id)
    if beautification is None:
        return error(
            "not_found",
            f"beautification {beautification_id} not found",
            status_code=404,
        )

    settings = get_settings()
    path = beautified_html_path(settings.storage_dir, beautification.id)
    if not path.exists():
        return error(
            "not_found",
            "Beautified HTML file is missing on disk.",
            status_code=404,
        )

    return FileResponse(
        path,
        media_type="text/html; charset=utf-8",
        filename=f"beautified-resume-{beautification.id}.html",
    )
