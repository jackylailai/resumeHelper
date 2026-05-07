from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.app.api.envelope import error, success
from backend.app.config import get_settings
from backend.app.db import get_db
from backend.app.models.evaluation_job import EvaluationJob
from backend.app.models.resume import Resume
from backend.app.models.resume_version import ResumeVersion
from backend.app.schemas.evaluation import EvaluationOut, JobOut
from backend.app.schemas.resume import ResumeOut, ResumeVersionOut
from backend.app.services import hashing, parsing, storage
from backend.app.services.llm import LLMClient
from backend.app.services.parsing import NoExtractableTextError
from backend.app.workers.tasks import enqueue_evaluation

router = APIRouter()

_ALLOWED_EXTENSIONS = {"pdf", "docx"}
_VERSION_CAP = 50


def _get_llm(request: Request) -> LLMClient:
    return request.app.state.llm_client  # type: ignore[no-any-return]


@router.post("/resumes")
async def upload_resume(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    job_description: str = Form(...),
    resume_id: uuid.UUID | None = Form(default=None),
    db: Session = Depends(get_db),
) -> JSONResponse:
    settings = get_settings()
    llm = _get_llm(request)

    # --- Validate extension ---
    filename = file.filename or ""
    ext = Path(filename).suffix.lstrip(".").lower()
    if ext not in _ALLOWED_EXTENSIONS:
        return error(
            "unsupported_format",
            f"Only pdf and docx are accepted, got {ext!r}",
            status_code=415,
        )

    # --- Read and validate size ---
    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        return error(
            "file_too_large",
            f"File exceeds {settings.max_upload_bytes} bytes limit",
            status_code=413,
        )

    # --- Validate magic bytes ---
    try:
        text = parsing.parse(data, ext)
    except NoExtractableTextError:
        return error(
            "no_extractable_text",
            "No parseable text found. Scanned-image files are not supported.",
            status_code=422,
        )
    except ValueError as exc:
        return error("unsupported_format", str(exc), status_code=415)

    # --- Hashing ---
    cv_hash = hashing.content_hash(text)
    fhash = storage.file_hash(data)
    prompt_version = settings.llm_prompt_version

    # --- Validate resume_id if provided ---
    if resume_id is not None:
        existing_resume = db.get(Resume, resume_id)
        if existing_resume is None:
            return error("not_found", f"Resume {resume_id} not found", status_code=404)

    # --- Cache check ---
    from backend.app.services.evaluator import check_cache
    cached_eval = check_cache(db, cv_hash, job_description, prompt_version)
    if cached_eval:
        try:
            _create_version(db, data, fhash, ext, cv_hash, text, resume_id, filename)
        except ValueError as exc:
            return error("version_cap_exceeded", str(exc), status_code=422)
        return success(
            EvaluationOut.model_validate(cached_eval).model_dump(mode="json"),
            cached=True,
            status="succeeded",
        )

    # --- Persist version ---
    try:
        version = _create_version(db, data, fhash, ext, cv_hash, text, resume_id, filename)
    except ValueError as exc:
        return error("version_cap_exceeded", str(exc), status_code=422)

    # --- Evaluate synchronously (small/fast) or async ---
    version._job_description = job_description  # passed through to worker

    job = EvaluationJob(
        id=uuid.uuid4(),
        resume_version_id=version.id,
        jd_hash=hashing.jd_hash(job_description),
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.commit()

    background_tasks.add_task(enqueue_evaluation, job.id, llm)

    return success(
        JobOut.model_validate(job).model_dump(mode="json"),
        status_code=202,
        status="pending",
    )


@router.get("/resumes")
def list_resumes(db: Session = Depends(get_db)) -> JSONResponse:
    from backend.app.models.resume import Resume as ResumeModel
    from backend.app.models.resume_evaluation import ResumeEvaluation

    resumes = db.query(ResumeModel).order_by(ResumeModel.updated_at.desc()).limit(100).all()
    result = []
    for resume in resumes:
        data = ResumeOut.model_validate(resume).model_dump(mode="json")
        latest_version = (
            db.query(ResumeVersion)
            .filter(ResumeVersion.resume_id == resume.id)
            .order_by(ResumeVersion.version_number.desc())
            .first()
        )
        if latest_version:
            data["latest_version_number"] = latest_version.version_number
            latest_eval = (
                db.query(ResumeEvaluation)
                .filter(ResumeEvaluation.resume_version_id == latest_version.id)
                .order_by(ResumeEvaluation.created_at.desc())
                .first()
            )
            if latest_eval:
                data["latest_score"] = latest_eval.score
        result.append(data)
    return success(result)


@router.get("/resumes/{resume_id}/versions")
def list_versions(resume_id: uuid.UUID, db: Session = Depends(get_db)) -> JSONResponse:
    from backend.app.models.resume import Resume as ResumeModel
    from backend.app.models.resume_version import ResumeVersion as RV

    resume = db.get(ResumeModel, resume_id)
    if resume is None:
        return error("not_found", f"Resume {resume_id} not found", status_code=404)

    versions = (
        db.query(RV)
        .filter(RV.resume_id == resume_id)
        .order_by(RV.version_number.desc())
        .all()
    )
    return success([ResumeVersionOut.model_validate(v).model_dump(mode="json") for v in versions])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_version(
    db: Session,
    data: bytes,
    fhash: str,
    ext: str,
    cv_hash: str,
    text: str,
    resume_id: uuid.UUID | None,
    filename: str,
) -> ResumeVersion:
    now = datetime.now(timezone.utc)

    if resume_id is None:
        resume = Resume(
            id=uuid.uuid4(),
            display_name=filename or "Unnamed Resume",
            created_at=now,
            updated_at=now,
        )
        db.add(resume)
        db.flush()
        resume_id = resume.id
    else:
        resume = db.get(Resume, resume_id)
        if resume is None:
            raise ValueError(f"Resume {resume_id} not found")
        resume.updated_at = now

    # Version cap
    existing_count = (
        db.query(ResumeVersion).filter(ResumeVersion.resume_id == resume_id).count()
    )
    if existing_count >= _VERSION_CAP:
        raise ValueError(f"Version cap of {_VERSION_CAP} reached for resume {resume_id}")

    version_number = existing_count + 1
    rel_path = storage.save(data, fhash, ext)

    version = ResumeVersion(
        id=uuid.uuid4(),
        resume_id=resume_id,
        version_number=version_number,
        content_hash=cv_hash,
        file_hash=fhash,
        file_format=ext,
        file_size_bytes=len(data),
        storage_path=rel_path,
        parsed_text=text,
        uploaded_at=now,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version
