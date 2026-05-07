from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.envelope import error
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

    # Without this handler, uncaught exceptions in routes (LLM context-window
    # blowups, network errors, etc.) become plain-text "Internal Server Error"
    # responses, which break the front-end JSON parser. See #51.
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.exception(
            "unhandled %s on %s %s [request_id=%s]",
            type(exc).__name__, request.method, request.url, request_id,
        )
        return error(
            "internal_error",
            f"{type(exc).__name__}: {exc}",
            status_code=500,
            request_id=request_id,
        )

    app.include_router(health_router, prefix="/api")
    app.include_router(profile_router, prefix="/api")
    app.include_router(evaluate_router, prefix="/api")

    # Serve static UI at root — mount last so API routes take priority
    app.mount("/", StaticFiles(directory="static", html=True), name="static")

    return app


app = create_app()
