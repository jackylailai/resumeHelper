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
        structured_data: dict | None = None,
    ) -> dict:
        """Fake tailoring returns deterministic output for tests."""
        return {
            "tailoring_suggestions": [
                "Keep source facts unchanged while emphasizing relevant evidence",
                "Review gaps manually before submitting",
            ],
            "tailored_resume": (
                f"# Tailored Resume (fake)\n\n"
                f"**Score before tailoring:** {score}\n\n"
                f"## Source Profile\n\n{baseline_text.strip()}\n"
            ),
            "token_count_input": 120,
            "token_count_output": 80,
        }

    def beautify(
        self,
        resume_markdown: str,
        style: str = "modern",
    ) -> dict:
        """Fake beautify returns canned HTML wrapping the markdown for tests."""
        html = (
            "<!DOCTYPE html>"
            "<html><head><meta charset='utf-8'>"
            f"<title>Fake Beautified Resume - {style}</title>"
            "<style>body{font-family:system-ui;max-width:720px;margin:2rem auto;}"
            "pre{white-space:pre-wrap;}</style>"
            "</head><body>"
            f"<header><strong>Style:</strong> {style}</header>"
            f"<pre>{resume_markdown}</pre>"
            "</body></html>"
        )
        return {
            "html_content": html,
            "prompt_version": "beautify-fake-v1",
            "token_count_input": 90,
            "token_count_output": 60,
        }

    def extract_structured(self, source_text: str) -> dict:
        """Fake structured extraction is deterministic for tests."""
        return {
            "personal": {"name": "Fake Candidate"},
            "summary": f"Fake summary derived from {len(source_text)} chars.",
            "work_experience": [
                {
                    "employer": "FakeCorp",
                    "title": "Software Engineer",
                    "start_date": "2023-01",
                    "is_current": True,
                    "achievements": ["Did fake things", "Wrote fake tests"],
                }
            ],
            "skills": {"languages": ["Python"]},
            "_source_chars": len(source_text),
        }
