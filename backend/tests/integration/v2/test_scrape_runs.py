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
from backend.app.services.scrapers.pipeline import DescriptionFilter, execute_scrape_run


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


def _fake_scraper_with_descriptions(scraper_source: str, descriptions: list[str]):
    """Fake scraper whose search returns up to len(descriptions) drafts and whose
    fetch_detail attaches the matching description by index."""

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
                for idx in range(min(limit, len(descriptions)))
            ]

        async def fetch_detail(self, draft: JobListingDraft) -> JobListingDraft:
            idx = int(draft.source_id.rsplit("-", 1)[-1])
            draft.description = descriptions[idx]
            draft.raw_json = {"source": scraper_source, "id": draft.source_id}
            return draft

    return FakeScraper


@pytest.mark.integration
def test_advanced_filter_default_off_leaves_behaviour_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
):
    """With no must_contain set, scrape behaves exactly like before."""
    source = "104"
    monkeypatch.setitem(scraper_registry.SCRAPERS, source, _fake_scraper_cls(source))
    run = ScrapeRun(source=source, keyword=f"kw-{uuid.uuid4()}", limit=2)
    db_session.add(run)
    db_session.commit()

    completed = asyncio.run(execute_scrape_run(db_session, run.id))

    assert completed.status == "succeeded"
    assert completed.inserted == 2
    assert completed.skipped_by_filter == 0


@pytest.mark.integration
def test_advanced_filter_and_substring_skips_non_matches(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
):
    """AND mode: a draft must contain every term in its description to survive."""
    source = "104"
    descriptions = [
        "Build services with kubernetes and terraform.",  # match
        "Maintain a kubernetes-only cluster.",  # missing terraform
        "Build with kubernetes and terraform pipelines.",  # match
        "Build with python only.",  # missing both
    ]
    monkeypatch.setitem(
        scraper_registry.SCRAPERS,
        source,
        _fake_scraper_with_descriptions(source, descriptions),
    )
    run = ScrapeRun(
        source=source,
        keyword=f"kw-{uuid.uuid4()}",
        limit=10,
        must_contain=["kubernetes", "terraform"],
        match_mode="all",
        regex=False,
    )
    db_session.add(run)
    db_session.commit()

    completed = asyncio.run(execute_scrape_run(db_session, run.id))

    assert completed.status == "succeeded"
    assert completed.inserted == 2
    assert completed.skipped_by_filter == 2
    rows = db_session.execute(
        select(JobListing).where(
            JobListing.source == source,
            JobListing.source_id.like(f"{run.keyword}-%"),
        )
    ).scalars().all()
    assert all("terraform" in row.description.lower() for row in rows)
    assert len(rows) == 2


@pytest.mark.integration
def test_advanced_filter_any_substring_keeps_either_match(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
):
    """OR mode: a draft survives if any term appears in its description."""
    source = "104"
    descriptions = [
        "Pure golang shop with grpc.",  # match (golang)
        "Heavy postgres workloads.",  # match (postgres)
        "Frontend role with react and typescript.",  # neither
    ]
    monkeypatch.setitem(
        scraper_registry.SCRAPERS,
        source,
        _fake_scraper_with_descriptions(source, descriptions),
    )
    run = ScrapeRun(
        source=source,
        keyword=f"kw-{uuid.uuid4()}",
        limit=10,
        must_contain=["golang", "postgres"],
        match_mode="any",
        regex=False,
    )
    db_session.add(run)
    db_session.commit()

    completed = asyncio.run(execute_scrape_run(db_session, run.id))

    assert completed.status == "succeeded"
    assert completed.inserted == 2
    assert completed.skipped_by_filter == 1


@pytest.mark.integration
def test_advanced_filter_regex_mode(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
):
    """Regex mode applies re.search case-insensitively against the description."""
    source = "104"
    descriptions = [
        "Senior Python 3.11 engineer.",  # match \bpython\s*3\.\d+
        "We use Python 2.7 internals.",  # match
        "We use Ruby 3.0 here.",  # no match
    ]
    monkeypatch.setitem(
        scraper_registry.SCRAPERS,
        source,
        _fake_scraper_with_descriptions(source, descriptions),
    )
    run = ScrapeRun(
        source=source,
        keyword=f"kw-{uuid.uuid4()}",
        limit=10,
        must_contain=[r"python\s*\d+\.\d+"],
        match_mode="all",
        regex=True,
    )
    db_session.add(run)
    db_session.commit()

    completed = asyncio.run(execute_scrape_run(db_session, run.id))

    assert completed.status == "succeeded"
    assert completed.inserted == 2
    assert completed.skipped_by_filter == 1


@pytest.mark.integration
def test_advanced_filter_feed_exhausted_under_limit(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
):
    """If the feed runs out before `limit` matches are found, the run still succeeds with fewer rows."""
    source = "104"
    descriptions = [
        "kubernetes shop.",  # match
        "frontend only.",  # no match
        "another kubernetes role.",  # match
        "ios role.",  # no match
    ]
    monkeypatch.setitem(
        scraper_registry.SCRAPERS,
        source,
        _fake_scraper_with_descriptions(source, descriptions),
    )
    run = ScrapeRun(
        source=source,
        keyword=f"kw-{uuid.uuid4()}",
        limit=10,
        must_contain=["kubernetes"],
        match_mode="all",
        regex=False,
    )
    db_session.add(run)
    db_session.commit()

    completed = asyncio.run(execute_scrape_run(db_session, run.id))

    assert completed.status == "succeeded"
    assert completed.inserted == 2
    assert completed.skipped_by_filter == 2


def test_description_filter_from_optional_normalises_input():
    """Whitespace-only terms are dropped; an empty result returns None."""
    assert DescriptionFilter.from_optional(None) is None
    assert DescriptionFilter.from_optional([]) is None
    assert DescriptionFilter.from_optional(["   "]) is None

    f = DescriptionFilter.from_optional(["  kubernetes  ", "", "terraform"])
    assert f is not None
    assert f.terms == ("kubernetes", "terraform")
    assert f.mode == "all"

    with pytest.raises(ValueError):
        DescriptionFilter.from_optional(["k8s"], mode="invalid")


def test_description_filter_regex_bad_pattern_drops_listing():
    """An invalid regex pattern fails closed: every description is filtered out."""
    f = DescriptionFilter(terms=("[invalid",), mode="all", regex=True)
    assert f.matches("kubernetes everywhere") is False


@pytest.mark.integration
def test_scrape_api_passes_advanced_filter_through(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
):
    """API: POST /api/scrape/run persists must_contain/match_mode/regex on the run."""
    monkeypatch.setattr(
        "backend.app.api.scrape.run_scrape_background",
        lambda _run_ids, _session_factory: None,
    )
    response = client.post(
        "/api/scrape/run",
        json={
            "source": "104",
            "keyword": "backend",
            "limit": 5,
            "must_contain": ["kubernetes", "terraform"],
            "match_mode": "any",
            "regex": False,
        },
    )
    assert response.status_code == 202
    runs = response.json()["data"]["runs"]
    assert len(runs) == 1
    assert runs[0]["must_contain"] == ["kubernetes", "terraform"]
    assert runs[0]["match_mode"] == "any"
    assert runs[0]["regex"] is False


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
