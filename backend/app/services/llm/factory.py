from __future__ import annotations

import logging

from backend.app.config import get_settings
from backend.app.services.llm import LLMClient, LLMUnavailableError
from backend.app.services.llm.anthropic import AnthropicLLMClient
from backend.app.services.llm.claude_cli import ClaudeCLIClient
from backend.app.services.llm.fake import FakeLLMClient

logger = logging.getLogger(__name__)


def create_llm_client() -> LLMClient:
    settings = get_settings()
    backend = settings.llm_backend

    if backend == "claude_cli":
        logger.info("llm_backend=claude_cli")
        return ClaudeCLIClient()

    if backend == "anthropic":
        if not settings.anthropic_api_key:
            raise LLMUnavailableError(
                "ANTHROPIC_API_KEY is required when LLM_BACKEND=anthropic"
            )
        logger.info("llm_backend=anthropic model=%s", settings.llm_model)
        return AnthropicLLMClient()

    logger.warning("llm_backend=fake should only be used for local development or tests")
    return FakeLLMClient()
