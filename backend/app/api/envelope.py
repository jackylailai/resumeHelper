from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse


def success(data: Any, status_code: int = 200, **meta: Any) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"data": data, "error": None, "meta": meta},
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
            "meta": meta,
        },
    )
