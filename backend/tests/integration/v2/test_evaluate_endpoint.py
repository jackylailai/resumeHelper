"""P1-T04: POST /api/evaluate — TDD RED."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from backend.app.config import get_settings
from backend.app.services.llm import LLMInvalidOutputError, LLMUnavailableError

_JD = "Looking for a Python backend engineer with FastAPI and PostgreSQL experience."


@pytest.mark.integration
def test_evaluate_returns_score(client: TestClient):
    client.post("/api/profile", json={"skills_text": "Python, FastAPI, PostgreSQL"})
    r = client.post("/api/evaluate", json={"jd_text": _JD})
    assert r.status_code == 200
    data = r.json()["data"]
    assert 0 <= data["score"] <= 100
    assert data["explanation"]
    assert isinstance(data["strengths"], list)
    assert isinstance(data["gaps"], list)


@pytest.mark.integration
def test_evaluate_same_jd_twice_uses_cache(client: TestClient):
    client.post("/api/profile", json={"skills_text": "Python, FastAPI"})
    r1 = client.post("/api/evaluate", json={"jd_text": _JD})
    r2 = client.post("/api/evaluate", json={"jd_text": _JD})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json()["meta"].get("cached") is True


@pytest.mark.integration
def test_evaluate_without_profile_returns_404(client: TestClient):
    r = client.post("/api/evaluate", json={"jd_text": _JD})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


@pytest.mark.integration
def test_evaluate_missing_jd_returns_422(client: TestClient):
    client.post("/api/profile", json={"skills_text": "Python"})
    r = client.post("/api/evaluate", json={})
    assert r.status_code == 422


@pytest.mark.integration
def test_evaluate_long_google_bmc_jd_returns_json_400(client: TestClient):
    """#51: long JD input should fail with a clear JSON envelope, not HTML/plain text."""
    client.post("/api/profile", json={"skills_text": "Python, FastAPI, PostgreSQL"})
    settings = get_settings()
    jd = (
        "Google Business Messages Commerce job description. "
        "Responsibilities include backend platform ownership, distributed systems, "
        "product collaboration, observability, privacy reviews, launch readiness, "
        "API design, incident response, and partner integrations. "
    )
    repeats = (settings.max_jd_chars // len(jd)) + 2
    long_jd = (jd * repeats)[: settings.max_jd_chars + 1]

    r = client.post("/api/evaluate", json={"jd_text": long_jd})

    assert r.status_code == 400
    assert r.headers["content-type"].startswith("application/json")
    body = r.json()
    assert body["data"] is None
    assert body["error"]["code"] == "jd_too_long"
    assert body["error"]["details"]["actual_chars"] == settings.max_jd_chars + 1
    assert body["error"]["details"]["max_chars"] == settings.max_jd_chars


@pytest.mark.integration
def test_evaluate_stores_job_analysis(client: TestClient):
    client.post("/api/profile", json={"skills_text": "Python, FastAPI"})
    client.post("/api/evaluate", json={"jd_text": _JD})
    history = client.get("/api/history").json()["data"]
    assert len(history) >= 1
    assert history[0]["score"] is not None


@pytest.mark.integration
def test_evaluate_returns_json_on_unhandled_exception(client: TestClient):
    """#51: a blowup inside the LLM (e.g. context overflow) must still yield
    JSON, not plain-text 'Internal Server Error' which crashes the front end."""
    client.post("/api/profile", json={"skills_text": "Python"})

    class _RaisingLLM:
        def evaluate(self, *_args, **_kwargs):
            raise RuntimeError("simulated LLM context overflow")

        def tailor(self, *_args, **_kwargs):
            raise NotImplementedError

    client.app.state.llm_client = _RaisingLLM()

    # The shared client fixture sets raise_server_exceptions=True (so unrelated
    # bugs surface in tests). For this test we explicitly want to inspect the
    # response, so wrap the same app with a non-raising client.
    with TestClient(client.app, raise_server_exceptions=False) as nc:
        r = nc.post(
            "/api/evaluate",
            json={"jd_text": _JD + " a different jd to bypass the cache"},
        )
    assert r.status_code == 500
    body = r.json()
    assert body["data"] is None
    assert body["error"]["code"] == "internal_error"
    assert body["error"]["details"]["request_id"]


@pytest.mark.integration
def test_evaluate_returns_json_on_llm_unavailable(client: TestClient):
    client.post("/api/profile", json={"skills_text": "Python"})

    class _UnavailableLLM:
        def evaluate(self, *_args, **_kwargs):
            raise LLMUnavailableError("claude CLI executable was not found")

    client.app.state.llm_client = _UnavailableLLM()

    r = client.post("/api/evaluate", json={"jd_text": _JD + " unavailable"})

    assert r.status_code == 503
    body = r.json()
    assert body["error"]["code"] == "llm_unavailable"


@pytest.mark.integration
def test_evaluate_returns_json_on_llm_invalid_output(client: TestClient):
    client.post("/api/profile", json={"skills_text": "Python"})

    class _InvalidOutputLLM:
        def evaluate(self, *_args, **_kwargs):
            raise LLMInvalidOutputError("score out of range")

    client.app.state.llm_client = _InvalidOutputLLM()

    r = client.post("/api/evaluate", json={"jd_text": _JD + " invalid output"})

    assert r.status_code == 502
    body = r.json()
    assert body["error"]["code"] == "llm_invalid_output"
