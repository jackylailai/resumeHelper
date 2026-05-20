from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class EvaluationResult:
    score: int
    explanation: str
    strengths: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    token_count_input: int | None = None
    token_count_output: int | None = None


class LLMError(RuntimeError):
    """Base class for user-facing LLM failures."""


class LLMUnavailableError(LLMError):
    """Raised when the configured LLM backend cannot be reached or executed."""


class LLMInvalidOutputError(LLMError):
    """Raised when the LLM returns data that cannot be used safely."""


class LLMClient(Protocol):
    def evaluate(
        self,
        parsed_text: str,
        job_description: str,
        prompt_version: str,
    ) -> EvaluationResult: ...

    def tailor(
        self,
        baseline_text: str,
        jd_text: str,
        gaps: list[str],
        score: int,
        structured_data: dict[str, Any] | None = None,
        proof_points: str | None = None,
    ) -> dict[str, Any]: ...
