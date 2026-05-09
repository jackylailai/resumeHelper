"""E2E test fixtures.

Hard isolation: every session spins its OWN ephemeral postgres via
testcontainers AND its OWN uvicorn process. The dev `resume_helper` DB
is never touched, no matter how `DATABASE_URL` is set in the parent
environment. There are no escape hatches — the previous `E2E_USE_RUNNING_APP`
env knob was removed because it could (and did) destroy real data.

`clean_db` is no longer autouse. Tests that want a clean slate request it
explicitly. This makes the data lifecycle visible in each test signature.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from testcontainers.postgres import PostgresContainer

SCREENSHOTS_DIR = Path(__file__).resolve().parent.parent / "screenshots"
PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_for_health(url: str, timeout: float = 30.0) -> None:
    import time
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{url}/api/health", timeout=2.0)
            if r.status_code == 200:
                return
        except Exception as exc:  # pragma: no cover - retry path
            last = exc
        time.sleep(0.5)
    raise RuntimeError(f"app at {url} not healthy in {timeout}s (last err: {last})")


@pytest.fixture(scope="session")
def _e2e_postgres() -> Iterator[str]:
    """Spin a fresh postgres just for this test session. Discarded on exit."""
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def _e2e_db(_e2e_postgres: str) -> str:
    """Apply alembic migrations to the ephemeral DB."""
    subprocess.run(
        [
            sys.executable, "-m", "alembic",
            "-c", "backend/alembic.ini", "upgrade", "head",
        ],
        check=True,
        cwd=str(PROJECT_ROOT),
        env={**os.environ, "DATABASE_URL": _e2e_postgres},
    )
    return _e2e_postgres


@pytest.fixture(scope="session")
def live_app(_e2e_db: str) -> Iterator[str]:
    """Yield BASE_URL of a uvicorn instance bound to the e2e DB."""
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = SCREENSHOTS_DIR.parent / "uvicorn.log"

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "DATABASE_URL": _e2e_db,
        "LLM_BACKEND": "fake",
    }

    with log_path.open("w") as log:
        proc = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn",
                "backend.app.main:app", "--host", "127.0.0.1", "--port", str(port),
            ],
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    try:
        _wait_for_health(base_url, timeout=30)
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="session")
def db_engine(_e2e_db: str) -> Iterator[Engine]:
    """SQLAlchemy engine pointed at the ephemeral DB only.

    By construction this can never connect to the dev DB — `_e2e_db` is
    derived from a testcontainers instance with a random port, not from
    any user-controlled env var.
    """
    engine = create_engine(_e2e_db, future=True)
    yield engine
    engine.dispose()


_DATA_TABLES = (
    "generated_resumes",
    "job_analyses",
    "job_listings",
    "baseline_profile",
)


@pytest.fixture
def clean_db(db_engine: Engine) -> None:
    """Truncate per-test data tables. NOT autouse: tests opt in explicitly
    so the data lifecycle is visible in each test signature. Safe by
    construction because db_engine only ever points at the e2e
    testcontainers DB."""
    with db_engine.begin() as conn:
        conn.execute(
            text(f"TRUNCATE {', '.join(_DATA_TABLES)} RESTART IDENTITY CASCADE")
        )


@pytest.fixture
def seeded_profile(live_app: str, clean_db: None) -> dict:
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
def seeded_listings(db_engine: Engine, clean_db: None) -> list[dict]:
    """Insert 5 JobListing rows directly. JD descriptions embed [[score=N]]
    markers that FakeLLMClient honours, so different rows score
    differently when batch-evaluated."""
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
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 900},
    }


@pytest.fixture
def shots_dir(request: pytest.FixtureRequest) -> Path:
    name = request.node.name
    out = SCREENSHOTS_DIR / name
    out.mkdir(parents=True, exist_ok=True)
    return out
