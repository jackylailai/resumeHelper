"""POST /api/generated-resumes/{id}/beautify — produces ResumeBeautification row + URLs."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# WeasyPrint needs Pango at runtime. Skip the suite when the lib can't import
# (e.g. host dev machines without `brew install pango`); CI installs it.
try:
    import weasyprint  # noqa: F401
except (ImportError, OSError) as _wp_exc:
    pytest.skip(
        f"weasyprint unavailable ({_wp_exc.__class__.__name__}: {_wp_exc}); "
        "install system Pango deps to run beautify tests",
        allow_module_level=True,
    )

_JD = "Backend engineer with Python skills needed."


def _create_resume(client: TestClient) -> tuple[str, str]:
    """Seed a profile, evaluate to needs_tailoring, post a callback resume.

    Returns (job_id, generated_resume_id).
    """
    client.post("/api/profile", json={"skills_text": "Python, FastAPI"})
    eval_resp = client.post("/api/evaluate", json={"jd_text": _JD})
    job_id = eval_resp.json()["data"]["job_analysis_id"]
    cb = client.post(
        "/api/callback",
        json={
            "job_analysis_id": job_id,
            "resume_text": "# Resume\n\n## Skills\nPython, FastAPI\n\n## Experience\nSWE\n",
            "prompt_version": "v1",
        },
    )
    return job_id, cb.json()["data"]["id"]


@pytest.mark.integration
def test_beautify_creates_row_with_urls(client: TestClient):
    _, resume_id = _create_resume(client)

    r = client.post(
        f"/api/generated-resumes/{resume_id}/beautify",
        json={"style": "modern"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["generated_resume_id"] == resume_id
    assert data["style"] == "modern"
    assert data["html_url"].startswith("/api/beautifications/")
    assert data["pdf_url"].startswith("/api/beautifications/")
    assert data["html_url"].endswith("/html")
    assert data["pdf_url"].endswith("/pdf")


@pytest.mark.integration
def test_beautify_html_endpoint_returns_html(client: TestClient):
    _, resume_id = _create_resume(client)

    create = client.post(
        f"/api/generated-resumes/{resume_id}/beautify",
        json={"style": "classic"},
    )
    html_url = create.json()["data"]["html_url"]

    r = client.get(html_url)
    assert r.status_code == 200, r.text
    assert "html" in r.headers.get("content-type", "")
    body = r.text
    assert "<!DOCTYPE html>" in body
    assert "</html>" in body


@pytest.mark.integration
def test_beautify_appears_in_history_detail(client: TestClient):
    job_id, resume_id = _create_resume(client)

    client.post(
        f"/api/generated-resumes/{resume_id}/beautify",
        json={"style": "minimal"},
    )

    r = client.get(f"/api/history/{job_id}")
    assert r.status_code == 200
    resumes = r.json()["data"]["generated_resumes"]
    assert resumes
    beautifications = resumes[0]["beautifications"]
    assert len(beautifications) == 1
    assert beautifications[0]["style"] == "minimal"
    assert beautifications[0]["html_url"].startswith("/api/beautifications/")
    assert beautifications[0]["pdf_url"].startswith("/api/beautifications/")


@pytest.mark.integration
def test_beautify_invalid_llm_output_returns_502(client: TestClient):
    _, resume_id = _create_resume(client)

    class _InvalidBeautifyLLM:
        def beautify(self, _resume_markdown: str, style: str = "modern") -> dict:
            return {
                "html_content": (
                    "<!DOCTYPE html><html><head><style>body{}</style></head>"
                    "<body><script>alert(1)</script></body></html>"
                ),
                "prompt_version": f"beautify-{style}",
            }

    client.app.state.llm_client = _InvalidBeautifyLLM()

    r = client.post(
        f"/api/generated-resumes/{resume_id}/beautify",
        json={"style": "modern"},
    )

    assert r.status_code == 502
    assert r.json()["error"]["code"] == "llm_invalid_output"


@pytest.mark.integration
def test_beautify_unknown_resume_returns_404(client: TestClient):
    r = client.post(
        "/api/generated-resumes/00000000-0000-0000-0000-000000000000/beautify",
        json={"style": "modern"},
    )
    assert r.status_code == 404
