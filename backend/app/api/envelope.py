from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any

from fastapi.responses import JSONResponse

_REQUEST_ID: ContextVar[str | None] = ContextVar("request_id", default=None)


def set_request_id(request_id: str) -> Token[str | None]:
    return _REQUEST_ID.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    _REQUEST_ID.reset(token)


def current_request_id() -> str | None:
    return _REQUEST_ID.get()


def _meta_with_request_id(meta: dict[str, Any]) -> dict[str, Any]:
    request_id = current_request_id()
    if request_id and "request_id" not in meta:
        meta["request_id"] = request_id
    return meta


def success(data: Any, status_code: int = 200, **meta: Any) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"data": data, "error": None, "meta": _meta_with_request_id(meta)},
    )


def error(
    code: str,
    message: str,
    status_code: int = 400,
    details: dict[str, Any] | None = None,
    **meta: Any,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "data": None,
            "error": {"code": code, "message": message, "details": details or {}},
            "meta": _meta_with_request_id(meta),
        },
    )
