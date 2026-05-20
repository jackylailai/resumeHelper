from __future__ import annotations

import re
from collections.abc import Sequence

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.app.models.proof_point import ProofPoint

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#.-]{1,}", re.IGNORECASE)
_STOPWORDS = {
    "and",
    "are",
    "for",
    "from",
    "have",
    "into",
    "role",
    "that",
    "the",
    "this",
    "with",
    "you",
    "your",
}


def select_relevant_proof_points(
    db: Session,
    *,
    profile_id: int | None,
    jd_text: str,
    gaps: Sequence[str] = (),
    limit: int = 5,
) -> list[ProofPoint]:
    """Return proof points relevant to a JD for the selected profile.

    Profile-scoped proof points and global proof points are eligible. Selection is
    deliberately conservative: a point must share a meaningful skill, tag, or
    content token with the JD/gaps before it can reach the prompt.
    """
    if limit <= 0:
        return []

    query = db.query(ProofPoint)
    if profile_id is None:
        query = query.filter(ProofPoint.profile_id.is_(None))
    else:
        query = query.filter(
            or_(ProofPoint.profile_id == profile_id, ProofPoint.profile_id.is_(None))
        )

    search_text = " ".join([jd_text, *gaps])
    ranked: list[tuple[int, ProofPoint]] = []
    for proof_point in query.all():
        score = _score_proof_point(proof_point, search_text)
        if score > 0:
            ranked.append((score, proof_point))

    ranked.sort(
        key=lambda item: (
            -item[0],
            -(item[1].updated_at or item[1].created_at).timestamp(),
            item[1].title.casefold(),
        ),
    )
    return [proof_point for _, proof_point in ranked[:limit]]


def format_proof_points_for_prompt(proof_points: Sequence[ProofPoint]) -> str:
    """Render selected proof points as compact evidence for the tailor prompt."""
    if not proof_points:
        return "(none)"

    lines: list[str] = []
    for index, proof_point in enumerate(proof_points, start=1):
        lines.append(f"{index}. id: {proof_point.id}")
        lines.append(f"   title: {proof_point.title}")
        _append_field(lines, "context", proof_point.context)
        _append_field(lines, "metrics", proof_point.metrics)
        _append_list_field(lines, "skills", proof_point.skills or [])
        _append_list_field(lines, "tags", proof_point.tags or [])
        _append_field(lines, "situation", proof_point.situation)
        _append_field(lines, "task", proof_point.task)
        _append_field(lines, "action", proof_point.action)
        _append_field(lines, "result", proof_point.result)
    return "\n".join(lines)


def _score_proof_point(proof_point: ProofPoint, search_text: str) -> int:
    folded_search = search_text.casefold()
    search_tokens = _tokens(search_text)
    point_tokens = _tokens(_proof_point_text(proof_point))

    score = len(search_tokens.intersection(point_tokens))
    for skill in proof_point.skills or []:
        score += _phrase_score(
            str(skill), folded_search, search_tokens, exact=8, token=4
        )
    for tag in proof_point.tags or []:
        score += _phrase_score(
            str(tag), folded_search, search_tokens, exact=5, token=2
        )
    return score


def _phrase_score(
    phrase: str,
    folded_search: str,
    search_tokens: set[str],
    *,
    exact: int,
    token: int,
) -> int:
    value = phrase.strip().casefold()
    if not value:
        return 0
    if value in folded_search:
        return exact
    phrase_tokens = _tokens(value)
    if phrase_tokens.intersection(search_tokens):
        return token
    return 0


def _proof_point_text(proof_point: ProofPoint) -> str:
    parts = [
        proof_point.title,
        proof_point.context or "",
        proof_point.metrics or "",
        proof_point.situation or "",
        proof_point.task or "",
        proof_point.action or "",
        proof_point.result or "",
        *list(proof_point.skills or []),
        *list(proof_point.tags or []),
    ]
    return " ".join(parts)


def _tokens(text: str) -> set[str]:
    return {
        token.casefold()
        for token in _TOKEN_RE.findall(text)
        if token.casefold() not in _STOPWORDS
    }


def _append_field(lines: list[str], label: str, value: str | None) -> None:
    if value:
        lines.append(f"   {label}: {value.strip()}")


def _append_list_field(lines: list[str], label: str, values: Sequence[str]) -> None:
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    if cleaned:
        lines.append(f"   {label}: {', '.join(cleaned)}")
