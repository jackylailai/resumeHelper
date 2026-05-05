from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class EvaluationResult:
    score: int
    explanation: str
    strengths: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    token_count_input: int | None = None
    token_count_output: int | None = None


class LLMClient(Protocol):
    def evaluate(
        self,
        parsed_text: str,
        job_description: str,
        prompt_version: str,
    ) -> EvaluationResult: ...
