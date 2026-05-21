from __future__ import annotations

import argparse
import logging
import sys
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import backend.app.schemas.evaluate as evaluate_schemas
from backend.app.api.envelope import reset_request_id, set_request_id
from backend.app.config import get_settings
from backend.app.models.job_analysis import (
    STATUS_NEEDS_TAILORING,
    STATUS_READY_TO_SUBMIT,
    STATUS_SKIP,
)
from backend.app.services.evaluator_v2 import evaluate_jd
from backend.app.services.job_queue import (
    AI_JOB_KIND_EVALUATE,
    AI_JOB_KIND_TAILOR,
    AI_JOB_STATUS_CANCELLED,
    AI_JOB_STATUS_FAILED,
    AI_JOB_STATUS_SUCCEEDED,
    ClaimedAIJob,
    claim_next_job,
    enqueue_tailoring_job,
    job_analysis_id_from_claim,
    mark_job_failed,
    mark_job_succeeded,
)
from backend.app.services.llm import LLMClient, LLMInvalidOutputError, LLMUnavailableError
from backend.app.services.llm.audit import (
    error_code_for_exception,
    error_message_for_exception,
)
from backend.app.services.llm.prompt_registry import STEP_TAILOR, prompt_version_for_step
from backend.app.workers.tailor import (
    TAILORING_STATUS_SUCCEEDED,
    TailoringError,
    TailoringResult,
    run_tailoring,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JobExecutionResult:
    id: uuid.UUID
    kind: str
    status: str
    error_code: str | None = None
    error_message: str | None = None
    result: dict[str, Any] | None = None


class JobExecutionError(RuntimeError):
    def __init__(self, error_code: str, error_message: str) -> None:
        super().__init__(error_message)
        self.error_code = error_code
        self.error_message = error_message


def _get_default_session_factory() -> Any:
    from backend.app.db import SessionLocal

    return SessionLocal


def run_job_queue_once(
    *,
    llm: LLMClient,
    session_factory: Callable | None = None,
    kind: str | None = None,
) -> JobExecutionResult | None:
    if session_factory is None:
        session_factory = _get_default_session_factory()

    with session_factory() as db:
        claimed = claim_next_job(db, kind=kind)

    if claimed is None:
        return None
    if claimed.status == AI_JOB_STATUS_CANCELLED:
        return JobExecutionResult(
            id=claimed.id,
            kind=claimed.kind,
            status=AI_JOB_STATUS_CANCELLED,
        )

    try:
        result = _execute_claimed_job(
            claimed,
            llm=llm,
            session_factory=session_factory,
        )
    except Exception as exc:
        error_code, error_message = _error_details(exc)
        with session_factory() as db:
            ref = mark_job_failed(
                db,
                job_id=claimed.id,
                error_code=error_code,
                error_message=error_message,
            )
        final_status = ref.status if ref is not None else AI_JOB_STATUS_FAILED
        logger.exception(
            "ai_job_failed ai_job_id=%s kind=%s error_code=%s",
            claimed.id,
            claimed.kind,
            error_code,
        )
        return JobExecutionResult(
            id=claimed.id,
            kind=claimed.kind,
            status=final_status,
            error_code=error_code,
            error_message=error_message,
        )

    with session_factory() as db:
        ref = mark_job_succeeded(db, job_id=claimed.id, result=result)
    final_status = ref.status if ref is not None else AI_JOB_STATUS_SUCCEEDED
    return JobExecutionResult(
        id=claimed.id,
        kind=claimed.kind,
        status=final_status,
        result=result,
    )


def run_job_queue_loop(
    *,
    llm: LLMClient,
    session_factory: Callable | None = None,
    poll_interval_seconds: float = 5.0,
    max_jobs: int | None = None,
    kind: str | None = None,
) -> int:
    processed = 0
    while True:
        result = run_job_queue_once(
            llm=llm,
            session_factory=session_factory,
            kind=kind,
        )
        if result is None:
            if max_jobs is not None:
                return processed
            time.sleep(poll_interval_seconds)
            continue

        processed += 1
        logger.info(
            "ai_job_processed ai_job_id=%s kind=%s status=%s",
            result.id,
            result.kind,
            result.status,
        )
        if max_jobs is not None and processed >= max_jobs:
            return processed


def _execute_claimed_job(
    claimed: ClaimedAIJob,
    *,
    llm: LLMClient,
    session_factory: Callable,
) -> dict[str, Any]:
    if claimed.kind == AI_JOB_KIND_TAILOR:
        tailoring_result = _execute_tailor_job(
            claimed,
            llm=llm,
            session_factory=session_factory,
        )
        return {
            "job_analysis_id": str(tailoring_result.job_analysis_id),
            "generated_resume_id": str(tailoring_result.generated_resume_id)
            if tailoring_result.generated_resume_id
            else None,
        }
    if claimed.kind == AI_JOB_KIND_EVALUATE:
        return _execute_evaluate_job(
            claimed,
            llm=llm,
            session_factory=session_factory,
        )
    raise JobExecutionError("unsupported_job_kind", f"unsupported ai_job kind {claimed.kind}")


def _execute_evaluate_job(
    claimed: ClaimedAIJob,
    *,
    llm: LLMClient,
    session_factory: Callable,
) -> dict[str, Any]:
    jd_text = _required_string(claimed.input_payload, "jd_text")
    profile_id = _required_int(claimed.input_payload, "profile_id")
    prompt_version = _required_string(claimed.input_payload, "prompt_version")
    request_id = _string_or_none(claimed.input_payload.get("request_id"))

    settings = get_settings()
    tailor_prompt_version = _string_or_none(
        claimed.input_payload.get("tailor_prompt_version")
    ) or prompt_version_for_step(STEP_TAILOR, settings=settings)

    if _is_cancel_requested(session_factory, job_id=claimed.id):
        raise JobExecutionError("job_cancelled", "evaluate job was cancelled")

    token = set_request_id(request_id) if request_id else None
    try:
        with session_factory() as db:
            job, cached = evaluate_jd(
                db,
                jd_text,
                llm,
                prompt_version=prompt_version,
                threshold=settings.resume_gen_threshold,
                profile_id=profile_id,
            )
            if _is_cancel_requested(session_factory, job_id=claimed.id):
                raise JobExecutionError("job_cancelled", "evaluate job was cancelled")

            status = job.status or STATUS_SKIP
            message, action = _evaluate_message_and_action(
                status=status,
                score=job.score or 0,
                skip_reason=job.skip_reason,
            )
            tailoring_ref = None
            if status == STATUS_NEEDS_TAILORING:
                tailoring_ref = enqueue_tailoring_job(
                    db,
                    job_analysis_id=job.id,
                    prompt_version=tailor_prompt_version,
                    request_id=request_id,
                )

            evaluation = evaluate_schemas.EvaluateOut(
                job_analysis_id=job.id,
                score=job.score or 0,
                explanation=job.explanation or "",
                strengths=job.strengths or [],
                gaps=job.gaps or [],
                threshold_met=job.threshold_met,
                status=status,
                message=message,
                action=action,
                prompt_version=job.prompt_version,
                llm_backend=job.llm_backend,
                llm_model=job.llm_model,
                tailoring_job_id=tailoring_ref.id if tailoring_ref is not None else None,
                tailoring_status=tailoring_ref.status if tailoring_ref is not None else None,
            ).model_dump(mode="json")
            return {
                "cached": cached,
                "job_analysis_id": str(job.id),
                "tailoring_job_id": evaluation["tailoring_job_id"],
                "tailoring_status": evaluation["tailoring_status"],
                "evaluation": evaluation,
            }
    finally:
        if token is not None:
            reset_request_id(token)


def _execute_tailor_job(
    claimed: ClaimedAIJob,
    *,
    llm: LLMClient,
    session_factory: Callable,
) -> TailoringResult:
    result = run_tailoring(
        job_analysis_id=job_analysis_id_from_claim(claimed),
        llm=llm,
        prompt_version=_string_or_none(claimed.input_payload.get("prompt_version")),
        session_factory=session_factory,
        request_id=_string_or_none(claimed.input_payload.get("request_id")),
        cancel_requested=lambda: _is_cancel_requested(
            session_factory,
            job_id=claimed.id,
        ),
    )
    if result.status != TAILORING_STATUS_SUCCEEDED:
        raise JobExecutionError(
            result.error_code or "tailor_failed",
            result.error_message or "tailoring failed",
        )
    return result


def _error_details(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, JobExecutionError | TailoringError):
        return exc.error_code, _truncate_error(exc.error_message)
    if isinstance(exc, LLMUnavailableError | LLMInvalidOutputError):
        return error_code_for_exception(exc), _truncate_error(error_message_for_exception(exc))
    return type(exc).__name__, _truncate_error(str(exc) or type(exc).__name__)


def _evaluate_message_and_action(
    *,
    status: str,
    score: int,
    skip_reason: str | None,
) -> tuple[str, str]:
    if status == STATUS_READY_TO_SUBMIT:
        return f"Score {score}: Excellent match. Resume is ready to submit.", "none"
    if status == STATUS_NEEDS_TAILORING:
        return f"Score {score}: Good match. Tailoring resume in background.", "tailoring"
    reason = skip_reason or ""
    return f"Score {score}: Low match. Skipping this job. {reason}", "skip"


def _is_cancel_requested(session_factory: Callable, *, job_id: uuid.UUID) -> bool:
    from backend.app.services.job_queue import is_cancel_requested

    with session_factory() as db:
        return is_cancel_requested(db, job_id=job_id)


def _truncate_error(message: str) -> str:
    return message[:240]


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = _string_or_none(payload.get(key))
    if value is None:
        raise JobExecutionError("invalid_job_payload", f"missing {key}")
    return value


def _required_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or value is None:
        raise JobExecutionError("invalid_job_payload", f"missing {key}")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise JobExecutionError("invalid_job_payload", f"invalid {key}") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.app.workers.job_queue")
    parser.add_argument("--once", action="store_true", help="process at most one job")
    parser.add_argument("--max-jobs", type=int, default=None, help="stop after N jobs")
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--kind", default=None, help="optional ai_jobs.kind filter")
    args = parser.parse_args(argv)

    from backend.app.services.llm.factory import create_llm_client

    llm = create_llm_client()
    max_jobs = 1 if args.once else args.max_jobs
    processed = run_job_queue_loop(
        llm=llm,
        poll_interval_seconds=args.poll_interval,
        max_jobs=max_jobs,
        kind=args.kind,
    )
    print(f"processed={processed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
