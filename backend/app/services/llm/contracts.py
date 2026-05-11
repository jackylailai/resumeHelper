from __future__ import annotations

import json
from typing import Annotated

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
