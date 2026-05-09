from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.app.api.envelope import error, success
from backend.app.config import get_settings

router = APIRouter()

_PING_PROMPT = "reply with the literal text PONG and nothing else"
_OUTPUT_LIMIT = 500
_TIMEOUT_SECONDS = 60


@router.get("/debug/claude-cli-ping")
def claude_cli_ping() -> JSONResponse:
    settings = get_settings()
    if settings.environment == "production":
        return error(
            "not_available",
            "Debug endpoints are disabled in production.",
            status_code=404,
        )

    claude_bin = shutil.which("claude")
    home = os.environ.get("HOME", "")
    claude_dir = Path(home) / ".claude" if home else None
    claude_json = Path(home) / ".claude.json" if home else None
    payload: dict[str, object] = {
        "ok": False,
        "returncode": None,
        "stdout": "",
        "stderr": "",
        "latency_ms": None,
        "claude_bin_path": claude_bin,
        "home": home,
        "claude_dir_exists": bool(claude_dir and claude_dir.exists()),
        "claude_json_exists": bool(claude_json and claude_json.exists()),
        "oauth_token_set": bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")),
        "anthropic_api_key_set": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "model_used": settings.llm_model,
    }

    if claude_bin is None:
        payload["stderr"] = "claude CLI not found on PATH"
        return success(payload)

    start = time.perf_counter()
    try:
        result = subprocess.run(
            [claude_bin, "--print", "-p", _PING_PROMPT, "--model", settings.llm_model],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        payload["latency_ms"] = int((time.perf_counter() - start) * 1000)
        payload["stderr"] = f"timeout after {_TIMEOUT_SECONDS}s: {exc}"
        return success(payload)
    except OSError as exc:
        payload["stderr"] = f"failed to spawn claude CLI: {exc}"
        return success(payload)

    latency_ms = int((time.perf_counter() - start) * 1000)
    stdout = (result.stdout or "")[:_OUTPUT_LIMIT]
    stderr = (result.stderr or "")[:_OUTPUT_LIMIT]

    payload.update(
        {
            "ok": result.returncode == 0 and "PONG" in stdout.upper(),
            "returncode": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "latency_ms": latency_ms,
        }
    )
    return success(payload)
