"""Background tailoring task for the three-tier resume evaluation system.

For jobs with status='needs_tailoring' (score 60-84), this task:
1. Calls the LLM to analyze gaps and generate a tailored resume text
2. Saves the GeneratedResume record to DB
3. Marks the JobAnalysis as can_submit=True
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from backend.app.config import get_settings
from backend.app.models.baseline_profile import BaselineProfile
from backend.app.models.generated_resume import GeneratedResume
from backend.app.models.job_analysis import STATUS_NEEDS_TAILORING, JobAnalysis
from backend.app.services.llm import LLMClient, LLMInvalidOutputError
from backend.app.services.llm.audit import (
    STATUS_FAILED,
    STATUS_SUCCEEDED,
    error_code_for_exception,
    error_message_for_exception,
    llm_metadata,
    record_llm_audit_log,
    stable_payload_hash,
)
from backend.app.services.llm.contracts import validate_tailor_output
from backend.app.services.llm.prompt_registry import STEP_TAILOR, prompt_version_for_step
from backend.app.services.pdf import write_generated_resume_pdf
from backend.app.services.proof_points import (
    format_proof_points_for_prompt,
    select_relevant_proof_points,
)

logger = logging.getLogger(__name__)

TAILORING_STATUS_SUCCEEDED = "succeeded"
TAILORING_STATUS_FAILED = "failed"


@dataclass(frozen=True)
class TailoringResult:
    job_analysis_id: uuid.UUID
    status: str
    generated_resume_id: uuid.UUID | None = None
    error_code: str | None = None
    error_message: str | None = None


class TailoringError(RuntimeError):
    def __init__(self, error_code: str, error_message: str) -> None:
        super().__init__(error_message)
        self.error_code = error_code
        self.error_message = error_message


def _get_default_session_factory() -> Any:
    """Return the module-level SessionLocal, imported lazily to allow test override."""
    from backend.app.db import SessionLocal

    return SessionLocal


def run_tailoring(
    job_analysis_id: uuid.UUID,
    llm: LLMClient,
    prompt_version: str | None = None,
    session_factory: Callable | None = None,
    request_id: str | None = None,
    cancel_requested: Callable[[], bool] | None = None,
) -> TailoringResult:
    """Run one tailoring job and return a structured outcome.

    Args:
        job_analysis_id: The UUID of the JobAnalysis to tailor.
        llm: The LLM client to use for tailoring.
        prompt_version: Tag stored on the GeneratedResume.
        session_factory: Optional SQLAlchemy sessionmaker; defaults to app SessionLocal.
                         Pass a test-scoped factory in tests for proper DB isolation.
    """
    if session_factory is None:
        session_factory = _get_default_session_factory()
    prompt_version = prompt_version_for_step(STEP_TAILOR, override=prompt_version)

    with session_factory() as db:
        job = db.get(JobAnalysis, job_analysis_id)
        if job is None:
            logger.error("tailor_job_not_found job_id=%s", job_analysis_id)
            return _tailoring_failure(
                job_analysis_id,
                "job_analysis_not_found",
                f"job_analysis {job_analysis_id} not found",
            )

        if job.status != STATUS_NEEDS_TAILORING:
            logger.warning(
                "tailor_skip_wrong_status job_id=%s status=%s",
                job_analysis_id,
                job.status,
            )
            return _tailoring_failure(
                job_analysis_id,
                "invalid_job_status",
                f"job_analysis {job_analysis_id} status is {job.status}",
            )

        logger.info("tailor_start job_id=%s score=%s", job_analysis_id, job.score)
        if job.profile_id:
            baseline = db.get(BaselineProfile, job.profile_id)
        else:
            # Older JobAnalysis rows can have profile_id=None. Prefer the
            # explicitly-defaulted profile over "latest by id" so a user who
            # marked one profile as default doesn't suddenly get tailored
            # against whatever they uploaded most recently.
            from backend.app.services.evaluator_v2 import get_default_profile

            baseline = get_default_profile(db)
        if baseline is None:
            logger.error("tailor_no_baseline job_id=%s", job_analysis_id)
            return _tailoring_failure(
                job_analysis_id,
                "baseline_profile_not_found",
                "baseline_profile not set",
            )
        if _is_cancelled(job_analysis_id, cancel_requested):
            return _tailoring_failure(
                job_analysis_id,
                "job_cancelled",
                "tailoring job was cancelled",
            )

        baseline_text = baseline.skills_text
        structured_data = baseline.structured_data
        proof_points = select_relevant_proof_points(
            db,
            profile_id=baseline.id,
            jd_text=job.jd_full_text,
            gaps=job.gaps or [],
        )
        proof_points_text = format_proof_points_for_prompt(proof_points)
        proof_point_ids = [str(proof_point.id) for proof_point in proof_points]

        backend, model = llm_metadata(llm)
        input_hash = stable_payload_hash(
            {
                "step": STEP_TAILOR,
                "job_analysis_id": job_analysis_id,
                "baseline_text": baseline_text,
                "structured_data": structured_data,
                "jd_text": job.jd_full_text,
                "gaps": job.gaps or [],
                "score": job.score or 0,
                "prompt_version": prompt_version,
                "proof_point_ids": proof_point_ids,
                "proof_points": proof_points_text,
            }
        )
        started = time.perf_counter()
        try:
            result = _call_tailor_llm(
                llm,
                job,
                baseline_text,
                structured_data,
                proof_points_text,
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            record_llm_audit_log(
                db,
                workflow_step=STEP_TAILOR,
                backend=backend,
                model=model,
                prompt_version=prompt_version,
                input_hash=input_hash,
                latency_ms=latency_ms,
                status=STATUS_FAILED,
                error_code=error_code_for_exception(exc),
                error_message=error_message_for_exception(exc),
                request_id=request_id,
                baseline_profile_id=baseline.id,
                job_analysis_id=job_analysis_id,
            )
            logger.error("tailor_llm_failed job_id=%s error=%s", job_analysis_id, exc)
            return _tailoring_failure(
                job_analysis_id,
                error_code_for_exception(exc),
                error_message_for_exception(exc),
            )
        latency_ms = int((time.perf_counter() - started) * 1000)
        if _is_cancelled(job_analysis_id, cancel_requested):
            return _tailoring_failure(
                job_analysis_id,
                "job_cancelled",
                "tailoring job was cancelled",
            )

        try:
            if _is_cancelled(job_analysis_id, cancel_requested):
                return _tailoring_failure(
                    job_analysis_id,
                    "job_cancelled",
                    "tailoring job was cancelled",
                )
            resume = GeneratedResume(
                job_analysis_id=job_analysis_id,
                resume_text=result["tailored_resume"],
                pdf_url=None,
                prompt_version=prompt_version,
                llm_backend=backend,
                llm_model=model,
                proof_point_ids=proof_point_ids,
            )
            db.add(resume)
            db.flush()

            write_generated_resume_pdf(
                get_settings().storage_dir,
                resume.id,
                resume.resume_text,
            )
            if _is_cancelled(job_analysis_id, cancel_requested):
                db.rollback()
                return _tailoring_failure(
                    job_analysis_id,
                    "job_cancelled",
                    "tailoring job was cancelled",
                )
            resume.pdf_url = f"/api/generated-resumes/{resume.id}/pdf"

            job.can_submit = True
            db.commit()
            db.refresh(resume)
        except Exception as exc:
            db.rollback()
            logger.exception("tailor_persist_failed job_id=%s", job_analysis_id)
            return _tailoring_failure(
                job_analysis_id,
                "tailor_persist_failed",
                type(exc).__name__,
            )
        record_llm_audit_log(
            db,
            workflow_step=STEP_TAILOR,
            backend=backend,
            model=model,
            prompt_version=prompt_version,
            input_hash=input_hash,
            output_hash=stable_payload_hash(
                {
                    "tailoring_suggestions": result.get("tailoring_suggestions", []),
                    "tailored_resume": result.get("tailored_resume", ""),
                }
            ),
            latency_ms=latency_ms,
            token_count_input=result.get("token_count_input"),
            token_count_output=result.get("token_count_output"),
            status=STATUS_SUCCEEDED,
            request_id=request_id,
            baseline_profile_id=baseline.id,
            job_analysis_id=job_analysis_id,
            generated_resume_id=resume.id,
        )

        logger.info(
            "tailor_complete job_id=%s resume_id=%s",
            job_analysis_id,
            resume.id,
        )
        return TailoringResult(
            job_analysis_id=job_analysis_id,
            status=TAILORING_STATUS_SUCCEEDED,
            generated_resume_id=resume.id,
        )


def _call_tailor_llm(
    llm: LLMClient,
    job: JobAnalysis,
    baseline_text: str = "",
    structured_data: dict | None = None,
    proof_points: str | None = None,
) -> dict:
    """Call the LLM to produce tailoring suggestions and a tailored resume.

    Uses the LLM client's `tailor` method and rejects invalid output before
    GeneratedResume state is persisted.
    """
    tailor = getattr(llm, "tailor", None)
    if tailor is not None:
        kwargs = {
            "baseline_text": baseline_text,
            "jd_text": job.jd_full_text,
            "gaps": job.gaps or [],
            "score": job.score or 0,
        }
        # Pass structured_data only when the client signature accepts it.
        import inspect

        sig = inspect.signature(tailor)
        if "structured_data" in sig.parameters:
            kwargs["structured_data"] = structured_data
        if "proof_points" in sig.parameters:
            kwargs["proof_points"] = proof_points
        result = tailor(**kwargs)
        return validate_tailor_output(result, source=llm.__class__.__name__)
    raise LLMInvalidOutputError("active LLM client does not implement tailor")


def _tailoring_failure(
    job_analysis_id: uuid.UUID,
    error_code: str,
    error_message: str,
) -> TailoringResult:
    return TailoringResult(
        job_analysis_id=job_analysis_id,
        status=TAILORING_STATUS_FAILED,
        error_code=error_code,
        error_message=error_message,
    )


def _is_cancelled(
    job_analysis_id: uuid.UUID,
    cancel_requested: Callable[[], bool] | None,
) -> bool:
    if cancel_requested is None:
        return False
    try:
        cancelled = cancel_requested()
    except Exception:
        logger.exception("tailor_cancel_check_failed job_id=%s", job_analysis_id)
        return False
    if cancelled:
        logger.info("tailor_cancelled job_id=%s", job_analysis_id)
    return cancelled
