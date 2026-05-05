from __future__ import annotations

from backend.app.services.llm import EvaluationResult


class FakeLLMClient:
    """Deterministic test double. Returns fixed results keyed by content hash prefix."""

    def __init__(self, default_score: int = 72, delay_seconds: float = 0.0) -> None:
        self._default_score = default_score
        self._delay = delay_seconds
        self._overrides: dict[str, EvaluationResult] = {}

    def set_result(self, content_hash_prefix: str, result: EvaluationResult) -> None:
        self._overrides[content_hash_prefix] = result

    def evaluate(
        self,
        parsed_text: str,
        job_description: str,
        prompt_version: str,
    ) -> EvaluationResult:
        if self._delay:
            import time
            time.sleep(self._delay)

        for prefix, result in self._overrides.items():
            if parsed_text.startswith(prefix):
                return result

        return EvaluationResult(
            score=self._default_score,
            explanation=(
                f"[fake evaluation] Resume text length: {len(parsed_text)} chars. "
                f"JD length: {len(job_description)} chars. "
                f"Prompt version: {prompt_version}."
            ),
            strengths=["Demonstrated experience", "Clear formatting"],
            gaps=["Missing quantified achievements"],
            token_count_input=100,
            token_count_output=50,
        )
