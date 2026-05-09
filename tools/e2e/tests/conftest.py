"""E2E test fixtures.

The suite drives the deployed UI through Playwright against a uvicorn
process running with `LLM_BACKEND=fake`. Tests share that one process for
the session and isolate themselves by truncating data tables before each
test (alembic schema is preserved).

If you already have an app listening, set `E2E_USE_RUNNING_APP=1` and the
session fixture will skip the spawn.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

DEFAULT_DB_URL = "postgresql://postgres:postgres@localhost:5432/resume_helper"
DATABASE_URL = os.environ.get("DATABASE_URL", DEFAULT_DB_URL)
BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8001")
SCREENSHOTS_DIR = Path(__file__).resolve().parent.parent / "screenshots"

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _port_from_url(url: str) -> int:
    return int(url.rsplit(":", 1)[-1].split("/", 1)[0])


def _wait_for_health(url: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{url}/api/health", timeout=2.0)
            if r.status_code == 200:
                return
        except Exception as exc:
            last_err = exc
        time.sleep(0.5)
    raise RuntimeError(f"app at {url} not healthy within {timeout}s (last err: {last_err})")


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


@pytest.fixture(scope="session")
def live_app() -> Iterator[str]:
    """Yield BASE_URL of a running FastAPI app. Starts one if needed."""
    if os.environ.get("E2E_USE_RUNNING_APP"):
        _wait_for_health(BASE_URL, timeout=10)
        yield BASE_URL
        return

    port = _port_from_url(BASE_URL)
    if _port_in_use(port):
        raise RuntimeError(
            f"port {port} already in use — set E2E_USE_RUNNING_APP=1 to reuse it "
            f"or pick a different E2E_BASE_URL"
        )

    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = SCREENSHOTS_DIR.parent / "uvicorn.log"
    env = os.environ.copy()
    env.setdefault("LLM_BACKEND", "fake")
    env.setdefault("DATABASE_URL", DATABASE_URL)

    with log_path.open("w") as log:
        proc = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn",
                "backend.app.main:app", "--port", str(port),
            ],
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    try:
        _wait_for_health(BASE_URL, timeout=30)
        yield BASE_URL
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    engine = create_engine(DATABASE_URL, future=True)
    yield engine
    engine.dispose()


_DATA_TABLES = (
    "generated_resumes",
    "job_analyses",
    "job_listings",
    "baseline_profile",
)


@pytest.fixture(autouse=True)
def _wipe_data_tables(db_engine: Engine, live_app: str) -> None:
    """Truncate per-test data so tests don't leak rows into each other.
    Schema is owned by alembic and untouched."""
    with db_engine.begin() as conn:
        conn.execute(
            text(f"TRUNCATE {', '.join(_DATA_TABLES)} RESTART IDENTITY CASCADE")
        )


@pytest.fixture
def seeded_profile(live_app: str) -> dict:
    """Create a baseline profile via legacy POST /api/profile and return its row."""
    skills = (
        "Senior Backend Engineer with 7 years of Python and Java. "
        "Built FastAPI + Spring Boot services on AWS (EC2, EKS, Lambda) "
        "scaling to 50k QPS. Strong with PostgreSQL, Kafka, Redis, "
        "Docker, Kubernetes, Prometheus, Grafana, GitLab CI."
    )
    r = httpx.post(
        f"{live_app}/api/profile",
        json={"skills_text": skills},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["data"]


@pytest.fixture
def seeded_listings(db_engine: Engine) -> list[dict]:
    """Insert 5 JobListing rows directly. JD descriptions embed [[score=N]]
    markers that FakeLLMClient honours, so different rows score differently
    when batch-evaluated."""
    rows = [
        {
            "id": uuid.uuid4(),
            "source": "104",
            "source_id": f"e2e-{i}",
            "title": title,
            "company": company,
            "location": "Taipei",
            "url": f"https://example.test/jobs/e2e-{i}",
            "description": (
                f"{title} at {company}. We need 5+ years backend, "
                f"Python/Java, Kafka, AWS. [[score={score}]]"
            ),
        }
        for i, (title, company, score) in enumerate(
            [
                ("Senior Backend Engineer", "AcmeCorp", 88),
                ("Platform Engineer", "BetaIO", 75),
                ("Java Developer", "CooLabs", 65),
                ("Site Reliability Engineer", "DataDyne", 50),
                ("Solutions Architect", "EvoTech", 40),
            ]
        )
    ]

    with db_engine.begin() as conn:
        for row in rows:
            conn.execute(
                text(
                    "INSERT INTO job_listings "
                    "(id, source, source_id, title, company, location, url, description) "
                    "VALUES (:id, :source, :source_id, :title, :company, "
                    ":location, :url, :description)"
                ),
                row,
            )
    return rows


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict) -> dict:
    """Standard viewport for screenshot consistency."""
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 900},
    }


@pytest.fixture
def shots_dir(request: pytest.FixtureRequest) -> Path:
    """Per-test screenshot directory: tools/e2e/screenshots/<test-name>/"""
    name = request.node.name
    out = SCREENSHOTS_DIR / name
    out.mkdir(parents=True, exist_ok=True)
    return out
