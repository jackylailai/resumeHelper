from __future__ import annotations

import json
import logging

import anthropic

from backend.app.config import get_settings
from backend.app.services.llm import EvaluationResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an expert recruiter and resume evaluator. Analyze the provided resume
against the job description and return a structured JSON evaluation.

Return ONLY valid JSON with this exact schema:
{
  "score": <integer 0-100>,
  "explanation": "<2-3 sentence overall assessment>",
  "strengths": ["<strength 1>", "<strength 2>", ...],
  "gaps": ["<gap 1>", "<gap 2>", ...]
}

Scoring guide:
- 90-100: Exceptional fit, meets nearly all requirements
- 70-89: Strong fit, meets most requirements
- 50-69: Moderate fit, meets some requirements
- 30-49: Weak fit, significant gaps
- 0-29: Poor fit, major mismatches

Return ONLY the JSON object, no markdown, no extra text.
"""


class AnthropicLLMClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.llm_model

    def evaluate(
        self,
        parsed_text: str,
        job_description: str,
        prompt_version: str,
    ) -> EvaluationResult:
        user_content = (
            f"<resume>\n{parsed_text}\n</resume>\n\n"
            f"<job_description>\n{job_description}\n</job_description>"
        )

        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )

        raw = response.content[0].text.strip()  # type: ignore[index]
        logger.info(
            "llm_response model=%s tokens_in=%d tokens_out=%d",
            self._model,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM returned invalid JSON: {exc}\nRaw: {raw[:200]}") from exc

        return EvaluationResult(
            score=int(data["score"]),
            explanation=data.get("explanation", ""),
            strengths=data.get("strengths", []),
            gaps=data.get("gaps", []),
            token_count_input=response.usage.input_tokens,
            token_count_output=response.usage.output_tokens,
        )
