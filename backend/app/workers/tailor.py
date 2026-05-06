"""Background tailoring task for the three-tier resume evaluation system.

For jobs with status='needs_tailoring' (score 60-84), this task:
1. Calls the LLM to analyze gaps and generate a tailored resume text
2. Saves the GeneratedResume record to DB
3. Marks the JobAnalysis as can_submit=True
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Callable, Optional

from backend.app.models.baseline_profile import BaselineProfile
from backend.app.models.job_analysis import JobAnalysis, STATUS_NEEDS_TAILORING
from backend.app.models.generated_resume import GeneratedResume
from backend.app.services.llm import LLMClient

logger = logging.getLogger(__name__)


def _get_default_session_factory() -> Any:
    """Return the module-level SessionLocal, imported lazily to allow test override."""
    from backend.app.db import SessionLocal
    return SessionLocal


def run_tailoring(
    job_analysis_id: uuid.UUID,
    llm: LLMClient,
    prompt_version: str = "tailor-v1",
    session_factory: Optional[Callable] = None,
) -> None:
    """BackgroundTasks entrypoint — runs in-process after /api/evaluate response is sent.

    Args:
        job_analysis_id: The UUID of the JobAnalysis to tailor.
        llm: The LLM client to use for tailoring.
        prompt_version: Tag stored on the GeneratedResume.
        session_factory: Optional SQLAlchemy sessionmaker; defaults to app SessionLocal.
                         Pass a test-scoped factory in tests for proper DB isolation.
    """
    if session_factory is None:
        session_factory = _get_default_session_factory()

    with session_factory() as db:
        job = db.get(JobAnalysis, job_analysis_id)
        if job is None:
            logger.error("tailor_job_not_found job_id=%s", job_analysis_id)
            return

        if job.status != STATUS_NEEDS_TAILORING:
            logger.warning(
                "tailor_skip_wrong_status job_id=%s status=%s",
                job_analysis_id, job.status,
            )
            return

        logger.info("tailor_start job_id=%s score=%s", job_analysis_id, job.score)
        if job.profile_id:
            baseline = db.get(BaselineProfile, job.profile_id)
        else:
            baseline = db.query(BaselineProfile).order_by(BaselineProfile.id.desc()).first()
        if baseline is None:
            logger.error("tailor_no_baseline job_id=%s", job_analysis_id)
            return

        baseline_text = baseline.skills_text

        try:
            result = _call_tailor_llm(llm, job, baseline_text)
        except Exception as exc:
            logger.error("tailor_llm_failed job_id=%s error=%s", job_analysis_id, exc)
            return

        resume = GeneratedResume(
            job_analysis_id=job_analysis_id,
            resume_text=result["tailored_resume"],
            pdf_url=None,   # PDF generation not available (weasyprint not installed)
            prompt_version=prompt_version,
        )
        db.add(resume)

        job.can_submit = True
        db.commit()
        db.refresh(resume)

        logger.info(
            "tailor_complete job_id=%s resume_id=%s",
            job_analysis_id, resume.id,
        )


def _call_tailor_llm(llm: LLMClient, job: JobAnalysis, baseline_text: str = "") -> dict:
    """Call the LLM to produce tailoring suggestions and a tailored resume.

    Uses the LLMClient's `tailor` method if available (AnthropicLLMClient),
    otherwise falls back to a synthetic result.
    """
    if hasattr(llm, "tailor"):
        return llm.tailor(  # type: ignore[union-attr]
            baseline_text=baseline_text,
            jd_text=job.jd_full_text,
            gaps=job.gaps or [],
            score=job.score or 0,
        )
    # Fallback for any LLMClient without tailor method
    logger.warning("tailor_llm_no_tailor_method using fallback")
    return {
        "tailoring_suggestions": job.gaps or ["No specific gaps found"],
        "tailored_resume": (
            f"# Tailored Resume\n\n**Score:** {job.score}\n\n"
            f"## Key Skills\n\n{job.jd_snippet or ''}\n"
        ),
    }
