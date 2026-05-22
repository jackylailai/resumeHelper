from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import func, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.api.envelope import success
from backend.app.config import get_settings
from backend.app.db import get_db
from backend.app.models.baseline_profile import BaselineProfile
from backend.app.models.job_listing import JobListing

router = APIRouter()


@router.get("/health")
def health_check(db: Session = Depends(get_db)) -> JSONResponse:
    data = build_health_payload(db)
    return success(data)


@router.get("/health/live")
def liveness_check() -> JSONResponse:
    return success(_liveness())


@router.get("/health/ready")
def readiness_check(db: Session = Depends(get_db)) -> JSONResponse:
    data = build_health_payload(db)
    status_code = 200 if data["readiness"]["status"] == "ready" else 503
    return success(data["readiness"], status_code=status_code)


def build_health_payload(db: Session) -> dict[str, object]:
    settings = get_settings()
    checks: dict[str, dict[str, str]] = {
        "api": {"status": "ok", "message": "API is reachable."},
    }
    counts: dict[str, int | None] = {
        "profiles": None,
        "job_listings": None,
    }

    try:
        db.execute(text("SELECT 1"))
        counts["profiles"] = (
            db.query(func.count(BaselineProfile.id)).scalar()
        )
        counts["job_listings"] = (
            db.query(func.count(JobListing.id)).scalar()
        )
        checks["db"] = {"status": "ok", "message": "Database is reachable."}
    except SQLAlchemyError as exc:
        checks["db"] = {
            "status": "error",
            "message": f"Database check failed: {exc.__class__.__name__}",
        }

    checks["llm"] = _llm_check(settings.llm_backend, settings.anthropic_api_key)

    status = "ok"
    if any(check["status"] == "error" for check in checks.values()):
        status = "degraded"

    profile_count = counts["profiles"] or 0
    listing_count = counts["job_listings"] or 0
    next_actions: list[dict[str, str]] = []
    if checks["db"]["status"] == "error":
        next_actions.append({
            "kind": "db",
            "message": checks["db"]["message"],
        })
    elif profile_count == 0:
        next_actions.append({
            "kind": "profile",
            "message": "Add a profile before evaluating jobs.",
        })
    if checks["db"]["status"] == "ok" and listing_count == 0:
        next_actions.append({
            "kind": "job_listings",
            "message": "Add JD data by using JD Database or a scraper.",
        })
    if checks["llm"]["status"] == "error":
        next_actions.append({
            "kind": "llm",
            "message": checks["llm"]["message"],
        })

    can_evaluate = (
        checks["db"]["status"] == "ok"
        and checks["llm"]["status"] != "error"
        and profile_count > 0
    )
    ready = checks["db"]["status"] == "ok" and checks["llm"]["status"] != "error"

    return {
        "status": status,
        "liveness": _liveness(),
        "readiness": {
            "status": "ready" if ready else "not_ready",
            "checks": {
                "db": checks["db"],
                "llm": checks["llm"],
            },
        },
        "checks": checks,
        "counts": counts,
        "can_evaluate": can_evaluate,
        "next_actions": next_actions,
    }


def _liveness() -> dict[str, str]:
    return {"status": "ok", "message": "API process is running."}


def _llm_check(backend: str, api_key: str) -> dict[str, str]:
    if backend == "anthropic" and not api_key:
        return {
            "status": "error",
            "backend": backend,
            "message": "ANTHROPIC_API_KEY is required for LLM_BACKEND=anthropic.",
        }
    if backend == "claude_cli":
        return {
            "status": "warning",
            "backend": backend,
            "message": "Claude CLI configured; credentials are verified during evaluation.",
        }
    return {
        "status": "ok",
        "backend": backend,
        "message": f"{backend} backend is configured.",
    }
