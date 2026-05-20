from __future__ import annotations

import uuid
from datetime import UTC, datetime

from backend.app.models.proof_point import ProofPoint
from backend.app.services.proof_points import (
    format_proof_points_for_prompt,
    select_relevant_proof_points,
)


class _Query:
    def __init__(self, rows: list[ProofPoint]) -> None:
        self.rows = rows

    def filter(self, *_args: object) -> _Query:
        return self

    def all(self) -> list[ProofPoint]:
        return self.rows


class _Session:
    def __init__(self, rows: list[ProofPoint]) -> None:
        self.rows = rows

    def query(self, _model: object) -> _Query:
        return _Query(self.rows)


def _proof_point(
    *,
    title: str,
    skills: list[str],
    tags: list[str],
    context: str = "",
    metrics: str = "",
    action: str = "",
    result: str = "",
    updated_at: datetime | None = None,
) -> ProofPoint:
    timestamp = updated_at or datetime(2026, 5, 20, tzinfo=UTC)
    return ProofPoint(
        id=uuid.uuid4(),
        title=title,
        context=context or None,
        metrics=metrics or None,
        skills=skills,
        tags=tags,
        action=action or None,
        result=result or None,
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_select_relevant_proof_points_ranks_matching_evidence() -> None:
    relevant = _proof_point(
        title="Reduced checkout latency",
        context="Checkout API performance project",
        metrics="Reduced p95 latency from 900ms to 220ms",
        skills=["FastAPI", "Redis"],
        tags=["performance"],
        action="Added Redis caching and optimized FastAPI handlers.",
    )
    fallback = _proof_point(
        title="PostgreSQL reporting cleanup",
        skills=["PostgreSQL"],
        tags=["analytics"],
        action="Refined SQL reports.",
    )
    irrelevant = _proof_point(
        title="Updated landing page visuals",
        skills=["Figma"],
        tags=["design"],
    )

    selected = select_relevant_proof_points(
        _Session([irrelevant, fallback, relevant]),  # type: ignore[arg-type]
        profile_id=1,
        jd_text=(
            "Backend role needing FastAPI and Redis performance work "
            "with PostgreSQL reporting."
        ),
        gaps=["Show API latency evidence"],
        limit=2,
    )

    assert selected == [relevant, fallback]


def test_format_proof_points_for_prompt_is_compact_evidence() -> None:
    point = _proof_point(
        title="Reduced checkout latency",
        context="Checkout API performance project",
        metrics="Reduced p95 latency from 900ms to 220ms",
        skills=["FastAPI", "Redis"],
        tags=["performance"],
        action="Added Redis caching.",
        result="Cut p95 latency by 75%.",
    )

    rendered = format_proof_points_for_prompt([point])

    assert f"id: {point.id}" in rendered
    assert "title: Reduced checkout latency" in rendered
    assert "metrics: Reduced p95 latency from 900ms to 220ms" in rendered
    assert "skills: FastAPI, Redis" in rendered
    assert "result: Cut p95 latency by 75%." in rendered
