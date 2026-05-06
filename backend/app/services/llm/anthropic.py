from __future__ import annotations

import json
import logging
from typing import List

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

_TAILOR_SYSTEM_PROMPT = """\
You are an expert resume writer. Given a candidate's baseline skills/resume and a job description,
plus a list of identified skill gaps, generate a tailored resume that:
1. Highlights relevant skills matching the job requirements
2. Reframes experience to align with the role
3. Incorporates key keywords from the job description
4. Addresses the identified gaps where possible

Return ONLY valid JSON with this exact schema:
{
  "tailoring_suggestions": ["<actionable suggestion 1>", "<actionable suggestion 2>", ...],
  "tailored_resume": "<full markdown resume text, professionally formatted>"
}

The tailored_resume should be a complete, polished resume in Markdown format.
Return ONLY the JSON object, no markdown code fences, no extra text.
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

    def tailor(
        self,
        baseline_text: str,
        jd_text: str,
        gaps: List[str],
        score: int,
    ) -> dict:
        """Generate tailoring suggestions and a tailored resume text."""
        gaps_text = "\n".join(f"- {g}" for g in gaps) if gaps else "- No specific gaps identified"
        user_content = (
            f"<current_score>{score}</current_score>\n\n"
            f"<identified_gaps>\n{gaps_text}\n</identified_gaps>\n\n"
            f"<baseline_resume>\n{baseline_text}\n</baseline_resume>\n\n"
            f"<job_description>\n{jd_text}\n</job_description>"
        )

        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=_TAILOR_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )

        raw = response.content[0].text.strip()  # type: ignore[index]
        logger.info(
            "tailor_llm_response model=%s tokens_in=%d tokens_out=%d",
            self._model,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM returned invalid JSON for tailor: {exc}\nRaw: {raw[:200]}") from exc

        return {
            "tailoring_suggestions": data.get("tailoring_suggestions", []),
            "tailored_resume": data.get("tailored_resume", ""),
        }
