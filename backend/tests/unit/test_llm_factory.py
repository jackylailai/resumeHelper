from __future__ import annotations

from backend.app.config import get_settings
from backend.app.services.llm.factory import create_llm_client
from backend.app.services.llm.fake import FakeLLMClient


def test_factory_uses_fake_backend(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:postgres@localhost/test")
    monkeypatch.setenv("LLM_BACKEND", "fake")
    get_settings.cache_clear()
    try:
        assert isinstance(create_llm_client(), FakeLLMClient)
    finally:
        get_settings.cache_clear()
