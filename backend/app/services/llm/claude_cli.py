from __future__ import annotations

import json
import logging
import subprocess
import time
from pathlib import Path

from backend.app.services.llm import EvaluationResult

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
        result = subprocess.run(
            [_CLAUDE_BIN, "--print", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=120,
        )
        latency_ms = int((time.time() - start) * 1000)

        if result.returncode != 0:
            raise RuntimeError(f"claude CLI failed: {result.stderr[:200]}")

        raw = result.stdout.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
            raw = raw.rstrip("`").strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"claude CLI returned invalid JSON: {exc}\nRaw: {raw[:300]}") from exc

        logger.info("claude_cli score=%d latency_ms=%d", data.get("score", -1), latency_ms)

        return EvaluationResult(
            score=int(data["score"]),
            explanation=data.get("explanation", ""),
            strengths=data.get("strengths", []),
            gaps=data.get("gaps", []),
            token_count_input=None,
            token_count_output=None,
        )
