from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models.ai_job import AIJob
from backend.app.models.generated_resume import GeneratedResume
from backend.app.services import hashing

logger = logging.getLogger(__name__)

AI_JOB_KIND_TAILOR = "tailor"
AI_JOB_KIND_EVALUATE = "evaluate"

AI_JOB_STATUS_QUEUED = "queued"
AI_JOB_STATUS_RETRY_WAIT = "retry_wait"
AI_JOB_STATUS_RUNNING = "running"
AI_JOB_STATUS_SUCCEEDED = "succeeded"
AI_JOB_STATUS_FAILED = "failed"
AI_JOB_STATUS_CANCEL_REQUESTED = "cancel_requested"
AI_JOB_STATUS_CANCELLED = "cancelled"

CLAIMABLE_JOB_STATUSES = (
    AI_JOB_STATUS_QUEUED,
    AI_JOB_STATUS_RETRY_WAIT,
)
TERMINAL_JOB_STATUSES = (
    AI_JOB_STATUS_SUCCEEDED,
    AI_JOB_STATUS_FAILED,
    AI_JOB_STATUS_CANCELLED,
)


class AIJobModelUnavailable(RuntimeError):
    """Retained for API compatibility with queue callers."""


@dataclass(frozen=True)
class TailoringJobRef:
    id: uuid.UUID
    status: str
    created: bool = False


@dataclass(frozen=True)
class EvaluateJobRef:
    id: uuid.UUID
    status: str
    created: bool = False


@dataclass(frozen=True)
class ClaimedAIJob:
    id: uuid.UUID
    kind: str
    dedupe_key: str | None
    status: str
    input_payload: dict[str, Any]


def tailor_dedupe_key(job_analysis_id: uuid.UUID) -> str:
    return f"{AI_JOB_KIND_TAILOR}:{job_analysis_id}"


def evaluate_dedupe_key(
    *,
    profile_id: int,
    prompt_version: str,
    jd_text: str,
) -> str:
    return f"{AI_JOB_KIND_EVALUATE}:{profile_id}:{prompt_version}:{hashing.jd_hash(jd_text)}"


def enqueue_evaluate_job(
    db: Session,
    *,
    jd_text: str,
    profile_id: int,
    prompt_version: str,
    tailor_prompt_version: str,
    request_id: str | None = None,
) -> EvaluateJobRef:
    """Create or reuse a durable single-JD evaluate job."""
    dedupe_key = evaluate_dedupe_key(
        profile_id=profile_id,
        prompt_version=prompt_version,
        jd_text=jd_text,
    )
    existing = _find_job_by_dedupe(db, dedupe_key)
    payload = {
        "jd_text": jd_text,
        "profile_id": profile_id,
        "prompt_version": prompt_version,
        "tailor_prompt_version": tailor_prompt_version,
    }
    if request_id:
        payload["request_id"] = request_id

    if existing is not None:
        if existing.status in {AI_JOB_STATUS_FAILED, AI_JOB_STATUS_CANCELLED}:
            _set_queued_fields(existing, payload=payload)
            existing.profile_id = profile_id
            existing.prompt_version = prompt_version
            existing.request_id = request_id
            existing.progress_current = 0
            existing.progress_total = 1
            db.commit()
            db.refresh(existing)
        elif existing.status in {AI_JOB_STATUS_QUEUED, AI_JOB_STATUS_RETRY_WAIT}:
            _merge_payload(existing, payload)
            existing.profile_id = profile_id
            existing.prompt_version = prompt_version
            if request_id:
                existing.request_id = request_id
            existing.updated_at = datetime.now(UTC)
            db.commit()
            db.refresh(existing)
        return _evaluate_ref(existing, created=False)

    job = AIJob(
        kind=AI_JOB_KIND_EVALUATE,
        dedupe_key=dedupe_key,
        profile_id=profile_id,
        prompt_version=prompt_version,
        request_id=request_id,
        progress_total=1,
    )
    _set_queued_fields(job, payload=payload)
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _find_job_by_dedupe(db, dedupe_key)
        if existing is None:
            raise
        return _evaluate_ref(existing, created=False)
    db.refresh(job)
    logger.info(
        "evaluate_job_queued ai_job_id=%s profile_id=%s",
        job.id,
        profile_id,
    )
    return _evaluate_ref(job, created=True)


def enqueue_tailoring_job(
    db: Session,
    *,
    job_analysis_id: uuid.UUID,
    prompt_version: str | None = None,
    request_id: str | None = None,
) -> TailoringJobRef | None:
    """Create or reuse the durable tailor job for a JobAnalysis.

    If a generated resume already exists and no AIJob exists, there is no work
    to enqueue. If a terminal AIJob exists without a resume, move it back to
    queued so cached needs_tailoring analyses do not get stuck forever.
    """
    existing = _find_tailoring_job(db, job_analysis_id)
    has_resume = _has_generated_resume(db, job_analysis_id)
    payload = _tailor_payload(
        job_analysis_id=job_analysis_id,
        prompt_version=prompt_version,
        request_id=request_id,
    )

    if existing is not None:
        if not has_resume and existing.status in TERMINAL_JOB_STATUSES:
            _set_queued_fields(existing, payload=payload)
            db.commit()
            db.refresh(existing)
            logger.info(
                "tailor_job_requeued ai_job_id=%s job_analysis_id=%s",
                existing.id,
                job_analysis_id,
            )
            return _tailoring_ref(existing, created=False)

        if existing.status in {AI_JOB_STATUS_QUEUED, AI_JOB_STATUS_RETRY_WAIT}:
            _merge_payload(existing, payload)
            if prompt_version:
                existing.prompt_version = prompt_version
            if request_id:
                existing.request_id = request_id
            existing.updated_at = datetime.now(UTC)
            db.commit()
            db.refresh(existing)
        return _tailoring_ref(existing, created=False)

    if has_resume:
        return None

    job = AIJob(
        kind=AI_JOB_KIND_TAILOR,
        dedupe_key=tailor_dedupe_key(job_analysis_id),
        job_analysis_id=job_analysis_id,
        prompt_version=prompt_version,
        request_id=request_id,
    )
    _set_queued_fields(job, payload=payload)
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _find_tailoring_job(db, job_analysis_id)
        if existing is None:
            raise
        return _tailoring_ref(existing, created=False)
    db.refresh(job)
    logger.info(
        "tailor_job_queued ai_job_id=%s job_analysis_id=%s",
        job.id,
        job_analysis_id,
    )
    return _tailoring_ref(job, created=True)


def get_tailoring_job_ref(
    db: Session,
    *,
    job_analysis_id: uuid.UUID,
) -> TailoringJobRef | None:
    job = _find_tailoring_job(db, job_analysis_id)
    if job is None:
        return None
    return _tailoring_ref(job, created=False)


def claim_next_job(
    db: Session,
    *,
    kind: str | None = None,
    now: datetime | None = None,
) -> ClaimedAIJob | None:
    """Claim one queued job using FOR UPDATE SKIP LOCKED.

    The transaction is committed before returning so handlers can perform slow
    LLM work without holding row locks.
    """
    now = now or datetime.now(UTC)
    stmt = select(AIJob).where(
        AIJob.status.in_(CLAIMABLE_JOB_STATUSES),
        AIJob.run_after <= now,
    )
    if kind is not None:
        stmt = stmt.where(AIJob.kind == kind)
    stmt = stmt.order_by(
        AIJob.priority.desc(),
        AIJob.run_after.asc(),
        AIJob.created_at.asc(),
        AIJob.id.asc(),
    ).with_for_update(skip_locked=True)

    job = db.execute(stmt).scalars().first()
    if job is None:
        db.rollback()
        return None

    job.status = AI_JOB_STATUS_RUNNING
    job.started_at = now
    job.locked_at = now
    job.updated_at = now
    job.attempts = (job.attempts or 0) + 1
    _clear_error_fields(job)
    db.commit()
    db.refresh(job)
    return _claimed_job(job)


def mark_job_succeeded(
    db: Session,
    *,
    job_id: uuid.UUID,
    result: dict[str, Any] | None = None,
) -> TailoringJobRef | None:
    job = db.get(AIJob, job_id)
    if job is None:
        return None
    _set_terminal_fields(job, AI_JOB_STATUS_SUCCEEDED)
    if result is not None:
        job.result_payload = result
        job_analysis_id = result.get("job_analysis_id")
        if job_analysis_id:
            job.job_analysis_id = uuid.UUID(str(job_analysis_id))
        generated_resume_id = result.get("generated_resume_id")
        if generated_resume_id:
            job.generated_resume_id = uuid.UUID(str(generated_resume_id))
    if job.progress_total is not None:
        job.progress_current = job.progress_total
    db.commit()
    db.refresh(job)
    return _tailoring_ref(job, created=False)


def mark_job_failed(
    db: Session,
    *,
    job_id: uuid.UUID,
    error_code: str,
    error_message: str,
) -> TailoringJobRef | None:
    job = db.get(AIJob, job_id)
    if job is None:
        return None
    if job.status == AI_JOB_STATUS_CANCEL_REQUESTED:
        _set_terminal_fields(job, AI_JOB_STATUS_CANCELLED)
    elif (job.attempts or 0) < (job.max_attempts or 1):
        _set_retry_wait_fields(
            job,
            error_code=error_code,
            error_message=error_message,
        )
    else:
        _set_terminal_fields(
            job,
            AI_JOB_STATUS_FAILED,
            error_code=error_code,
            error_message=error_message,
        )
    db.commit()
    db.refresh(job)
    return _tailoring_ref(job, created=False)


def mark_job_cancelled(
    db: Session,
    *,
    job_id: uuid.UUID,
) -> TailoringJobRef | None:
    job = db.get(AIJob, job_id)
    if job is None:
        return None
    _set_terminal_fields(job, AI_JOB_STATUS_CANCELLED)
    db.commit()
    db.refresh(job)
    return _tailoring_ref(job, created=False)


def is_cancel_requested(db: Session, *, job_id: uuid.UUID) -> bool:
    job = db.get(AIJob, job_id)
    if job is None:
        return False
    return job.status == AI_JOB_STATUS_CANCEL_REQUESTED


def job_analysis_id_from_claim(claimed: ClaimedAIJob) -> uuid.UUID:
    raw = claimed.input_payload.get("job_analysis_id")
    if raw:
        return uuid.UUID(str(raw))
    prefix = f"{AI_JOB_KIND_TAILOR}:"
    if claimed.dedupe_key and claimed.dedupe_key.startswith(prefix):
        return uuid.UUID(claimed.dedupe_key[len(prefix) :])
    raise ValueError(f"tailor ai_job {claimed.id} is missing job_analysis_id")


def _find_tailoring_job(
    db: Session,
    job_analysis_id: uuid.UUID,
) -> AIJob | None:
    return (
        db.query(AIJob)
        .filter(
            AIJob.kind == AI_JOB_KIND_TAILOR,
            AIJob.dedupe_key == tailor_dedupe_key(job_analysis_id),
        )
        .order_by(AIJob.created_at.desc())
        .first()
    )


def _find_job_by_dedupe(db: Session, dedupe_key: str) -> AIJob | None:
    return (
        db.query(AIJob)
        .filter(AIJob.dedupe_key == dedupe_key)
        .order_by(AIJob.created_at.desc())
        .first()
    )


def _has_generated_resume(db: Session, job_analysis_id: uuid.UUID) -> bool:
    return (
        db.query(GeneratedResume.id)
        .filter(GeneratedResume.job_analysis_id == job_analysis_id)
        .first()
        is not None
    )


def _tailor_payload(
    *,
    job_analysis_id: uuid.UUID,
    prompt_version: str | None,
    request_id: str | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"job_analysis_id": str(job_analysis_id)}
    if prompt_version:
        payload["prompt_version"] = prompt_version
    if request_id:
        payload["request_id"] = request_id
    return payload


def _set_queued_fields(job: AIJob, *, payload: dict[str, Any]) -> None:
    now = datetime.now(UTC)
    job.status = AI_JOB_STATUS_QUEUED
    job.run_after = now
    job.started_at = None
    job.finished_at = None
    job.locked_at = None
    job.locked_by = None
    job.updated_at = now
    _clear_error_fields(job)
    _merge_payload(job, payload)


def _set_terminal_fields(
    job: AIJob,
    status: str,
    *,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    now = datetime.now(UTC)
    job.status = status
    job.finished_at = now
    job.locked_at = None
    job.locked_by = None
    job.updated_at = now
    if error_code or error_message:
        job.error_code = error_code
        job.error_message = error_message


def _set_retry_wait_fields(
    job: AIJob,
    *,
    error_code: str,
    error_message: str,
) -> None:
    now = datetime.now(UTC)
    backoff_seconds = min(60 * (2 ** max((job.attempts or 1) - 1, 0)), 900)
    job.status = AI_JOB_STATUS_RETRY_WAIT
    job.run_after = now + timedelta(seconds=backoff_seconds)
    job.finished_at = None
    job.locked_at = None
    job.locked_by = None
    job.updated_at = now
    job.error_code = error_code
    job.error_message = error_message


def _clear_error_fields(job: AIJob) -> None:
    job.error_code = None
    job.error_message = None


def _merge_payload(job: AIJob, payload: dict[str, Any]) -> None:
    current = job.input_payload
    if not isinstance(current, dict):
        current = {}
    job.input_payload = {**current, **payload}


def _claimed_job(job: AIJob) -> ClaimedAIJob:
    return ClaimedAIJob(
        id=job.id,
        kind=job.kind,
        dedupe_key=job.dedupe_key,
        status=job.status,
        input_payload=job.input_payload if isinstance(job.input_payload, dict) else {},
    )


def _tailoring_ref(job: AIJob, *, created: bool) -> TailoringJobRef:
    return TailoringJobRef(id=job.id, status=job.status, created=created)


def _evaluate_ref(job: AIJob, *, created: bool) -> EvaluateJobRef:
    return EvaluateJobRef(id=job.id, status=job.status, created=created)
