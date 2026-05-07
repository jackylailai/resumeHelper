from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.models.evaluation_job import EvaluationCache
from backend.app.models.resume_evaluation import ResumeEvaluation
from backend.app.models.resume_version import ResumeVersion
from backend.app.services.hashing import cache_key, jd_hash
from backend.app.services.llm import EvaluationResult, LLMClient

logger = logging.getLogger(__name__)


class LLMUnavailableError(RuntimeError):
    pass


class LLMInvalidScoreError(ValueError):
    pass


def check_cache(
    db: Session,
    content_hash: str,
    job_description: str,
    prompt_version: str,
) -> ResumeEvaluation | None:
    key = cache_key(content_hash, job_description, prompt_version)
    entry = db.get(EvaluationCache, key)
    if entry:
        return entry.evaluation
    return None


def run_evaluation(
    db: Session,
    version: ResumeVersion,
    job_description: str,
    llm: LLMClient,
) -> ResumeEvaluation:
    settings = get_settings()
    prompt_version = settings.llm_prompt_version
    model_name = settings.llm_model

    jd = jd_hash(job_description)
    key = cache_key(version.content_hash, job_description, prompt_version)

    # Cache hit — return existing evaluation
    entry = db.get(EvaluationCache, key)
    if entry:
        logger.info(
            "cache_hit cache_key=%s version_id=%s",
            key[:8],
            version.id,
        )
        return entry.evaluation

    # Call LLM
    start = time.monotonic()
    try:
        result: EvaluationResult = llm.evaluate(
            version.parsed_text, job_description, prompt_version
        )
    except Exception as exc:
        logger.error("llm_error version_id=%s error=%s", version.id, exc)
        raise LLMUnavailableError(str(exc)) from exc

    latency_ms = int((time.monotonic() - start) * 1000)

    if not (0 <= result.score <= 100):
        raise LLMInvalidScoreError(f"LLM returned out-of-range score: {result.score}")

    evaluation = ResumeEvaluation(
        id=uuid.uuid4(),
        resume_version_id=version.id,
        job_description=job_description,
        jd_hash=jd,
        score=result.score,
        explanation=result.explanation,
        strengths=result.strengths,
        gaps=result.gaps,
        prompt_version=prompt_version,
        model=model_name,
        token_count_input=result.token_count_input,
        token_count_output=result.token_count_output,
        latency_ms=latency_ms,
        created_at=datetime.now(timezone.utc),
    )
    db.add(evaluation)
    db.flush()  # get evaluation.id

    cache_entry = EvaluationCache(
        cache_key=key,
        evaluation_id=evaluation.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(cache_entry)
    db.commit()
    db.refresh(evaluation)

    logger.info(
        "evaluation_done version_id=%s score=%d latency_ms=%d "
        "prompt_version=%s token_in=%s token_out=%s",
        version.id,
        result.score,
        latency_ms,
        prompt_version,
        result.token_count_input,
        result.token_count_output,
    )
    return evaluation
