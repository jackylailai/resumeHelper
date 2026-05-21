"""needs_tailoring evaluate -> durable worker writes PDF.

Submittable tab lists it and the PDF link returns a 200 PDF."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
from playwright.sync_api import Page, expect

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _wait_for_submittable_with_pdf(base_url: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    last: list[dict] = []
    while time.monotonic() < deadline:
        r = httpx.get(f"{base_url}/api/submittable", timeout=5)
        r.raise_for_status()
        last = r.json()["data"]
        for row in last:
            if row.get("pdf_url"):
                return row
        time.sleep(0.5)
    raise AssertionError(f"no submittable row with pdf_url within {timeout}s; last: {last}")


def _run_tailoring_worker_once(database_url: str) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "backend.app.workers.job_queue",
            "--once",
            "--kind",
            "tailor",
        ],
        check=True,
        cwd=str(PROJECT_ROOT),
        env={**os.environ, "DATABASE_URL": database_url, "LLM_BACKEND": "fake"},
    )


def test_submittable_renders_tailored_pdf(
    live_app: str,
    _e2e_db: str,
    seeded_profile: dict,
    page: Page,
    shots_dir: Path,
) -> None:
    r = httpx.post(
        f"{live_app}/api/evaluate",
        json={
            "jd_text": "Senior backend role. Python, AWS, Kafka. [[score=75]]",
            "profile_id": seeded_profile["id"],
        },
        timeout=30,
    )
    r.raise_for_status()
    body = r.json()["data"]
    assert body["status"] == "needs_tailoring", body
    assert body["tailoring_job_id"], body

    _run_tailoring_worker_once(_e2e_db)
    submittable_row = _wait_for_submittable_with_pdf(live_app)
    pdf_url = submittable_row["pdf_url"]
    assert pdf_url.startswith("/api/generated-resumes/"), pdf_url

    page.goto(f"{live_app}/", wait_until="networkidle")
    page.click('button.tab-btn[data-tab="submittable"]')
    expect(page.locator("#submittable-body tr")).to_have_count(1, timeout=10_000)
    page.screenshot(path=str(shots_dir / "01-submittable.png"), full_page=True)

    r = httpx.get(f"{live_app}{pdf_url}", timeout=10)
    assert r.status_code == 200, r.text
    assert r.headers.get("content-type", "").startswith("application/pdf"), r.headers
    assert r.content[:4] == b"%PDF", r.content[:8]
