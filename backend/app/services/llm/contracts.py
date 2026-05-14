from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    ValidationError,
    field_validator,
)

from backend.app.services.llm import EvaluationResult, LLMInvalidOutputError

_MAX_EXPLANATION_CHARS = 2000
_MAX_LIST_ITEMS = 20
_MAX_LIST_ITEM_CHARS = 500
_MAX_TAILORED_RESUME_CHARS = 30000
_TAILOR_ALLOWED_METADATA = {"token_count_input", "token_count_output"}
_PREAMBLE_PREFIXES = (
    "here is",
    "here's",
    "sure,",
    "of course",
    "below is",
)

_BoundedText = Annotated[
    StrictStr,
    Field(min_length=1, max_length=_MAX_LIST_ITEM_CHARS),
]


class EvaluationOutputContract(BaseModel):
    """Schema for the resume-vs-JD scoring LLM call."""

    model_config = ConfigDict(extra="forbid")

    score: StrictInt = Field(ge=0, le=100)
    explanation: StrictStr = Field(min_length=1, max_length=_MAX_EXPLANATION_CHARS)
    strengths: list[_BoundedText] = Field(max_length=_MAX_LIST_ITEMS)
    gaps: list[_BoundedText] = Field(max_length=_MAX_LIST_ITEMS)

    @field_validator("explanation")
    @classmethod
    def _strip_explanation(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("explanation must not be blank")
        return value

    @field_validator("strengths", "gaps")
    @classmethod
    def _strip_list_items(cls, value: list[str]) -> list[str]:
        stripped = [item.strip() for item in value]
        if any(not item for item in stripped):
            raise ValueError("items must not be blank")
        return stripped


class TailorOutputContract(BaseModel):
    """Schema for the resume tailoring LLM call."""

    model_config = ConfigDict(extra="forbid")

    tailoring_suggestions: list[_BoundedText] = Field(max_length=_MAX_LIST_ITEMS)
    tailored_resume: StrictStr = Field(
        min_length=1,
        max_length=_MAX_TAILORED_RESUME_CHARS,
    )

    @field_validator("tailoring_suggestions")
    @classmethod
    def _strip_suggestions(cls, value: list[str]) -> list[str]:
        stripped = [item.strip() for item in value]
        if any(not item for item in stripped):
            raise ValueError("tailoring_suggestions items must not be blank")
        return stripped

    @field_validator("tailored_resume")
    @classmethod
    def _validate_tailored_resume(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("tailored_resume must not be blank")
        if "```" in text:
            raise ValueError("tailored_resume must not contain code fences")
        lowered = text.casefold()
        if any(lowered.startswith(prefix) for prefix in _PREAMBLE_PREFIXES):
            raise ValueError("tailored_resume must not include a preamble")
        return text


def strip_json_code_fence(raw: str) -> str:
    """Allow legacy adapters to accept a single fenced JSON object."""
    text = raw.strip()
    if not text.startswith("```"):
        return text

    lines = text.splitlines()
    if not lines:
        return text
    if not lines[-1].strip().startswith("```"):
        return text
    return "\n".join(lines[1:-1]).strip()


def parse_evaluation_output(
    raw: str,
    *,
    source: str,
    token_count_input: int | None = None,
    token_count_output: int | None = None,
) -> EvaluationResult:
    """Parse and validate raw LLM scoring output into the shared result type."""
    text = strip_json_code_fence(raw)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMInvalidOutputError(f"{source} returned invalid JSON: {exc}") from exc

    try:
        contract = EvaluationOutputContract.model_validate(payload)
    except ValidationError as exc:
        raise LLMInvalidOutputError(
            f"{source} returned invalid evaluation output: {exc}"
        ) from exc

    return EvaluationResult(
        score=contract.score,
        explanation=contract.explanation,
        strengths=contract.strengths,
        gaps=contract.gaps,
        token_count_input=token_count_input,
        token_count_output=token_count_output,
    )


def parse_tailor_output(
    raw: str,
    *,
    source: str,
    token_count_input: int | None = None,
    token_count_output: int | None = None,
) -> dict[str, Any]:
    """Parse and validate raw LLM tailoring output."""
    text = strip_json_code_fence(raw)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMInvalidOutputError(
            f"{source} returned invalid tailor JSON: {exc}"
        ) from exc
    return validate_tailor_output(
        payload,
        source=source,
        token_count_input=token_count_input,
        token_count_output=token_count_output,
    )


def validate_tailor_output(
    payload: Mapping[str, Any],
    *,
    source: str,
    token_count_input: int | None = None,
    token_count_output: int | None = None,
) -> dict[str, Any]:
    """Validate a parsed tailoring payload and preserve provider metadata."""
    if not isinstance(payload, Mapping):
        raise LLMInvalidOutputError(
            f"{source} returned invalid tailoring output: expected object"
        )

    unexpected = (
        set(payload) - set(TailorOutputContract.model_fields) - _TAILOR_ALLOWED_METADATA
    )
    if unexpected:
        raise LLMInvalidOutputError(
            f"{source} returned unexpected tailor fields: {sorted(unexpected)}"
        )

    try:
        contract = TailorOutputContract.model_validate(
            {
                "tailoring_suggestions": payload.get("tailoring_suggestions"),
                "tailored_resume": payload.get("tailored_resume", ""),
            }
        )
    except ValidationError as exc:
        raise LLMInvalidOutputError(
            f"{source} returned invalid tailoring output: {exc}"
        ) from exc

    output: dict[str, Any] = {
        "tailoring_suggestions": contract.tailoring_suggestions,
        "tailored_resume": contract.tailored_resume,
    }
    resolved_input_tokens = (
        token_count_input
        if token_count_input is not None
        else payload.get("token_count_input")
    )
    resolved_output_tokens = (
        token_count_output
        if token_count_output is not None
        else payload.get("token_count_output")
    )
    if resolved_input_tokens is not None:
        output["token_count_input"] = resolved_input_tokens
    if resolved_output_tokens is not None:
        output["token_count_output"] = resolved_output_tokens
    return output
