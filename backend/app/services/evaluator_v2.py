from __future__ import annotations
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.models.baseline_profile import BaselineProfile
from backend.app.models.job_analysis import (
    JobAnalysis,
    STATUS_READY_TO_SUBMIT,
    STATUS_NEEDS_TAILORING,
    STATUS_SKIP,
    THRESHOLD_HIGH,
    THRESHOLD_MID,
)
from backend.app.services import hashing
from backend.app.services.llm import LLMClient

logger = logging.getLogger(__name__)

_SNIPPET_LEN = 200


def get_baseline(db: Session) -> BaselineProfile | None:
    return db.query(BaselineProfile).order_by(BaselineProfile.id.desc()).first()


def upsert_baseline(db: Session, skills_text: str) -> BaselineProfile:
    existing = get_baseline(db)
    if existing:
        existing.skills_text = skills_text
        existing.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        return existing
    profile = BaselineProfile(skills_text=skills_text)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def evaluate_jd(
    db: Session,
    jd_text: str,
    llm: LLMClient,
    prompt_version: str,
    threshold: int,
) -> tuple[JobAnalysis, bool]:
    """Score JD against baseline. Returns (job_analysis, cache_hit)."""
    jd_h = hashing.jd_hash(jd_text)

    existing = db.query(JobAnalysis).filter(JobAnalysis.jd_hash == jd_h).first()
    if existing:
        logger.info("cache_hit jd_hash=%s score=%s", jd_h, existing.score)
        return existing, True

    baseline = get_baseline(db)
    if baseline is None:
        raise LookupError("baseline_profile not set")

    result = llm.evaluate(baseline.skills_text, jd_text, prompt_version)

    # Compute three-tier status
    score = result.score
    if score >= THRESHOLD_HIGH:
        status = STATUS_READY_TO_SUBMIT
        can_submit = True
        skip_reason = None
    elif score >= THRESHOLD_MID:
        status = STATUS_NEEDS_TAILORING
        can_submit = False
        skip_reason = None
    else:
        status = STATUS_SKIP
        can_submit = False
        skip_reason = (
            f"Score {score} is below threshold {THRESHOLD_MID}. "
            "The resume does not sufficiently match this job description."
        )

    job = JobAnalysis(
        jd_hash=jd_h,
        jd_snippet=jd_text[:_SNIPPET_LEN],
        jd_full_text=jd_text,
        score=score,
        explanation=result.explanation,
        strengths=result.strengths,
        gaps=result.gaps,
        threshold_met=score >= threshold,
        status=status,
        can_submit=can_submit,
        skip_reason=skip_reason,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    logger.info(
        "evaluated jd_hash=%s score=%d status=%s threshold_met=%s",
        jd_h, score, status, job.threshold_met,
    )
    return job, False
