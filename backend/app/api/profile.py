from __future__ import annotations
import logging

from fastapi import APIRouter, Depends, UploadFile, File
from fastapi.responses import JSONResponse
from pypdf import PdfReader
from sqlalchemy.orm import Session

from backend.app.api.envelope import error, success
from backend.app.db import get_db
from backend.app.schemas.profile import ProfileIn, ProfileOut
from backend.app.services.evaluator_v2 import get_baseline, upsert_baseline

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/profile")
def set_profile(body: ProfileIn, db: Session = Depends(get_db)) -> JSONResponse:
    try:
        profile = upsert_baseline(db, body.skills_text)
    except ValueError as exc:
        logger.error("set_profile failed: %s", exc, exc_info=True)
        return error("invalid_input", str(exc), status_code=400)
    return success(ProfileOut.model_validate(profile).model_dump(mode="json"))


@router.post("/profile/upload")
def upload_profile_pdf(file: UploadFile = File(...), db: Session = Depends(get_db)) -> JSONResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return error("invalid_input", "Only PDF files are accepted", status_code=400)
    try:
        reader = PdfReader(file.file)
        pages = [page.extract_text() or "" for page in reader.pages]
        skills_text = "\n".join(pages).strip()
    except Exception as exc:
        logger.error("PDF extraction failed: %s", exc, exc_info=True)
        return error("pdf_error", f"Could not read PDF: {exc}", status_code=422)
    if not skills_text:
        return error("invalid_input", "No text could be extracted from the PDF", status_code=422)
    try:
        profile = upsert_baseline(db, skills_text)
    except ValueError as exc:
        logger.error("upload_profile_pdf upsert failed: %s", exc, exc_info=True)
        return error("invalid_input", str(exc), status_code=400)
    return success(ProfileOut.model_validate(profile).model_dump(mode="json"))


@router.get("/profile")
def get_profile(db: Session = Depends(get_db)) -> JSONResponse:
    profile = get_baseline(db)
    if profile is None:
        return error("not_found", "No baseline profile set yet", status_code=404)
    return success(ProfileOut.model_validate(profile).model_dump(mode="json"))
