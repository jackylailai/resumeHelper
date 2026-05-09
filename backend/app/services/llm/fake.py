from __future__ import annotations

import re

from backend.app.services.llm import EvaluationResult

_E2E_SCORE_MARKER = re.compile(r"\[\[score=(\d{1,3})\]\]")


class FakeLLMClient:
    """Deterministic test double. Returns fixed results keyed by content hash prefix.

    For E2E tests running against a separate uvicorn process (where in-process
    state can't be mutated), the JD text may embed `[[score=N]]` and the fake
    will return that score. Production JDs never contain this marker.
    """

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

        marker = _E2E_SCORE_MARKER.search(job_description)
        score = int(marker.group(1)) if marker else self._default_score
        return EvaluationResult(
            score=score,
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

    def tailor(
        self,
        baseline_text: str,
        jd_text: str,
        gaps: list[str],
        score: int,
    ) -> dict:
        """Fake tailoring — returns deterministic output for tests."""
        return {
            "tailoring_suggestions": [
                "Add quantified achievements",
                "Highlight relevant keywords from the JD",
            ],
            "tailored_resume": (
                f"# Tailored Resume (fake)\n\n"
                f"**Score before tailoring:** {score}\n\n"
                f"## Skills\n\nPython, FastAPI, PostgreSQL\n\n"
                f"## Experience\n\nSoftware Engineer — tailored for this role.\n"
            ),
        }
