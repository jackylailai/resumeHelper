from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app import main as app_main
from backend.app.config import Settings, get_settings
from backend.app.main import create_app


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _set_minimal_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./test-observability.db")
    monkeypatch.setenv("LLM_BACKEND", "fake")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    monkeypatch.setenv("STORAGE_DIR", "./backend/storage/test-observability")


def test_production_disallows_wildcard_cors(monkeypatch: pytest.MonkeyPatch):
    _set_minimal_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")

    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS"):
        Settings()


def test_cors_uses_configured_origins(monkeypatch: pytest.MonkeyPatch):
    _set_minimal_env(monkeypatch)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://app.example.com, https://ops.example.com")
    app = create_app()

    with TestClient(app) as client:
        response = client.options(
            "/api/health",
            headers={
                "Origin": "https://app.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://app.example.com"


def test_write_auth_guard_accepts_bearer_token(monkeypatch: pytest.MonkeyPatch):
    _set_minimal_env(monkeypatch)
    monkeypatch.setenv("MANAGEMENT_AUTH_ENABLED", "true")
    monkeypatch.setenv("MANAGEMENT_AUTH_TOKEN", "secret-token")
    app = create_app()

    with TestClient(app) as client:
        denied = client.post("/api/evaluate", json={})
        allowed = client.post(
            "/api/evaluate",
            headers={"Authorization": "Bearer secret-token"},
            json={},
        )

    assert denied.status_code == 401
    assert denied.json()["error"]["code"] == "unauthorized"
    assert denied.headers["X-Request-ID"] == denied.json()["meta"]["request_id"]
    assert allowed.status_code == 422


def test_write_auth_guard_accepts_basic_auth(monkeypatch: pytest.MonkeyPatch):
    _set_minimal_env(monkeypatch)
    monkeypatch.setenv("MANAGEMENT_AUTH_ENABLED", "true")
    monkeypatch.setenv("MANAGEMENT_AUTH_USERNAME", "ops")
    monkeypatch.setenv("MANAGEMENT_AUTH_PASSWORD", "pw")
    credentials = base64.b64encode(b"ops:pw").decode("ascii")
    app = create_app()

    with TestClient(app) as client:
        response = client.post(
            "/api/evaluate",
            headers={"Authorization": f"Basic {credentials}"},
            json={},
        )

    assert response.status_code == 422


def test_health_distinguishes_liveness_and_readiness(client: TestClient):
    response = client.get("/api/health")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["liveness"]["status"] == "ok"
    assert data["readiness"]["status"] == "ready"
    assert set(data["readiness"]["checks"]) == {"db", "llm"}


def test_request_logs_are_structured(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    messages: list[str] = []

    def capture_info(message: object, *args: object, **_kwargs: object) -> None:
        text = str(message)
        messages.append(text % args if args else text)

    monkeypatch.setattr(app_main.logger, "info", capture_info)

    response = client.get("/api/health")

    records = [
        json.loads(message)
        for message in messages
        if message.startswith("{")
    ]
    assert records
    log = records[-1]
    assert log["request_id"] == response.json()["meta"]["request_id"]
    assert log["path"] == "/api/health"
    assert log["status"] == 200
    assert isinstance(log["latency_ms"], float)
