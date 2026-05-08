from __future__ import annotations

import io
import logging
import unicodedata
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse
from pypdf import PdfReader
from sqlalchemy.orm import Session

from backend.app.api.envelope import error, success
from backend.app.config import get_settings
from backend.app.db import get_db
from backend.app.models.baseline_profile import BaselineProfile
from backend.app.schemas.profile import ProfileIn, ProfileOut, ProfileUpdateIn
from backend.app.services.evaluator_v2 import (
    create_profile,
    delete_profile,
    get_latest_profile,
    get_profile,
    list_profiles,
    update_profile,
)

logger = logging.getLogger(__name__)
router = APIRouter()


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
    return file.file.read()


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
        profile = create_profile(db, body.skills_text, body.name)
    except ValueError as exc:
        return error("invalid_input", str(exc), status_code=400)
    return success(ProfileOut.model_validate(profile).model_dump(mode="json"))


@router.post("/profiles/upload")
def upload_profile_pdf(
    file: UploadFile = File(...),
    name: str | None = Form(None),
    db: Session = Depends(get_db),
) -> JSONResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return error("invalid_input", "Only PDF files are accepted", status_code=400)
    pdf_bytes = _read_pdf_upload(file)
    try:
        skills_text = _extract_pdf_text(pdf_bytes)
    except Exception as exc:
        logger.error("PDF extraction failed: %s", exc, exc_info=True)
        return error(
            "pdf_error",
            "Could not extract text from PDF. Please check the file format.",
            status_code=422,
        )
    try:
        profile = create_profile(db, skills_text, name)
    except ValueError as exc:
        return error("invalid_input", str(exc), status_code=400)
    profile = _persist_pdf_for_profile(db, profile, pdf_bytes)
    return success(ProfileOut.model_validate(profile).model_dump(mode="json"))


@router.get("/profiles/{profile_id}")
def get_profile_endpoint(profile_id: int, db: Session = Depends(get_db)) -> JSONResponse:
    profile = get_profile(db, profile_id)
    if profile is None:
        return error("not_found", f"profile {profile_id} not found", status_code=404)
    return success(ProfileOut.model_validate(profile).model_dump(mode="json"))


@router.put("/profiles/{profile_id}")
def update_profile_endpoint(
    profile_id: int,
    body: ProfileUpdateIn,
    db: Session = Depends(get_db),
) -> JSONResponse:
    try:
        profile = update_profile(db, profile_id, body.skills_text, body.name)
    except LookupError as exc:
        return error("not_found", str(exc), status_code=404)
    except ValueError as exc:
        return error("invalid_input", str(exc), status_code=400)
    return success(ProfileOut.model_validate(profile).model_dump(mode="json"))


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
        profile = create_profile(db, body.skills_text, body.name)
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
    pdf_bytes = _read_pdf_upload(file)
    try:
        skills_text = _extract_pdf_text(pdf_bytes)
    except Exception as exc:
        logger.error("PDF extraction failed: %s", exc, exc_info=True)
        return error("pdf_error", f"Could not read PDF: {exc}", status_code=422)
    try:
        profile = create_profile(db, skills_text)
    except ValueError as exc:
        return error("invalid_input", str(exc), status_code=400)
    profile = _persist_pdf_for_profile(db, profile, pdf_bytes)
    return success(ProfileOut.model_validate(profile).model_dump(mode="json"))


@router.get("/profile")
def get_profile_legacy(db: Session = Depends(get_db)) -> JSONResponse:
    profile = get_latest_profile(db)
    if profile is None:
        return error("not_found", "No baseline profile set yet", status_code=404)
    return success(ProfileOut.model_validate(profile).model_dump(mode="json"))
