from __future__ import annotations

import asyncio
import uuid
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.job_listing import JobListing
from backend.app.models.scrape_run import ScrapeRun
from backend.app.services.scrapers import registry as scraper_registry
from backend.app.services.scrapers.base import BaseScraper, JobListingDraft
from backend.app.services.scrapers.pipeline import execute_scrape_run


def _fake_scraper_cls(scraper_source: str):
    class FakeScraper(BaseScraper):
        source: ClassVar[str] = scraper_source

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return None

        async def search(self, keyword: str, limit: int) -> list[JobListingDraft]:
            return [
                JobListingDraft(
                    source=scraper_source,
                    source_id=f"{keyword}-{idx}",
                    title=f"{keyword} Engineer {idx}",
                    company="Example Co",
                    url=f"https://example.com/{scraper_source}/{idx}",
                )
                for idx in range(limit)
            ]

        async def fetch_detail(self, draft: JobListingDraft) -> JobListingDraft:
            draft.description = f"Build backend services for {draft.title}."
            draft.raw_json = {"source": scraper_source, "id": draft.source_id}
            return draft

    return FakeScraper


@pytest.mark.integration
@pytest.mark.parametrize("source", ["104", "yourator"])
def test_execute_scrape_run_tracks_ingestion_stats(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    source: str,
):
    monkeypatch.setitem(scraper_registry.SCRAPERS, source, _fake_scraper_cls(source))
    run = ScrapeRun(source=source, keyword=f"backend-{uuid.uuid4()}", limit=2)
    db_session.add(run)
    db_session.commit()

    completed = asyncio.run(execute_scrape_run(db_session, run.id))

    assert completed.status == "succeeded"
    assert completed.inserted == 2
    assert completed.updated == 0
    assert completed.skipped == 0
    assert completed.failed == 0
    rows = db_session.execute(
        select(JobListing).where(JobListing.source == source)
    ).scalars().all()
    assert any(row.description.startswith("Build backend services") for row in rows)


@pytest.mark.integration
def test_scrape_api_creates_runs_and_reports_status(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
):
    monkeypatch.setattr(
        "backend.app.api.scrape.run_scrape_background",
        lambda _run_ids, _session_factory: None,
    )

    response = client.post(
        "/api/scrape/run",
        json={"source": "all", "keyword": "backend", "limit": 3},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["error"] is None
    assert {run["source"] for run in body["data"]["runs"]} == {"104", "yourator"}

    status_response = client.get("/api/scrape/status")
    assert status_response.status_code == 200
    runs = status_response.json()["data"]["recent_runs"]
    assert len(runs) >= 2
    assert {run["status"] for run in runs[:2]} == {"queued"}


@pytest.mark.integration
def test_scrape_control_blocks_or_replaces_active_runs(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
):
    monkeypatch.setattr(
        "backend.app.api.scrape.run_scrape_control_background",
        lambda *_args, **_kwargs: None,
    )

    first = client.post(
        "/api/scrape/control/start",
        json={
            "source": "all",
            "keyword": "backend",
            "limit": 2,
            "evaluate_after_scrape": False,
        },
    )
    assert first.status_code == 202
    first_runs = first.json()["data"]["runs"]
    assert {run["source"] for run in first_runs} == {"104", "yourator"}

    blocked = client.post(
        "/api/scrape/control/start",
        json={
            "source": "all",
            "keyword": "java",
            "limit": 2,
            "evaluate_after_scrape": False,
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "scrape_already_running"

    replaced = client.post(
        "/api/scrape/control/start",
        json={
            "source": "all_with_linkedin",
            "keyword": "java",
            "limit": 1,
            "evaluate_after_scrape": False,
            "stop_existing": True,
        },
    )
    assert replaced.status_code == 202
    replacement_runs = replaced.json()["data"]["runs"]
    assert {run["source"] for run in replacement_runs} == {
        "104",
        "yourator",
        "linkedin",
    }

    status = client.get("/api/scrape/control")
    assert status.status_code == 200
    recent_runs = status.json()["data"]["recent_runs"]
    cancelled_backend = [
        run
        for run in recent_runs
        if run["keyword"] == "backend" and run["status"] == "cancelled"
    ]
    assert len(cancelled_backend) == 2


@pytest.mark.integration
def test_scrape_control_stop_cancels_queued_runs(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
):
    monkeypatch.setattr(
        "backend.app.api.scrape.run_scrape_control_background",
        lambda *_args, **_kwargs: None,
    )

    response = client.post(
        "/api/scrape/control/start",
        json={
            "source": "104",
            "keyword": "backend",
            "limit": 2,
            "evaluate_after_scrape": False,
        },
    )
    assert response.status_code == 202

    stopped = client.post("/api/scrape/control/stop")
    assert stopped.status_code == 200
    assert stopped.json()["data"]["active"] is False
    assert stopped.json()["meta"]["cancelled_runs"][0]["status"] == "cancelled"
