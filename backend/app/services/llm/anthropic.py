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
2. Preserve every concrete number, percentage, duration, employment date
   range, and proper noun verbatim (e.g. "April 2024 - Present", "50,000 QPS",
   "TOEIC 790", "富邦媒體科技", "騰茲電通"). Do not translate or omit them.
3. Output a single complete HTML document — `<!DOCTYPE html>` ... `</html>`.
   Inline all CSS in a single `<style>` block. No external stylesheets, fonts,
   images, or scripts.
4. CJK support is mandatory. The `font-family` stack on body and text elements
   MUST include CJK fallbacks like "Noto Sans CJK SC", "Noto Sans CJK TC",
   "PingFang SC", "Microsoft YaHei" so Chinese characters render correctly.
5. Use only WeasyPrint-compatible CSS. Avoid JavaScript, external @font-face,
   `position: sticky`, fixed pixel widths on top-level containers.
6. Layout safety: do NOT use label-value grids with fixed-width labels that
   can overflow when values are long. Prefer `<dl>` blocks, inline labels with
   `<strong>`, or grid with `minmax(7rem, max-content) 1fr` + label
   `white-space: nowrap`. Default to single-column body; two-column only for
   short skill / language lists.
7. Include each work-experience entry's date range prominently alongside the
   employer name. Never silently drop dates.
8. Style preset will be in the user message — `modern` (clean sans-serif,
   blue accent), `classic` (serif, traditional), or `minimal` (monochrome).
9. Include only sections actually present in source markdown.

Return ONLY the HTML document. No markdown code fences, no preamble.
"""

_EXTRACT_SYSTEM_PROMPT = """\
You receive a candidate's free-form resume / profile text. Extract every
concrete fact you can find into a structured JSON object. Use only what is
explicitly in the source — do not invent, paraphrase facts, or add boilerplate.
If a field has no source, omit it.

Return ONLY a JSON object (no code fences, no preamble) with these top-level
keys (all optional, omit when source has nothing): personal, summary,
work_experience, education, languages, certifications, skills,
personal_qualities.

Each work_experience entry: {employer, title, location, start_date, end_date,
is_current, achievements: [...]}. Each education entry: {school, degree, field,
start_date, end_date}. Each language: {name, level, test, score}.

Rules:
- Every value comes verbatim from source. Dates, numbers, employer names,
  school names, certification names — copy as-is.
- Don't invent fields the source doesn't mention.
- Don't editorialize titles ("Backend Engineer" stays "Backend Engineer").
- Don't summarize achievement bullets — output every concrete claim from the
  source, one per array element.
- Preserve original language for proper nouns and quotes. You may translate
  connectors only if it improves clarity.
"""

_TAILOR_SYSTEM_PROMPT = """\
You are an expert resume writer. Treat the candidate's baseline profile as the
source of truth — your job is to rephrase, reorder, and emphasize what is
already there, never to add or omit hard data.

Hard rules:
1. Preserve every concrete fact verbatim — names, employers, job titles, dates,
   year ranges (e.g. "April 2024 - Present", "August 2023 - April 2024"),
   degrees, schools, certifications, language scores (e.g. "TOEIC 790"), and
   metrics (e.g. "50,000 QPS", "5 minutes", "10x") must appear unchanged.
2. Do NOT drop sections present in baseline — Education, Languages,
   Certifications, Personal Qualities, every work history entry must remain.
3. Do NOT invent skills, employers, dates, metrics, or contact info.
4. Do NOT add boilerplate — no "References available upon request", no
   "Portfolio available upon request", no generic objective statements unless
   they exist in baseline.
5. Reframe sentences to match JD language and reorder bullets to surface
   JD-relevant items, but the underlying facts must come from baseline.
6. Self-check: every date / metric / certification / degree from baseline must
   appear at least once in the tailored output before you return.

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
        structured_data: dict | None = None,
    ) -> dict:
        """Generate tailoring suggestions and a tailored resume text."""
        gaps_text = "\n".join(f"- {g}" for g in gaps) if gaps else "- No specific gaps identified"
        structured_block = (
            json.dumps(structured_data, ensure_ascii=False, indent=2)
            if structured_data
            else "(none — fall back to baseline_resume text below)"
        )
        user_content = (
            f"<current_score>{score}</current_score>\n\n"
            f"<identified_gaps>\n{gaps_text}\n</identified_gaps>\n\n"
            f"<structured_data>\n{structured_block}\n</structured_data>\n\n"
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

    def extract_structured(self, source_text: str) -> dict:
        """Parse a free-form profile text into structured JSON via the SDK."""
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=_EXTRACT_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": source_text}],
            )
        except anthropic.APIError as exc:
            raise LLMUnavailableError(
                f"Anthropic API request failed during extract: {exc}"
            ) from exc

        raw = response.content[0].text.strip()  # type: ignore[index]
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
            raw = raw.rstrip("`").strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMInvalidOutputError(
                f"Anthropic API extract returned invalid JSON: {exc}"
            ) from exc
        if not isinstance(data, dict):
            raise LLMInvalidOutputError("Anthropic API extract was not a JSON object")
        logger.info(
            "extract_llm_response model=%s keys=%d tokens_in=%d tokens_out=%d",
            self._model,
            len(data),
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        return data
