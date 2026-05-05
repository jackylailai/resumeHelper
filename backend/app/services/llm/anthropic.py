from __future__ import annotations

from backend.app.services.llm import EvaluationResult


class AnthropicLLMClient:
    """Production Claude client. Implemented in US1 task T046."""

    def evaluate(
        self,
        parsed_text: str,
        job_description: str,
        prompt_version: str,
    ) -> EvaluationResult:
        raise NotImplementedError("AnthropicLLMClient is implemented in Phase 3 (T046).")
