from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from json import dumps

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.api.applications import router as applications_router
from backend.app.api.beautify import router as beautify_router
from backend.app.api.debug import router as debug_router
from backend.app.api.envelope import error, reset_request_id, set_request_id
from backend.app.api.evaluate import router as evaluate_router
from backend.app.api.health import router as health_router
from backend.app.api.job_listings import router as job_listings_router
from backend.app.api.opportunities import router as opportunities_router
from backend.app.api.profile import router as profile_router
from backend.app.api.proof_points import router as proof_points_router
from backend.app.api.scrape import router as scrape_router
from backend.app.config import get_settings
from backend.app.rate_limit import (
    FixedWindowRateLimiter,
    client_identifier,
    rate_limit_rule_for,
)
from backend.app.security import is_management_authorized, write_auth_required
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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
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
    app.state.rate_limiter = FixedWindowRateLimiter()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        # Explicit: never send cookies / auth headers cross-origin. Turning
        # this on requires a concrete origin list (never "*") — see
        # config.py validate_production_config.
        allow_credentials=False,
    )

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        token = set_request_id(request_id)
        started = time.perf_counter()
        status_code = 500
        try:
            if settings.rate_limit_enabled:
                rule = rate_limit_rule_for(request, settings)
                if rule is not None:
                    decision = app.state.rate_limiter.check(
                        route_key=rule.key,
                        client_id=client_identifier(request),
                        limit=rule.limit,
                        window_seconds=rule.window_seconds,
                    )
                    if not decision.allowed:
                        response = error(
                            "rate_limited",
                            "Too many requests. Please retry after the rate limit window resets.",
                            status_code=429,
                            details={
                                "limit": decision.limit,
                                "window_seconds": decision.window_seconds,
                                "retry_after_seconds": decision.retry_after_seconds,
                            },
                            retry_after_seconds=decision.retry_after_seconds,
                        )
                        status_code = response.status_code
                        response.headers["Retry-After"] = str(decision.retry_after_seconds)
                        response.headers["X-Request-ID"] = request_id
                        return response

            auth_required = write_auth_required(request, settings)
            if auth_required and not is_management_authorized(request, settings):
                response = error(
                    "unauthorized",
                    "Authentication is required for write operations.",
                    status_code=401,
                )
                status_code = response.status_code
                response.headers["X-Request-ID"] = request_id
                response.headers["WWW-Authenticate"] = 'Basic realm="resume-helper"'
                return response
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.info(
                dumps(
                    {
                        "event": "request",
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "status": status_code,
                        "latency_ms": latency_ms,
                    },
                    separators=(",", ":"),
                )
            )
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
    app.include_router(profile_router, prefix="/api")
    app.include_router(evaluate_router, prefix="/api")
    app.include_router(job_listings_router, prefix="/api")
    app.include_router(opportunities_router, prefix="/api")
    app.include_router(applications_router, prefix="/api")
    app.include_router(proof_points_router, prefix="/api")
    app.include_router(beautify_router, prefix="/api")
    app.include_router(scrape_router, prefix="/api")
    if settings.environment != "production":
        app.include_router(debug_router, prefix="/api")

    app.mount("/", StaticFiles(directory="static", html=True), name="static")

    return app


app = create_app()
