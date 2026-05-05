from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.api.evaluations import router as evaluations_router
from backend.app.api.health import router as health_router
from backend.app.api.jobs import router as jobs_router
from backend.app.api.resumes import router as resumes_router
from backend.app.config import get_settings
from backend.app.db import SessionLocal
from backend.app.services.llm.anthropic import AnthropicLLMClient

logger = logging.getLogger(__name__)


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
    app.state.llm_client = AnthropicLLMClient()
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
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    app.include_router(health_router, prefix="/api")
    app.include_router(resumes_router, prefix="/api")
    app.include_router(evaluations_router, prefix="/api")
    app.include_router(jobs_router, prefix="/api")

    # Serve static UI at root — mount last so API routes take priority
    app.mount("/", StaticFiles(directory="static", html=True), name="static")

    return app


app = create_app()
