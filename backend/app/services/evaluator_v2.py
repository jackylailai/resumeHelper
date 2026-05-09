from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.app.models.baseline_profile import BaselineProfile
from backend.app.models.job_analysis import (
    STATUS_NEEDS_TAILORING,
    STATUS_READY_TO_SUBMIT,
    STATUS_SKIP,
    THRESHOLD_HIGH,
    THRESHOLD_MID,
    JobAnalysis,
)
from backend.app.services import hashing
from backend.app.services.llm import LLMClient

logger = logging.getLogger(__name__)

_SNIPPET_LEN = 200


# ---------------------------------------------------------------------------
# Profile CRUD
# ---------------------------------------------------------------------------

def list_profiles(db: Session) -> list[BaselineProfile]:
    return (
        db.query(BaselineProfile)
        .order_by(BaselineProfile.is_default.desc(), BaselineProfile.id.desc())
        .all()
    )


def get_profile(db: Session, profile_id: int) -> BaselineProfile | None:
    return db.get(BaselineProfile, profile_id)


def get_latest_profile(db: Session) -> BaselineProfile | None:
    return db.query(BaselineProfile).order_by(BaselineProfile.id.desc()).first()


def get_default_profile(db: Session) -> BaselineProfile | None:
    default_profile = (
        db.query(BaselineProfile)
        .filter(BaselineProfile.is_default.is_(True))
        .order_by(BaselineProfile.id.desc())
        .first()
    )
    return default_profile or get_latest_profile(db)


# Backward-compat alias used by tailor worker and old callers
def get_baseline(db: Session) -> BaselineProfile | None:
    return get_default_profile(db)


def _set_only_default(db: Session, profile: BaselineProfile) -> None:
    db.query(BaselineProfile).filter(BaselineProfile.id != profile.id).update(
        {BaselineProfile.is_default: False},
        synchronize_session=False,
    )
    profile.is_default = True


def create_profile(
    db: Session,
    skills_text: str,
    name: str | None = None,
    is_default: bool = False,
) -> BaselineProfile:
    skills_text = skills_text.replace("\x00", "")
    profile = BaselineProfile(skills_text=skills_text, name=name, is_default=is_default)
    db.add(profile)
    db.flush()
    if is_default:
        _set_only_default(db, profile)
    db.commit()
    db.refresh(profile)
    return profile


def update_profile(
    db: Session,
    profile_id: int,
    skills_text: str | None = None,
    name: str | None = None,
    is_default: bool | None = None,
) -> BaselineProfile:
    profile = db.get(BaselineProfile, profile_id)
    if profile is None:
        raise LookupError(f"profile {profile_id} not found")
    if skills_text is not None:
        profile.skills_text = skills_text.replace("\x00", "")
    if name is not None:
        profile.name = name
    if is_default is True:
        _set_only_default(db, profile)
    elif is_default is False and profile.is_default:
        profile.is_default = False
    profile.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(profile)
    return profile


def delete_profile(db: Session, profile_id: int) -> None:
    profile = db.get(BaselineProfile, profile_id)
    if profile is None:
        raise LookupError(f"profile {profile_id} not found")
    db.delete(profile)
    db.commit()


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate_jd(
    db: Session,
    jd_text: str,
    llm: LLMClient,
    prompt_version: str,
    threshold: int,
    profile_id: int | None = None,
) -> tuple[JobAnalysis, bool]:
    """Score JD against a profile. Returns (job_analysis, cache_hit)."""
    # Resolve profile
    if profile_id is not None:
        profile = get_profile(db, profile_id)
        if profile is None:
            raise LookupError(f"profile {profile_id} not found")
    else:
        profile = get_default_profile(db)
        if profile is None:
            raise LookupError("baseline_profile not set")
        profile_id = profile.id

    jd_h = hashing.jd_hash(jd_text)

    # Cache key is (jd_hash, profile_id)
    existing = (
        db.query(JobAnalysis)
        .filter(JobAnalysis.jd_hash == jd_h, JobAnalysis.profile_id == profile_id)
        .first()
    )
    if existing:
        logger.info("cache_hit jd_hash=%s profile_id=%s score=%s", jd_h, profile_id, existing.score)
        return existing, True

    result = llm.evaluate(profile.skills_text, jd_text, prompt_version)

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
        profile_id=profile_id,
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
        "evaluated jd_hash=%s profile_id=%s score=%d status=%s",
        jd_h, profile_id, score, status,
    )
    return job, False
