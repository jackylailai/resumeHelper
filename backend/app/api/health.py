from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.app.api.envelope import success

router = APIRouter()


@router.get("/health")
def health_check() -> JSONResponse:
    return success({"status": "ok"})
