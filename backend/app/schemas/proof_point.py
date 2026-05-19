from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

ShortText = Annotated[str, Field(min_length=1, max_length=255)]
LongText = Annotated[str, Field(min_length=1, max_length=4000)]
TermList = Annotated[
    list[Annotated[str, Field(min_length=1, max_length=80)]],
    Field(max_length=50),
]


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _clean_terms(values: list[str] | None) -> list[str]:
    if not values:
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        term = value.strip()
        key = term.casefold()
        if term and key not in seen:
            cleaned.append(term)
            seen.add(key)
    return cleaned


class ProofPointCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: int | None = None
    title: ShortText
    context: LongText | None = None
    metrics: LongText | None = None
    skills: TermList = Field(default_factory=list)
    tags: TermList = Field(default_factory=list)
    situation: LongText | None = None
    task: LongText | None = None
    action: LongText | None = None
    result: LongText | None = None

    @field_validator("title", mode="before")
    @classmethod
    def strip_required_title(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return stripped
        raise ValueError("title is required")

    @field_validator(
        "context",
        "metrics",
        "situation",
        "task",
        "action",
        "result",
        mode="before",
    )
    @classmethod
    def strip_text(cls, value: object) -> object:
        return _clean_optional_text(value) if isinstance(value, str) else value

    @field_validator("skills", "tags", mode="before")
    @classmethod
    def normalize_terms(cls, value: object) -> object:
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return _clean_terms(value)
        return value


class ProofPointUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: int | None = None
    title: ShortText | None = None
    context: LongText | None = None
    metrics: LongText | None = None
    skills: TermList | None = None
    tags: TermList | None = None
    situation: LongText | None = None
    task: LongText | None = None
    action: LongText | None = None
    result: LongText | None = None

    @field_validator("title", mode="before")
    @classmethod
    def strip_required_title(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return stripped
        raise ValueError("title cannot be blank or null")

    @field_validator(
        "context",
        "metrics",
        "situation",
        "task",
        "action",
        "result",
        mode="before",
    )
    @classmethod
    def strip_text(cls, value: object) -> object:
        return _clean_optional_text(value) if isinstance(value, str) else value

    @field_validator("skills", "tags", mode="before")
    @classmethod
    def normalize_terms(cls, value: object) -> object:
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return _clean_terms(value)
        return value


class ProofPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    profile_id: int | None
    title: str
    context: str | None
    metrics: str | None
    skills: list[str]
    tags: list[str]
    situation: str | None
    task: str | None
    action: str | None
    result: str | None
    created_at: datetime
    updated_at: datetime
