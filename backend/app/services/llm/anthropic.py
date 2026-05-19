from __future__ import annotations

import json
import logging

import anthropic

from backend.app.config import get_settings
from backend.app.services.llm import (
    EvaluationResult,
    LLMUnavailableError,
)
from backend.app.services.llm.contracts import (
    parse_evaluation_output,
    parse_structured_extraction_output,
    parse_tailor_output,
    validate_beautify_output,
)
from backend.app.services.llm.prompt_registry import (
    STEP_BEAUTIFY,
    STEP_EVALUATE,
    STEP_EXTRACT,
    STEP_TAILOR,
    render_prompt_for_step,
)

logger = logging.getLogger(__name__)


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
        prompt = render_prompt_for_step(
            STEP_EVALUATE,
            BASELINE_SKILLS=parsed_text,
            JOB_DESCRIPTION=job_description,
        )

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
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

        return parse_evaluation_output(
            raw,
            source="Anthropic API",
            token_count_input=response.usage.input_tokens,
            token_count_output=response.usage.output_tokens,
        )

    def tailor(
        self,
        baseline_text: str,
        jd_text: str,
        gaps: list[str],
        score: int,
        structured_data: dict | None = None,
    ) -> dict:
        """Generate tailoring suggestions and a tailored resume text."""

        structured_block = (
            json.dumps(structured_data, ensure_ascii=False, indent=2)
            if structured_data
            else "(none - fall back to baseline_skills text below)"
        )
        gaps_text = (
            "\n".join(f"- {gap}" for gap in gaps)
            if gaps
            else "- No specific gaps identified"
        )
        prompt = render_prompt_for_step(
            STEP_TAILOR,
            BASELINE_SKILLS=baseline_text,
            JOB_DESCRIPTION=jd_text,
            STRUCTURED_DATA=structured_block,
            CURRENT_SCORE=score,
            IDENTIFIED_GAPS=gaps_text,
        )

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as exc:
            raise LLMUnavailableError(f"Anthropic API request failed during tailor: {exc}") from exc

        raw = response.content[0].text.strip()  # type: ignore[index]
        logger.info(
            "tailor_llm_response model=%s tokens_in=%d tokens_out=%d",
            self._model,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )

        return parse_tailor_output(
            raw,
            source="Anthropic API",
            token_count_input=response.usage.input_tokens,
            token_count_output=response.usage.output_tokens,
        )

    def beautify(
        self,
        resume_markdown: str,
        style: str = "modern",
        prompt_version: str = "beautify-v1",
    ) -> dict:
        """Transform a tailored markdown resume into a styled HTML document."""

        prompt = render_prompt_for_step(
            STEP_BEAUTIFY,
            RESUME_MARKDOWN=resume_markdown,
            STYLE=style,
        )

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=8192,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as exc:
            raise LLMUnavailableError(
                f"Anthropic API request failed during beautify: {exc}"
            ) from exc

        html = response.content[0].text.strip()  # type: ignore[index]

        logger.info(
            "beautify_llm_response model=%s style=%s tokens_in=%d tokens_out=%d",
            self._model,
            style,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )

        return validate_beautify_output(
            html,
            source="Anthropic API",
            source_markdown=resume_markdown,
            prompt_version=prompt_version,
            token_count_input=response.usage.input_tokens,
            token_count_output=response.usage.output_tokens,
        )

    def extract_structured(self, source_text: str, prompt_version: str = "extract-v1") -> dict:
        """Parse a free-form profile text into structured JSON via the SDK."""

        prompt = render_prompt_for_step(STEP_EXTRACT, SOURCE_TEXT=source_text)
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as exc:
            raise LLMUnavailableError(
                f"Anthropic API request failed during extract: {exc}"
            ) from exc

        raw = response.content[0].text.strip()  # type: ignore[index]
        data = parse_structured_extraction_output(raw, source="Anthropic API")
        logger.info(
            "extract_llm_response model=%s keys=%d tokens_in=%d tokens_out=%d",
            self._model,
            len(data),
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        return data
