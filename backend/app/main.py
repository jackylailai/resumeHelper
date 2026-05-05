from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.api.evaluate import router as evaluate_router
from backend.app.api.health import router as health_router
from backend.app.api.profile import router as profile_router
from backend.app.config import get_settings
from backend.app.services.llm.claude_cli import ClaudeCLIClient

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    app.state.llm_client = ClaudeCLIClient()
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
    app.include_router(profile_router, prefix="/api")
    app.include_router(evaluate_router, prefix="/api")

    # Serve static UI at root — mount last so API routes take priority
    app.mount("/", StaticFiles(directory="static", html=True), name="static")

    return app


app = create_app()
