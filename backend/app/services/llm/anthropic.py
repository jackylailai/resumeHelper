from __future__ import annotations

import json
import logging

import anthropic

from backend.app.config import get_settings
from backend.app.services.llm import (
    EvaluationResult,
    LLMInvalidOutputError,
    LLMUnavailableError,
)

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

_BEAUTIFY_SYSTEM_PROMPT = """\
You are a resume designer. You receive a tailored resume in Markdown and must
transform it into a single self-contained HTML document with embedded CSS,
suitable for both browser display and PDF rendering via WeasyPrint.

Hard rules:
1. Use ONLY content from the source markdown. Do NOT invent, embellish,
   paraphrase to add facts, or fabricate skills, experience, dates, metrics,
   or contact details.
2. Preserve every concrete number, percentage, duration, scale figure, and
   proper noun verbatim.
3. Output a single complete HTML document — `<!DOCTYPE html>` ... `</html>`.
   Inline all CSS in a single `<style>` block in the head. No external
   stylesheets, fonts, images, or scripts.
4. Use only WeasyPrint-compatible CSS. Avoid JavaScript, external @font-face,
   position: sticky.
5. Style preset will be provided in the user message — interpret as: `modern`
   (clean sans-serif, blue accent), `classic` (serif, traditional), or
   `minimal` (monochrome, tight spacing).
6. Include only sections actually present in the source markdown.

Return ONLY the HTML document. No markdown code fences, no preamble.
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

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
        except anthropic.APIError as exc:
            raise LLMUnavailableError(f"Anthropic API request failed: {exc}") from exc

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
            raise LLMInvalidOutputError(f"LLM returned invalid JSON: {exc}") from exc

        try:
            score = int(data["score"])
        except (KeyError, TypeError, ValueError) as exc:
            raise LLMInvalidOutputError("LLM response did not include a valid score") from exc
        if score < 0 or score > 100:
            raise LLMInvalidOutputError(f"LLM score out of range: {score}")

        return EvaluationResult(
            score=score,
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
        gaps: list[str],
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
            raise ValueError(
                f"LLM returned invalid JSON for tailor: {exc}\nRaw: {raw[:200]}"
            ) from exc

        return {
            "tailoring_suggestions": data.get("tailoring_suggestions", []),
            "tailored_resume": data.get("tailored_resume", ""),
        }

    def beautify(
        self,
        resume_markdown: str,
        style: str = "modern",
    ) -> dict:
        """Transform a tailored markdown resume into a styled HTML document."""
        user_content = (
            f"<style_preset>{style}</style_preset>\n\n"
            f"<source_markdown>\n{resume_markdown}\n</source_markdown>"
        )

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=8192,
                system=_BEAUTIFY_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
        except anthropic.APIError as exc:
            raise LLMUnavailableError(
                f"Anthropic API request failed during beautify: {exc}"
            ) from exc

        html = response.content[0].text.strip()  # type: ignore[index]
        if html.startswith("```"):
            html = "\n".join(html.split("\n")[1:])
            html = html.rstrip("`").strip()

        if "<html" not in html.lower() or "</html>" not in html.lower():
            raise LLMInvalidOutputError(
                "Anthropic API beautify did not return a complete HTML document"
            )

        logger.info(
            "beautify_llm_response model=%s style=%s tokens_in=%d tokens_out=%d",
            self._model,
            style,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )

        return {"html_content": html, "prompt_version": "beautify-v1"}
