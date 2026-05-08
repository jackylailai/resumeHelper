from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str

    # LLM
    anthropic_api_key: str = ""
    llm_backend: str = "claude_cli"
    llm_model: str = "claude-sonnet-4-6"
    llm_prompt_version: str = "resume-fit-v1"

    # Storage
    storage_dir: Path = Path("./backend/storage")

    # Resume generation
    resume_gen_threshold: int = 60
    n8n_webhook_url: str = ""

    # Limits
    max_upload_bytes: int = 10 * 1024 * 1024  # 10 MB
    max_jd_chars: int = 5000

    # Server
    port: int = 8000
    log_level: str = "info"

    @field_validator("storage_dir", mode="after")
    @classmethod
    def make_storage_dir(cls, v: Path) -> Path:
        v.mkdir(parents=True, exist_ok=True)
        return v

    @field_validator("llm_backend", mode="after")
    @classmethod
    def normalize_llm_backend(cls, v: str) -> str:
        backend = v.strip().lower()
        if backend not in {"anthropic", "claude_cli", "fake"}:
            raise ValueError("LLM_BACKEND must be one of: anthropic, claude_cli, fake")
        return backend


@lru_cache
def get_settings() -> Settings:
    return Settings()
