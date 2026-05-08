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
                [_CLAUDE_BIN, "--print", "-p", prompt],
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
