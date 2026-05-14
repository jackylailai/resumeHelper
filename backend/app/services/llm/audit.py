from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime
from hashlib import sha256
from typing import Any

from sqlalchemy.orm import Session

from backend.app.api.envelope import current_request_id
from backend.app.config import get_settings
from backend.app.models.llm_audit_log import LLMAuditLog
from backend.app.services.llm import LLMInvalidOutputError, LLMUnavailableError

logger = logging.getLogger(__name__)

STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"

STEP_EVALUATE = "evaluate"
STEP_TAILOR = "tailor"
STEP_EXTRACT = "extract"
STEP_BEAUTIFY = "beautify"

_ERROR_MESSAGE_MAX_CHARS = 240


def stable_payload_hash(payload: Any) -> str:
    """Hash a structured payload without storing resume or JD text."""
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=_json_default,
    )
    return sha256(encoded.encode("utf-8")).hexdigest()


def llm_metadata(llm: object) -> tuple[str, str | None]:
    settings = get_settings()
    class_name = llm.__class__.__name__
    if class_name == "AnthropicLLMClient":
        return "anthropic", _string_or_none(getattr(llm, "_model", None))
    if class_name == "ClaudeCLIClient":
        return "claude_cli", _string_or_none(getattr(llm, "model", None))
    if class_name == "FakeLLMClient":
        return "fake", "fake"
    return settings.llm_backend, _string_or_none(
        getattr(llm, "model", getattr(llm, "_model", settings.llm_model))
    )


def error_code_for_exception(exc: Exception) -> str:
    if isinstance(exc, LLMUnavailableError):
        return "llm_unavailable"
    if isinstance(exc, LLMInvalidOutputError):
        return "llm_invalid_output"
    return "llm_error"


def error_message_for_exception(exc: Exception) -> str:
    # Store only a short error summary. Some exception strings can include raw
    # model output, which may contain private resume/JD content.
    message = type(exc).__name__
    if len(message) > _ERROR_MESSAGE_MAX_CHARS:
        return message[:_ERROR_MESSAGE_MAX_CHARS]
    return message


def record_llm_audit_log(
    db: Session,
    *,
    workflow_step: str,
    backend: str,
    model: str | None,
    prompt_version: str | None,
    input_hash: str | None,
    output_hash: str | None = None,
    latency_ms: int | None = None,
    token_count_input: int | None = None,
    token_count_output: int | None = None,
    status: str,
    error_code: str | None = None,
    error_message: str | None = None,
    request_id: str | None = None,
    baseline_profile_id: int | None = None,
    job_analysis_id: uuid.UUID | None = None,
    generated_resume_id: uuid.UUID | None = None,
    resume_beautification_id: uuid.UUID | None = None,
) -> LLMAuditLog | None:
    row = LLMAuditLog(
        request_id=request_id or current_request_id(),
        workflow_step=workflow_step,
        backend=backend,
        model=model,
        prompt_version=prompt_version,
        input_hash=input_hash,
        output_hash=output_hash,
        latency_ms=latency_ms,
        token_count_input=token_count_input,
        token_count_output=token_count_output,
        status=status,
        error_code=error_code,
        error_message=error_message,
        baseline_profile_id=baseline_profile_id,
        job_analysis_id=job_analysis_id,
        generated_resume_id=generated_resume_id,
        resume_beautification_id=resume_beautification_id,
    )
    db.add(row)
    try:
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        logger.exception(
            "llm_audit_log_write_failed workflow_step=%s status=%s",
            workflow_step,
            status,
        )
        return None
    return row


def _json_default(value: object) -> str:
    if isinstance(value, (uuid.UUID, datetime, date)):
        return str(value)
    return repr(value)


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
