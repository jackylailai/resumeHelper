from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.app.api.envelope import error, success
from backend.app.db import get_db
from backend.app.models.baseline_profile import BaselineProfile
from backend.app.models.proof_point import ProofPoint
from backend.app.schemas.proof_point import (
    ProofPointCreateIn,
    ProofPointOut,
    ProofPointUpdateIn,
)

router = APIRouter()

ProofPointSortBy = Literal["updated_at", "created_at", "title"]
SortDirection = Literal["asc", "desc"]


def _proof_point_out(proof_point: ProofPoint) -> dict:
    return ProofPointOut.model_validate(proof_point).model_dump(mode="json")


def _profile_not_found(profile_id: int) -> JSONResponse:
    return error(
        "not_found",
        f"Profile {profile_id} not found",
        status_code=404,
    )


def _ensure_profile(db: Session, profile_id: int | None) -> JSONResponse | None:
    if profile_id is None:
        return None
    if db.get(BaselineProfile, profile_id) is None:
        return _profile_not_found(profile_id)
    return None


@router.get("/proof-points")
def list_proof_points(
    profile_id: int | None = Query(default=None),
    q: str | None = Query(default=None, max_length=120),
    tag: str | None = Query(default=None, max_length=80),
    skill: str | None = Query(default=None, max_length=80),
    sort_by: ProofPointSortBy = Query(default="updated_at"),
    sort_dir: SortDirection = Query(default="desc"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> JSONResponse:
    query = db.query(ProofPoint)
    if profile_id is not None:
        query = query.filter(ProofPoint.profile_id == profile_id)
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        query = query.filter(
            or_(
                ProofPoint.title.ilike(pattern),
                ProofPoint.context.ilike(pattern),
                ProofPoint.metrics.ilike(pattern),
                ProofPoint.situation.ilike(pattern),
                ProofPoint.task.ilike(pattern),
                ProofPoint.action.ilike(pattern),
                ProofPoint.result.ilike(pattern),
            )
        )
    if tag and tag.strip():
        query = query.filter(ProofPoint.tags.contains([tag.strip()]))
    if skill and skill.strip():
        query = query.filter(ProofPoint.skills.contains([skill.strip()]))

    total = query.count()
    ascending = sort_dir == "asc"
    if sort_by == "title":
        order_expr = func.lower(ProofPoint.title)
        order = order_expr.asc() if ascending else order_expr.desc()
        order_by = [order, ProofPoint.updated_at.desc(), ProofPoint.id.asc()]
    elif sort_by == "created_at":
        order = (
            ProofPoint.created_at.asc()
            if ascending
            else ProofPoint.created_at.desc()
        )
        order_by = [order, ProofPoint.id.asc()]
    else:
        order = (
            ProofPoint.updated_at.asc()
            if ascending
            else ProofPoint.updated_at.desc()
        )
        order_by = [order, ProofPoint.id.asc()]

    rows = query.order_by(*order_by).offset(offset).limit(limit).all()
    return success(
        [_proof_point_out(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
        range_start=0 if not rows else offset + 1,
        range_end=0 if not rows else min(offset + len(rows), total),
        sort_by=sort_by,
        sort_dir=sort_dir,
        profile_id=profile_id,
        q=q,
        tag=tag,
        skill=skill,
    )


@router.post("/proof-points")
def create_proof_point(
    body: ProofPointCreateIn,
    db: Session = Depends(get_db),
) -> JSONResponse:
    profile_error = _ensure_profile(db, body.profile_id)
    if profile_error is not None:
        return profile_error

    proof_point = ProofPoint(
        profile_id=body.profile_id,
        title=body.title,
        context=body.context,
        metrics=body.metrics,
        skills=body.skills,
        tags=body.tags,
        situation=body.situation,
        task=body.task,
        action=body.action,
        result=body.result,
    )
    db.add(proof_point)
    db.commit()
    db.refresh(proof_point)
    return success(_proof_point_out(proof_point), status_code=201)


@router.get("/proof-points/{proof_point_id}")
def get_proof_point(
    proof_point_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> JSONResponse:
    proof_point = db.get(ProofPoint, proof_point_id)
    if proof_point is None:
        return error(
            "not_found",
            f"Proof point {proof_point_id} not found",
            status_code=404,
        )
    return success(_proof_point_out(proof_point))


@router.patch("/proof-points/{proof_point_id}")
def update_proof_point(
    proof_point_id: uuid.UUID,
    body: ProofPointUpdateIn,
    db: Session = Depends(get_db),
) -> JSONResponse:
    proof_point = db.get(ProofPoint, proof_point_id)
    if proof_point is None:
        return error(
            "not_found",
            f"Proof point {proof_point_id} not found",
            status_code=404,
        )
    if "profile_id" in body.model_fields_set:
        profile_error = _ensure_profile(db, body.profile_id)
        if profile_error is not None:
            return profile_error

    for field in (
        "profile_id",
        "title",
        "context",
        "metrics",
        "situation",
        "task",
        "action",
        "result",
    ):
        if field in body.model_fields_set:
            setattr(proof_point, field, getattr(body, field))
    for field in ("skills", "tags"):
        if field in body.model_fields_set:
            setattr(proof_point, field, getattr(body, field) or [])

    db.commit()
    db.refresh(proof_point)
    return success(_proof_point_out(proof_point))


@router.delete("/proof-points/{proof_point_id}")
def delete_proof_point(
    proof_point_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> JSONResponse:
    proof_point = db.get(ProofPoint, proof_point_id)
    if proof_point is None:
        return error(
            "not_found",
            f"Proof point {proof_point_id} not found",
            status_code=404,
        )
    db.delete(proof_point)
    db.commit()
    return success({"deleted": True, "id": str(proof_point_id)})
