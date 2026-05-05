from __future__ import annotations
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from backend.app.api.envelope import error, success
from backend.app.db import get_db
from backend.app.schemas.profile import ProfileIn, ProfileOut
from backend.app.services.evaluator_v2 import get_baseline, upsert_baseline

router = APIRouter()


@router.post("/profile")
def set_profile(body: ProfileIn, db: Session = Depends(get_db)) -> JSONResponse:
    profile = upsert_baseline(db, body.skills_text)
    return success(ProfileOut.model_validate(profile).model_dump(mode="json"))


@router.get("/profile")
def get_profile(db: Session = Depends(get_db)) -> JSONResponse:
    profile = get_baseline(db)
    if profile is None:
        return error("not_found", "No baseline profile set yet", status_code=404)
    return success(ProfileOut.model_validate(profile).model_dump(mode="json"))
