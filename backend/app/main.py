from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.api.envelope import error, reset_request_id, set_request_id
from backend.app.api.evaluations import router as evaluations_router
from backend.app.api.health import router as health_router
from backend.app.api.job_listings import router as job_listings_router
from backend.app.api.jobs import router as jobs_router
from backend.app.api.resumes import router as resumes_router
from backend.app.config import get_settings
from backend.app.db import SessionLocal
from backend.app.services.evaluator import LLMInvalidScoreError, LLMUnavailableError
from backend.app.services.llm.factory import create_llm_client

logger = logging.getLogger(__name__)


def _validation_error_details(exc: RequestValidationError) -> list[dict[str, object]]:
    details: list[dict[str, object]] = []
    for item in exc.errors():
        details.append(
            {
                "loc": [str(part) for part in item.get("loc", [])],
                "msg": str(item.get("msg", "Validation error")),
                "type": str(item.get("type", "validation_error")),
            }
        )
    return details


def _recover_orphaned_jobs() -> None:
    """On startup, mark any jobs stuck in 'running' as failed.

    BackgroundTasks are in-process; a crash leaves jobs in 'running' forever.
    """
    from backend.app.models.evaluation_job import EvaluationJob  # avoid circular at module level

    with SessionLocal() as db:
        orphans = db.query(EvaluationJob).filter(EvaluationJob.status == "running").all()
        if orphans:
            logger.warning("Recovering %d orphaned jobs from previous crash", len(orphans))
            for job in orphans:
                job.status = "failed"
                job.failure_reason = "worker_crashed"
                job.finished_at = datetime.now(timezone.utc)
            db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    _recover_orphaned_jobs()
    if not hasattr(app.state, "llm_client"):
        app.state.llm_client = create_llm_client()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())

    app = FastAPI(
        title="Resume Upload & Rating API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        token = set_request_id(request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            reset_request_id(token)

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(  # type: ignore[no-untyped-def]
        request: Request, exc: RequestValidationError
    ):
        details = _validation_error_details(exc)
        logger.info(
            "validation_error request_id=%s path=%s errors=%s",
            getattr(request.state, "request_id", None),
            request.url.path,
            details,
        )
        return error(
            "validation_failed",
            "Request validation failed.",
            status_code=422,
            details={"errors": details},
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(  # type: ignore[no-untyped-def]
        request: Request, exc: HTTPException
    ):
        message = exc.detail if isinstance(exc.detail, str) else "HTTP error"
        details = {} if isinstance(exc.detail, str) else {"detail": str(exc.detail)}
        code = "not_found" if exc.status_code == 404 else "http_error"
        logger.info(
            "http_error request_id=%s path=%s status=%s detail=%s",
            getattr(request.state, "request_id", None),
            request.url.path,
            exc.status_code,
            exc.detail,
        )
        return error(code, message, status_code=exc.status_code, details=details)

    @app.exception_handler(LLMUnavailableError)
    async def llm_unavailable_handler(  # type: ignore[no-untyped-def]
        request: Request, exc: LLMUnavailableError
    ):
        logger.warning(
            "llm_unavailable request_id=%s path=%s error=%s",
            getattr(request.state, "request_id", None),
            request.url.path,
            exc,
        )
        return error(
            "llm_unavailable",
            "The evaluation service is temporarily unavailable.",
            status_code=503,
        )

    @app.exception_handler(LLMInvalidScoreError)
    async def llm_invalid_score_handler(  # type: ignore[no-untyped-def]
        request: Request, exc: LLMInvalidScoreError
    ):
        logger.warning(
            "llm_invalid_score request_id=%s path=%s error=%s",
            getattr(request.state, "request_id", None),
            request.url.path,
            exc,
        )
        return error(
            "llm_invalid_response",
            "The evaluation service returned an invalid response.",
            status_code=502,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(  # type: ignore[no-untyped-def]
        request: Request, exc: Exception
    ):
        request_id = getattr(request.state, "request_id", None)
        logger.exception(
            "unhandled_exception request_id=%s path=%s method=%s",
            request_id,
            request.url.path,
            request.method,
        )
        return error(
            "internal_error",
            "Unexpected server error. Use the request_id when checking server logs.",
            status_code=500,
            details={"request_id": request_id},
        )

    app.include_router(health_router, prefix="/api")
    app.include_router(resumes_router, prefix="/api")
    app.include_router(evaluations_router, prefix="/api")
    app.include_router(jobs_router, prefix="/api")
    app.include_router(job_listings_router, prefix="/api")

    # Serve static UI at root — mount last so API routes take priority
    app.mount("/", StaticFiles(directory="static", html=True), name="static")

    return app


app = create_app()
