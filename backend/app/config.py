from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
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
    environment: str = "development"
    port: int = 8000
    log_level: str = "info"
    cors_allowed_origins: str = "*"

    # Optional write-operation guard
    management_auth_enabled: bool = False
    management_auth_token: str = ""
    management_auth_username: str = ""
    management_auth_password: str = ""

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]

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

    @field_validator("environment", mode="after")
    @classmethod
    def normalize_environment(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("cors_allowed_origins", mode="after")
    @classmethod
    def normalize_cors_allowed_origins(cls, v: str) -> str:
        origins = [origin.strip() for origin in v.split(",") if origin.strip()]
        return ",".join(origins) if origins else "*"

    @model_validator(mode="after")
    def validate_production_config(self) -> "Settings":
        if self.environment == "production" and "*" in self.cors_origins:
            raise ValueError("CORS_ALLOWED_ORIGINS cannot include '*' in production")
        if self.management_auth_enabled:
            has_token = bool(self.management_auth_token)
            has_basic = bool(self.management_auth_username and self.management_auth_password)
            if not (has_token or has_basic):
                raise ValueError(
                    "MANAGEMENT_AUTH_TOKEN or MANAGEMENT_AUTH_USERNAME/"
                    "MANAGEMENT_AUTH_PASSWORD is required when MANAGEMENT_AUTH_ENABLED=true"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
