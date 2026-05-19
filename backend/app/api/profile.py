from __future__ import annotations

import inspect
import io
import logging
import time
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pypdf import PdfReader
from sqlalchemy.orm import Session

from backend.app.api.envelope import error, success
from backend.app.config import get_settings
from backend.app.db import get_db
from backend.app.models.baseline_profile import BaselineProfile
from backend.app.models.generated_resume import GeneratedResume
from backend.app.models.job_analysis import JobAnalysis
from backend.app.schemas.profile import (
    ProfileDeleteImpactOut,
    ProfileIn,
    ProfileOut,
    ProfilePdfPreviewOut,
    ProfileUpdateIn,
)
from backend.app.services.evaluator_v2 import (
    create_profile,
    delete_profile,
    get_default_profile,
    get_profile,
    list_profiles,
    update_profile,
)
from backend.app.services.llm.audit import (
    STATUS_FAILED,
    STATUS_SUCCEEDED,
    error_code_for_exception,
    error_message_for_exception,
    llm_metadata,
    record_llm_audit_log,
    stable_payload_hash,
)
from backend.app.services.llm.contracts import validate_structured_extraction_output
from backend.app.services.llm.prompt_registry import STEP_EXTRACT, prompt_version_for_step

logger = logging.getLogger(__name__)
router = APIRouter()


class UploadTooLargeError(ValueError):
    def __init__(self, actual_bytes: int, max_bytes: int) -> None:
        super().__init__(f"Uploaded file exceeds the {max_bytes} byte limit")
        self.actual_bytes = actual_bytes
        self.max_bytes = max_bytes


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes, normalising unicode and stripping
    JSON-unsafe bytes (NUL, unpaired surrogates) while preserving line
    structure."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    if not text:
        raise ValueError("No text could be extracted from the PDF")

    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\x00", "")
    text = text.encode("utf-8", "ignore").decode("utf-8")

    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _save_pdf(profile_id: int, pdf_bytes: bytes) -> str:
    """Persist the uploaded PDF under STORAGE_DIR/profiles/<id>/<ts>.pdf and
    return the absolute path. Multiple uploads accumulate; the latest path
    is what gets stored on the row."""
    settings = get_settings()
    profile_dir = settings.storage_dir / "profiles" / str(profile_id)
    profile_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = profile_dir / f"{ts}.pdf"
    target.write_bytes(pdf_bytes)
    return str(target.resolve())


def _persist_pdf_for_profile(
    db: Session, profile: BaselineProfile, pdf_bytes: bytes
) -> BaselineProfile:
    profile.pdf_path = _save_pdf(profile.id, pdf_bytes)
    db.commit()
    db.refresh(profile)
    return profile


def _read_pdf_upload(file: UploadFile) -> bytes:
    """Read the upload stream into memory once. We need the bytes twice:
    parse for text extraction, and persist to disk."""
    max_bytes = get_settings().max_upload_bytes
    pdf_bytes = file.file.read(max_bytes + 1)
    if len(pdf_bytes) > max_bytes:
        raise UploadTooLargeError(len(pdf_bytes), max_bytes)
    return pdf_bytes


def _upload_too_large_response(exc: UploadTooLargeError) -> JSONResponse:
    return error(
        "payload_too_large",
        "Uploaded PDF exceeds the configured size limit.",
        status_code=413,
        details={"actual_bytes": exc.actual_bytes, "max_bytes": exc.max_bytes},
    )


# ---------------------------------------------------------------------------
# Multi-profile CRUD  (/api/profiles)
# ---------------------------------------------------------------------------

@router.get("/profiles")
def list_profiles_endpoint(db: Session = Depends(get_db)) -> JSONResponse:
    profiles = list_profiles(db)
    return success([ProfileOut.model_validate(p).model_dump(mode="json") for p in profiles])


@router.post("/profiles")
def create_profile_endpoint(body: ProfileIn, db: Session = Depends(get_db)) -> JSONResponse:
    try:
        profile = create_profile(db, body.skills_text, body.name, body.is_default)
    except ValueError as exc:
        return error("invalid_input", str(exc), status_code=400)
    return success(ProfileOut.model_validate(profile).model_dump(mode="json"))


@router.post("/profiles/upload")
def upload_profile_pdf(
    file: UploadFile = File(...),
    name: str | None = Form(None),
    skills_text: str | None = Form(None),
    is_default: bool = Form(False),
    db: Session = Depends(get_db),
) -> JSONResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return error("invalid_input", "Only PDF files are accepted", status_code=400)
    try:
        pdf_bytes = _read_pdf_upload(file)
    except UploadTooLargeError as exc:
        return _upload_too_large_response(exc)
    try:
        extracted_text = _extract_pdf_text(pdf_bytes)
    except Exception as exc:
        logger.error("pdf_extraction_failed reason=%s", type(exc).__name__)
        logger.debug("pdf_extraction_failed detail", exc_info=True)
        return error(
            "pdf_error",
            "Could not extract text from PDF. Please check the file format.",
            status_code=422,
        )
    try:
        profile = create_profile(db, skills_text or extracted_text, name, is_default)
    except ValueError as exc:
        return error("invalid_input", str(exc), status_code=400)
    profile = _persist_pdf_for_profile(db, profile, pdf_bytes)
    return success(ProfileOut.model_validate(profile).model_dump(mode="json"))


@router.post("/profiles/upload/preview")
def preview_profile_pdf(file: UploadFile = File(...)) -> JSONResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return error("invalid_input", "Only PDF files are accepted", status_code=400)
    try:
        pdf_bytes = _read_pdf_upload(file)
    except UploadTooLargeError as exc:
        return _upload_too_large_response(exc)
    try:
        skills_text = _extract_pdf_text(pdf_bytes)
    except Exception as exc:
        logger.error("pdf_extraction_failed reason=%s", type(exc).__name__)
        logger.debug("pdf_extraction_failed detail", exc_info=True)
        return error(
            "pdf_error",
            "Could not extract text from PDF. Please check the file format.",
            status_code=422,
        )
    out = ProfilePdfPreviewOut(filename=file.filename, skills_text=skills_text)
    return success(out.model_dump(mode="json"))


@router.get("/profiles/{profile_id}")
def get_profile_endpoint(profile_id: int, db: Session = Depends(get_db)) -> JSONResponse:
    profile = get_profile(db, profile_id)
    if profile is None:
        return error("not_found", f"profile {profile_id} not found", status_code=404)
    return success(ProfileOut.model_validate(profile).model_dump(mode="json"))


@router.put("/profiles/{profile_id}/structured")
def put_profile_structured(
    profile_id: int,
    body: dict,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Replace the profile's structured_data JSON in full.

    Body is the JSON object itself (not wrapped). Use null/empty {} to clear.
    """
    profile = get_profile(db, profile_id)
    if profile is None:
        return error("not_found", f"profile {profile_id} not found", status_code=404)
    profile.structured_data = body or None
    db.commit()
    db.refresh(profile)
    return success(ProfileOut.model_validate(profile).model_dump(mode="json"))


@router.post("/profiles/{profile_id}/structured/extract")
def extract_profile_structured(
    profile_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Use the active LLM to parse skills_text into a structured JSON object,
    save the result on the profile, and return the new profile row.

    Idempotent — overwrites previous structured_data on every call.
    """
    profile = get_profile(db, profile_id)
    if profile is None:
        return error("not_found", f"profile {profile_id} not found", status_code=404)

    llm = request.app.state.llm_client
    if not hasattr(llm, "extract_structured"):
        return error(
            "not_available",
            "Active LLM backend does not implement extract_structured().",
            status_code=503,
        )
    prompt_version = prompt_version_for_step(STEP_EXTRACT)
    backend, model = llm_metadata(llm)
    input_hash = stable_payload_hash(
        {
            "step": STEP_EXTRACT,
            "profile_id": profile.id,
            "skills_text": profile.skills_text,
            "prompt_version": prompt_version,
        }
    )
    started = time.perf_counter()
    try:
        extract_structured = llm.extract_structured
        kwargs: dict[str, object] = {}
        if "prompt_version" in inspect.signature(extract_structured).parameters:
            kwargs["prompt_version"] = prompt_version
        extracted = validate_structured_extraction_output(
            extract_structured(profile.skills_text, **kwargs),
            source=llm.__class__.__name__,
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        record_llm_audit_log(
            db,
            workflow_step=STEP_EXTRACT,
            backend=backend,
            model=model,
            prompt_version=prompt_version,
            input_hash=input_hash,
            latency_ms=latency_ms,
            status=STATUS_FAILED,
            error_code=error_code_for_exception(exc),
            error_message=error_message_for_exception(exc),
            request_id=getattr(request.state, "request_id", None),
            baseline_profile_id=profile.id,
        )
        logger.exception("structured_extract_failed profile_id=%s", profile_id)
        return error("llm_invalid_output", str(exc), status_code=502)
    latency_ms = int((time.perf_counter() - started) * 1000)

    profile.structured_data = extracted
    db.commit()
    db.refresh(profile)
    record_llm_audit_log(
        db,
        workflow_step=STEP_EXTRACT,
        backend=backend,
        model=model,
        prompt_version=prompt_version,
        input_hash=input_hash,
        output_hash=stable_payload_hash(extracted),
        latency_ms=latency_ms,
        status=STATUS_SUCCEEDED,
        request_id=getattr(request.state, "request_id", None),
        baseline_profile_id=profile.id,
    )
    return success(ProfileOut.model_validate(profile).model_dump(mode="json"))


@router.get("/profiles/{profile_id}/pdf", response_model=None)
def get_profile_pdf(
    profile_id: int,
    db: Session = Depends(get_db),
) -> FileResponse | JSONResponse:
    profile = get_profile(db, profile_id)
    if profile is None:
        return error("not_found", f"profile {profile_id} not found", status_code=404)
    if not profile.pdf_path:
        return error("not_found", "profile has no uploaded PDF", status_code=404)
    # Defense-in-depth: pdf_path comes from the DB and should already point
    # under storage_dir, but resolve the symlink chain and check containment
    # so a poisoned row can't escape via `..` or an absolute path.
    storage_root = Path(get_settings().storage_dir).resolve()
    try:
        path = Path(profile.pdf_path).resolve()
        path.relative_to(storage_root)
    except (OSError, ValueError):
        logger.error(
            "profile_pdf_path_outside_storage profile_id=%s",
            profile_id,
        )
        return error("not_found", "profile PDF file is missing on disk", status_code=404)
    if not path.exists():
        return error("not_found", "profile PDF file is missing on disk", status_code=404)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"baseline-profile-{profile.id}.pdf",
    )


@router.put("/profiles/{profile_id}")
def update_profile_endpoint(
    profile_id: int,
    body: ProfileUpdateIn,
    db: Session = Depends(get_db),
) -> JSONResponse:
    try:
        profile = update_profile(
            db,
            profile_id,
            body.skills_text,
            body.name,
            body.is_default,
        )
    except LookupError as exc:
        return error("not_found", str(exc), status_code=404)
    except ValueError as exc:
        return error("invalid_input", str(exc), status_code=400)
    return success(ProfileOut.model_validate(profile).model_dump(mode="json"))


@router.get("/profiles/{profile_id}/delete-impact")
def profile_delete_impact(profile_id: int, db: Session = Depends(get_db)) -> JSONResponse:
    if get_profile(db, profile_id) is None:
        return error("not_found", f"profile {profile_id} not found", status_code=404)
    job_count = db.query(JobAnalysis).filter(JobAnalysis.profile_id == profile_id).count()
    resume_count = (
        db.query(GeneratedResume)
        .join(JobAnalysis, GeneratedResume.job_analysis_id == JobAnalysis.id)
        .filter(JobAnalysis.profile_id == profile_id)
        .count()
    )
    out = ProfileDeleteImpactOut(
        profile_id=profile_id,
        job_analyses_count=job_count,
        generated_resumes_count=resume_count,
    )
    return success(out.model_dump(mode="json"))


@router.delete("/profiles/{profile_id}")
def delete_profile_endpoint(profile_id: int, db: Session = Depends(get_db)) -> JSONResponse:
    try:
        delete_profile(db, profile_id)
    except LookupError as exc:
        return error("not_found", str(exc), status_code=404)
    return success({"deleted": profile_id})


# ---------------------------------------------------------------------------
# Backward-compat singular endpoints (/api/profile)
# ---------------------------------------------------------------------------

@router.post("/profile")
def set_profile_legacy(body: ProfileIn, db: Session = Depends(get_db)) -> JSONResponse:
    try:
        profile = create_profile(db, body.skills_text, body.name, body.is_default)
    except ValueError as exc:
        logger.error("set_profile failed: %s", exc, exc_info=True)
        return error("invalid_input", str(exc), status_code=400)
    return success(ProfileOut.model_validate(profile).model_dump(mode="json"))


@router.post("/profile/upload")
def upload_profile_legacy(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> JSONResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return error("invalid_input", "Only PDF files are accepted", status_code=400)
    try:
        pdf_bytes = _read_pdf_upload(file)
    except UploadTooLargeError as exc:
        return _upload_too_large_response(exc)
    try:
        skills_text = _extract_pdf_text(pdf_bytes)
    except Exception as exc:
        logger.error("pdf_extraction_failed reason=%s", type(exc).__name__)
        logger.debug("pdf_extraction_failed detail", exc_info=True)
        return error("pdf_error", "Could not read PDF.", status_code=422)
    try:
        profile = create_profile(db, skills_text)
    except ValueError as exc:
        return error("invalid_input", str(exc), status_code=400)
    profile = _persist_pdf_for_profile(db, profile, pdf_bytes)
    return success(ProfileOut.model_validate(profile).model_dump(mode="json"))


@router.get("/profile")
def get_profile_legacy(db: Session = Depends(get_db)) -> JSONResponse:
    profile = get_default_profile(db)
    if profile is None:
        return error("not_found", "No baseline profile set yet", status_code=404)
    return success(ProfileOut.model_validate(profile).model_dump(mode="json"))
