from __future__ import annotations
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.models.baseline_profile import BaselineProfile
from backend.app.models.job_analysis import JobAnalysis
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

    job = JobAnalysis(
        jd_hash=jd_h,
        jd_snippet=jd_text[:_SNIPPET_LEN],
        jd_full_text=jd_text,
        score=result.score,
        explanation=result.explanation,
        strengths=result.strengths,
        gaps=result.gaps,
        threshold_met=result.score >= threshold,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    logger.info("evaluated jd_hash=%s score=%d threshold_met=%s", jd_h, result.score, job.threshold_met)
    return job, False
