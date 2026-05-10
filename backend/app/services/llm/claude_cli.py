from __future__ import annotations

import json
import logging
import subprocess
import time
from pathlib import Path

from backend.app.services.llm import (
    EvaluationResult,
    LLMInvalidOutputError,
    LLMUnavailableError,
)

logger = logging.getLogger(__name__)

_MODES_DIR = Path(__file__).parent.parent.parent.parent.parent / "modes"
_CLAUDE_BIN = "claude"


def _render(template_path: Path, **kwargs: str) -> str:
    text = template_path.read_text()
    for key, value in kwargs.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text


class ClaudeCLIClient:
    """Calls the local `claude` CLI — uses Claude Code subscription, no API key needed."""

    def __init__(self, model: str = "claude-opus-4-7") -> None:
        self.model = model

    def evaluate(
        self,
        parsed_text: str,
        job_description: str,
        prompt_version: str,
    ) -> EvaluationResult:
        prompt = _render(
            _MODES_DIR / "score.md",
            BASELINE_SKILLS=parsed_text,
            JOB_DESCRIPTION=job_description,
        )

        start = time.time()
        try:
            result = subprocess.run(
                [_CLAUDE_BIN, "--print", "-p", prompt, "--model", self.model],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except FileNotFoundError as exc:
            raise LLMUnavailableError("claude CLI executable was not found") from exc
        except subprocess.TimeoutExpired as exc:
            raise LLMUnavailableError("claude CLI timed out") from exc
        latency_ms = int((time.time() - start) * 1000)

        if result.returncode != 0:
            raise LLMUnavailableError(f"claude CLI failed: {result.stderr[:200]}")

        raw = result.stdout.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
            raw = raw.rstrip("`").strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMInvalidOutputError(
                f"claude CLI returned invalid JSON: {exc}"
            ) from exc

        try:
            score = int(data["score"])
        except (KeyError, TypeError, ValueError) as exc:
            raise LLMInvalidOutputError(
                "claude CLI response did not include a valid score"
            ) from exc
        if score < 0 or score > 100:
            raise LLMInvalidOutputError(f"claude CLI score out of range: {score}")

        logger.info("claude_cli score=%d latency_ms=%d", score, latency_ms)

        return EvaluationResult(
            score=score,
            explanation=data.get("explanation", ""),
            strengths=data.get("strengths", []),
            gaps=data.get("gaps", []),
            token_count_input=None,
            token_count_output=None,
        )

    def tailor(
        self,
        baseline_text: str,
        jd_text: str,
        gaps: list[str],
        score: int,
        structured_data: dict | None = None,
    ) -> dict:
        """Generate a tailored resume in Markdown via the `claude` CLI.

        The fallback in workers/tailor.py used to fire whenever the active LLM
        client lacked this method — that produced placeholder text like
        "Score: 78 / KEY SKILLS / <jd snippet>" instead of a real resume.
        """
        structured_block = (
            json.dumps(structured_data, ensure_ascii=False, indent=2)
            if structured_data
            else "(none — fall back to baseline_skills text below)"
        )
        prompt = _render(
            _MODES_DIR / "generate.md",
            BASELINE_SKILLS=baseline_text,
            JOB_DESCRIPTION=jd_text,
            STRUCTURED_DATA=structured_block,
        )

        start = time.time()
        try:
            result = subprocess.run(
                [_CLAUDE_BIN, "--print", "-p", prompt, "--model", self.model],
                capture_output=True,
                text=True,
                timeout=180,
            )
        except FileNotFoundError as exc:
            raise LLMUnavailableError("claude CLI executable was not found") from exc
        except subprocess.TimeoutExpired as exc:
            raise LLMUnavailableError("claude CLI timed out during tailoring") from exc
        latency_ms = int((time.time() - start) * 1000)

        if result.returncode != 0:
            raise LLMUnavailableError(
                f"claude CLI tailoring failed: {result.stderr[:200]}"
            )

        tailored = result.stdout.strip()
        if tailored.startswith("```"):
            tailored = "\n".join(tailored.split("\n")[1:])
            tailored = tailored.rstrip("`").strip()

        if not tailored:
            raise LLMInvalidOutputError("claude CLI returned empty tailored resume")

        logger.info(
            "claude_cli tailor latency_ms=%d chars=%d", latency_ms, len(tailored)
        )

        return {
            "tailoring_suggestions": [],
            "tailored_resume": tailored,
        }

    def beautify(
        self,
        resume_markdown: str,
        style: str = "modern",
    ) -> dict:
        """Transform a tailored markdown resume into a styled, self-contained HTML doc.

        The HTML is produced by `claude --print` using `modes/beautify.md`. The
        prompt forbids fabrication and requires verbatim preservation of every
        number / proper noun in the input — so the output content is a strict
        subset of the input markdown, just visually restructured.
        """
        prompt = _render(
            _MODES_DIR / "beautify.md",
            RESUME_MARKDOWN=resume_markdown,
            STYLE=style,
        )

        start = time.time()
        try:
            result = subprocess.run(
                [_CLAUDE_BIN, "--print", "-p", prompt, "--model", self.model],
                capture_output=True,
                text=True,
                timeout=180,
            )
        except FileNotFoundError as exc:
            raise LLMUnavailableError("claude CLI executable was not found") from exc
        except subprocess.TimeoutExpired as exc:
            raise LLMUnavailableError("claude CLI timed out during beautify") from exc
        latency_ms = int((time.time() - start) * 1000)

        if result.returncode != 0:
            raise LLMUnavailableError(
                f"claude CLI beautify failed: {result.stderr[:200]}"
            )

        html = result.stdout.strip()
        if html.startswith("```"):
            html = "\n".join(html.split("\n")[1:])
            html = html.rstrip("`").strip()

        if "<html" not in html.lower() or "</html>" not in html.lower():
            raise LLMInvalidOutputError(
                "claude CLI beautify did not return a complete HTML document"
            )

        logger.info(
            "claude_cli beautify style=%s latency_ms=%d chars=%d",
            style,
            latency_ms,
            len(html),
        )

        return {"html_content": html, "prompt_version": "beautify-v1"}

    def extract_structured(self, source_text: str) -> dict:
        """Parse a free-form profile text into a structured JSON dict via the
        `claude` CLI using `modes/extract.md`. Returns the parsed dict; raises
        LLMInvalidOutputError if the CLI does not return valid JSON.
        """
        prompt = _render(_MODES_DIR / "extract.md", SOURCE_TEXT=source_text)

        start = time.time()
        try:
            result = subprocess.run(
                [_CLAUDE_BIN, "--print", "-p", prompt, "--model", self.model],
                capture_output=True,
                text=True,
                timeout=180,
            )
        except FileNotFoundError as exc:
            raise LLMUnavailableError("claude CLI executable was not found") from exc
        except subprocess.TimeoutExpired as exc:
            raise LLMUnavailableError("claude CLI timed out during extract") from exc
        latency_ms = int((time.time() - start) * 1000)

        if result.returncode != 0:
            raise LLMUnavailableError(
                f"claude CLI extract failed: {result.stderr[:200]}"
            )

        raw = result.stdout.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
            raw = raw.rstrip("`").strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMInvalidOutputError(
                f"claude CLI extract returned invalid JSON: {exc}; raw[:200]={raw[:200]!r}"
            ) from exc
        if not isinstance(data, dict):
            raise LLMInvalidOutputError(
                "claude CLI extract did not return a JSON object"
            )

        logger.info(
            "claude_cli extract latency_ms=%d keys=%d", latency_ms, len(data)
        )
        return data
