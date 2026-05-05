from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from backend.app.db import SessionLocal
from backend.app.services.evaluator import (
    LLMInvalidScoreError,
    LLMUnavailableError,
    run_evaluation,
)
from backend.app.services.llm import LLMClient

logger = logging.getLogger(__name__)


def enqueue_evaluation(job_id: uuid.UUID, llm: LLMClient) -> None:
    """BackgroundTasks entrypoint — runs in-process after response is sent."""
    from backend.app.models.evaluation_job import EvaluationJob
    from backend.app.models.resume_version import ResumeVersion

    with SessionLocal() as db:
        job = db.get(EvaluationJob, job_id)
        if job is None:
            logger.error("job_not_found job_id=%s", job_id)
            return

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        db.commit()

        version = db.get(ResumeVersion, job.resume_version_id)
        if version is None:
            _fail(db, job, "version_not_found")
            return

        # Reconstruct job_description from jd_hash is not possible —
        # we need the original text. Fetch it from the evaluation if it
        # was already cached, otherwise look it up from the job's stored hash.
        # We store job_description on the version record via a temporary
        # thread-local set before enqueueing (see api/resumes.py).
        jd = getattr(version, "_job_description", None)
        if jd is None:
            _fail(db, job, "job_description_missing")
            return

        try:
            evaluation = run_evaluation(db, version, jd, llm)
        except LLMUnavailableError as exc:
            _fail(db, job, f"llm_unavailable: {exc}")
            return
        except LLMInvalidScoreError as exc:
            _fail(db, job, f"llm_invalid_score: {exc}")
            return
        except Exception as exc:
            logger.exception("unexpected error in job %s", job_id)
            _fail(db, job, f"unexpected: {exc}")
            return

        job.status = "succeeded"
        job.evaluation_id = evaluation.id
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("job_succeeded job_id=%s evaluation_id=%s", job_id, evaluation.id)


def _fail(db, job, reason: str) -> None:  # type: ignore[no-untyped-def]
    from backend.app.models.evaluation_job import EvaluationJob
    job.status = "failed"
    job.failure_reason = reason
    job.finished_at = datetime.now(timezone.utc)
    db.commit()
    logger.warning("job_failed job_id=%s reason=%s", job.id, reason)
