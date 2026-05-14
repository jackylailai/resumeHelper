from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from html.parser import HTMLParser
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    ValidationError,
    field_validator,
    model_validator,
)

from backend.app.services.llm import EvaluationResult, LLMInvalidOutputError

_MAX_EXPLANATION_CHARS = 2000
_MAX_LIST_ITEMS = 20
_MAX_LIST_ITEM_CHARS = 500
_MAX_TAILORED_RESUME_CHARS = 30000
_MAX_STRUCTURED_TEXT_CHARS = 4000
_MAX_HTML_CHARS = 200000
_TAILOR_ALLOWED_METADATA = {"token_count_input", "token_count_output"}
_BEAUTIFY_ALLOWED_METADATA = {"token_count_input", "token_count_output"}
_PREAMBLE_PREFIXES = (
    "here is",
    "here's",
    "sure,",
    "of course",
    "below is",
)
_KNOWN_HALLUCINATED_FACTS = (
    "References available upon request",
    "Portfolio available upon request",
    "automatic application submitted",
)
_UNSAFE_HTML_TAGS = {
    "script",
    "link",
    "iframe",
    "object",
    "embed",
    "img",
    "video",
    "audio",
    "source",
}
_UNSAFE_CSS_PATTERN = re.compile(r"(@import|@font-face|url\s*\()", re.IGNORECASE)

_BoundedText = Annotated[
    StrictStr,
    Field(min_length=1, max_length=_MAX_LIST_ITEM_CHARS),
]
_StructuredText = Annotated[
    StrictStr,
    Field(min_length=1, max_length=_MAX_STRUCTURED_TEXT_CHARS),
]


def _strip_text(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("string fields must not be blank")
    return value


def _strip_text_list(value: list[str]) -> list[str]:
    stripped = [item.strip() for item in value]
    if any(not item for item in stripped):
        raise ValueError("items must not be blank")
    return stripped


class EvaluationOutputContract(BaseModel):
    """Schema for the resume-vs-JD scoring LLM call."""

    model_config = ConfigDict(extra="forbid")

    score: StrictInt = Field(ge=0, le=100)
    explanation: StrictStr = Field(min_length=1, max_length=_MAX_EXPLANATION_CHARS)
    strengths: list[_BoundedText] = Field(max_length=_MAX_LIST_ITEMS)
    gaps: list[_BoundedText] = Field(max_length=_MAX_LIST_ITEMS)

    @field_validator("explanation")
    @classmethod
    def _strip_explanation(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("explanation must not be blank")
        return value

    @field_validator("strengths", "gaps")
    @classmethod
    def _strip_list_items(cls, value: list[str]) -> list[str]:
        stripped = [item.strip() for item in value]
        if any(not item for item in stripped):
            raise ValueError("items must not be blank")
        return stripped


class TailorOutputContract(BaseModel):
    """Schema for the resume tailoring LLM call."""

    model_config = ConfigDict(extra="forbid")

    tailoring_suggestions: list[_BoundedText] = Field(max_length=_MAX_LIST_ITEMS)
    tailored_resume: StrictStr = Field(
        min_length=1,
        max_length=_MAX_TAILORED_RESUME_CHARS,
    )

    @field_validator("tailoring_suggestions")
    @classmethod
    def _strip_suggestions(cls, value: list[str]) -> list[str]:
        stripped = [item.strip() for item in value]
        if any(not item for item in stripped):
            raise ValueError("tailoring_suggestions items must not be blank")
        return stripped

    @field_validator("tailored_resume")
    @classmethod
    def _validate_tailored_resume(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("tailored_resume must not be blank")
        if "```" in text:
            raise ValueError("tailored_resume must not contain code fences")
        lowered = text.casefold()
        if any(lowered.startswith(prefix) for prefix in _PREAMBLE_PREFIXES):
            raise ValueError("tailored_resume must not include a preamble")
        return text


class _StrictProfileModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def _strip_strings(cls, value: Any) -> Any:
        if isinstance(value, str):
            return _strip_text(value)
        return value


class StructuredLinkContract(_StrictProfileModel):
    label: _StructuredText | None = None
    url: _StructuredText | None = None

    @model_validator(mode="after")
    def _require_content(self) -> StructuredLinkContract:
        if not self.label and not self.url:
            raise ValueError("link entries must include label or url")
        return self


class StructuredPersonalContract(_StrictProfileModel):
    name: _StructuredText | None = None
    email: _StructuredText | None = None
    phone: _StructuredText | None = None
    location: _StructuredText | None = None
    links: list[StructuredLinkContract] | None = None

    @model_validator(mode="after")
    def _require_content(self) -> StructuredPersonalContract:
        if not any([self.name, self.email, self.phone, self.location, self.links]):
            raise ValueError("personal must not be empty")
        return self


class StructuredWorkExperienceContract(_StrictProfileModel):
    employer: _StructuredText | None = None
    title: _StructuredText | None = None
    location: _StructuredText | None = None
    start_date: _StructuredText | None = None
    end_date: _StructuredText | None = None
    is_current: StrictBool | None = None
    achievements: list[_StructuredText] | None = None

    @field_validator("achievements")
    @classmethod
    def _strip_achievements(cls, value: list[str] | None) -> list[str] | None:
        return _strip_text_list(value) if value is not None else None

    @model_validator(mode="after")
    def _require_content(self) -> StructuredWorkExperienceContract:
        if not any(
            [
                self.employer,
                self.title,
                self.location,
                self.start_date,
                self.end_date,
                self.is_current is not None,
                self.achievements,
            ]
        ):
            raise ValueError("work_experience entries must not be empty")
        return self


class StructuredEducationContract(_StrictProfileModel):
    school: _StructuredText | None = None
    degree: _StructuredText | None = None
    field: _StructuredText | None = None
    start_date: _StructuredText | None = None
    end_date: _StructuredText | None = None

    @model_validator(mode="after")
    def _require_content(self) -> StructuredEducationContract:
        if not any([self.school, self.degree, self.field, self.start_date, self.end_date]):
            raise ValueError("education entries must not be empty")
        return self


class StructuredLanguageContract(_StrictProfileModel):
    name: _StructuredText | None = None
    level: _StructuredText | None = None
    test: _StructuredText | None = None
    score: _StructuredText | None = None

    @model_validator(mode="after")
    def _require_content(self) -> StructuredLanguageContract:
        if not any([self.name, self.level, self.test, self.score]):
            raise ValueError("language entries must not be empty")
        return self


class StructuredCertificationContract(_StrictProfileModel):
    name: _StructuredText | None = None
    issuer: _StructuredText | None = None
    date: _StructuredText | None = None

    @model_validator(mode="after")
    def _require_content(self) -> StructuredCertificationContract:
        if not any([self.name, self.issuer, self.date]):
            raise ValueError("certification entries must not be empty")
        return self


class StructuredSkillsContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    languages: list[_StructuredText] = Field(default_factory=list)
    frameworks: list[_StructuredText] = Field(default_factory=list)
    databases: list[_StructuredText] = Field(default_factory=list)
    cloud: list[_StructuredText] = Field(default_factory=list)
    tools: list[_StructuredText] = Field(default_factory=list)
    other: list[_StructuredText] = Field(default_factory=list)

    @field_validator("languages", "frameworks", "databases", "cloud", "tools", "other")
    @classmethod
    def _strip_skill_items(cls, value: list[str]) -> list[str]:
        return _strip_text_list(value)

    @model_validator(mode="after")
    def _require_content(self) -> StructuredSkillsContract:
        if not any(
            [
                self.languages,
                self.frameworks,
                self.databases,
                self.cloud,
                self.tools,
                self.other,
            ]
        ):
            raise ValueError("skills must contain at least one category value")
        return self


class StructuredExtractionOutputContract(_StrictProfileModel):
    """Schema for structured profile extraction output."""

    personal: StructuredPersonalContract | None = None
    summary: _StructuredText | None = None
    work_experience: list[StructuredWorkExperienceContract] | None = None
    education: list[StructuredEducationContract] | None = None
    languages: list[StructuredLanguageContract] | None = None
    certifications: list[StructuredCertificationContract] | None = None
    skills: StructuredSkillsContract | None = None
    personal_qualities: list[_StructuredText] | None = None

    @field_validator("personal_qualities")
    @classmethod
    def _strip_personal_qualities(
        cls,
        value: list[str] | None,
    ) -> list[str] | None:
        return _strip_text_list(value) if value is not None else None

    @model_validator(mode="after")
    def _require_content(self) -> StructuredExtractionOutputContract:
        if not any(
            [
                self.personal,
                self.summary,
                self.work_experience,
                self.education,
                self.languages,
                self.certifications,
                self.skills,
                self.personal_qualities,
            ]
        ):
            raise ValueError("structured extraction output must not be empty")
        return self


class BeautifyOutputContract(BaseModel):
    """Schema for a validated beautify result consumed by the API."""

    model_config = ConfigDict(extra="forbid")

    html_content: StrictStr = Field(min_length=1, max_length=_MAX_HTML_CHARS)
    prompt_version: StrictStr = Field(min_length=1, max_length=100)
    token_count_input: StrictInt | None = Field(default=None, ge=0)
    token_count_output: StrictInt | None = Field(default=None, ge=0)

    @field_validator("html_content", "prompt_version")
    @classmethod
    def _strip_text_fields(cls, value: str) -> str:
        return _strip_text(value)


class _HTMLContractParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: set[str] = set()
        self.unsafe_reasons: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        tag_name = tag.casefold()
        self.tags.add(tag_name)
        if tag_name in _UNSAFE_HTML_TAGS:
            self.unsafe_reasons.append(f"disallowed <{tag_name}> tag")
        for attr_name, attr_value in attrs:
            name = attr_name.casefold()
            value = attr_value or ""
            if name in {"src", "srcset"}:
                self.unsafe_reasons.append(
                    f"disallowed external resource attribute {name}"
                )
            if name == "style" and _UNSAFE_CSS_PATTERN.search(value):
                self.unsafe_reasons.append("disallowed CSS external resource")


def strip_json_code_fence(raw: str) -> str:
    """Allow legacy adapters to accept a single fenced JSON object."""
    text = raw.strip()
    if not text.startswith("```"):
        return text

    lines = text.splitlines()
    if not lines:
        return text
    if not lines[-1].strip().startswith("```"):
        return text
    return "\n".join(lines[1:-1]).strip()


def parse_evaluation_output(
    raw: str,
    *,
    source: str,
    token_count_input: int | None = None,
    token_count_output: int | None = None,
) -> EvaluationResult:
    """Parse and validate raw LLM scoring output into the shared result type."""
    text = strip_json_code_fence(raw)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMInvalidOutputError(f"{source} returned invalid JSON: {exc}") from exc

    try:
        contract = EvaluationOutputContract.model_validate(payload)
    except ValidationError as exc:
        raise LLMInvalidOutputError(
            f"{source} returned invalid evaluation output: {exc}"
        ) from exc

    return EvaluationResult(
        score=contract.score,
        explanation=contract.explanation,
        strengths=contract.strengths,
        gaps=contract.gaps,
        token_count_input=token_count_input,
        token_count_output=token_count_output,
    )


def parse_tailor_output(
    raw: str,
    *,
    source: str,
    token_count_input: int | None = None,
    token_count_output: int | None = None,
) -> dict[str, Any]:
    """Parse and validate raw LLM tailoring output."""
    text = strip_json_code_fence(raw)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMInvalidOutputError(
            f"{source} returned invalid tailor JSON: {exc}"
        ) from exc
    return validate_tailor_output(
        payload,
        source=source,
        token_count_input=token_count_input,
        token_count_output=token_count_output,
    )


def validate_tailor_output(
    payload: Mapping[str, Any],
    *,
    source: str,
    token_count_input: int | None = None,
    token_count_output: int | None = None,
) -> dict[str, Any]:
    """Validate a parsed tailoring payload and preserve provider metadata."""
    if not isinstance(payload, Mapping):
        raise LLMInvalidOutputError(
            f"{source} returned invalid tailoring output: expected object"
        )

    unexpected = (
        set(payload) - set(TailorOutputContract.model_fields) - _TAILOR_ALLOWED_METADATA
    )
    if unexpected:
        raise LLMInvalidOutputError(
            f"{source} returned unexpected tailor fields: {sorted(unexpected)}"
        )

    try:
        contract = TailorOutputContract.model_validate(
            {
                "tailoring_suggestions": payload.get("tailoring_suggestions"),
                "tailored_resume": payload.get("tailored_resume", ""),
            }
        )
    except ValidationError as exc:
        raise LLMInvalidOutputError(
            f"{source} returned invalid tailoring output: {exc}"
        ) from exc

    output: dict[str, Any] = {
        "tailoring_suggestions": contract.tailoring_suggestions,
        "tailored_resume": contract.tailored_resume,
    }
    resolved_input_tokens = (
        token_count_input
        if token_count_input is not None
        else payload.get("token_count_input")
    )
    resolved_output_tokens = (
        token_count_output
        if token_count_output is not None
        else payload.get("token_count_output")
    )
    if resolved_input_tokens is not None:
        output["token_count_input"] = resolved_input_tokens
    if resolved_output_tokens is not None:
        output["token_count_output"] = resolved_output_tokens
    return output


def parse_structured_extraction_output(raw: str, *, source: str) -> dict[str, Any]:
    """Parse and validate raw structured profile extraction output."""
    text = strip_json_code_fence(raw)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMInvalidOutputError(
            f"{source} returned invalid structured extraction JSON: {exc}"
        ) from exc
    return validate_structured_extraction_output(payload, source=source)


def validate_structured_extraction_output(
    payload: Mapping[str, Any],
    *,
    source: str,
) -> dict[str, Any]:
    """Validate structured profile extraction output.

    Unknown-key policy is fail-closed: any unrecognized top-level or nested key
    rejects the output instead of silently persisting ambiguous profile state.
    """
    if not isinstance(payload, Mapping):
        raise LLMInvalidOutputError(
            f"{source} returned invalid structured extraction output: expected object"
        )

    try:
        contract = StructuredExtractionOutputContract.model_validate(payload)
    except ValidationError as exc:
        raise LLMInvalidOutputError(
            f"{source} returned invalid structured extraction output: {exc}"
        ) from exc
    return contract.model_dump(exclude_none=True, exclude_defaults=True)


def validate_beautify_output(
    html: str,
    *,
    source: str,
    source_markdown: str,
    prompt_version: str = "beautify-v1",
    token_count_input: int | None = None,
    token_count_output: int | None = None,
    forbidden_facts: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Validate a raw beautify HTML document and return the API result shape."""
    return validate_beautify_result(
        {
            "html_content": html,
            "prompt_version": prompt_version,
            "token_count_input": token_count_input,
            "token_count_output": token_count_output,
        },
        source=source,
        source_markdown=source_markdown,
        forbidden_facts=forbidden_facts,
    )


def validate_beautify_result(
    payload: Mapping[str, Any],
    *,
    source: str,
    source_markdown: str,
    forbidden_facts: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Validate a parsed beautify result before persisting HTML/PDF state."""
    if not isinstance(payload, Mapping):
        raise LLMInvalidOutputError(
            f"{source} returned invalid beautify output: expected object"
        )

    unexpected = (
        set(payload) - set(BeautifyOutputContract.model_fields) - _BEAUTIFY_ALLOWED_METADATA
    )
    if unexpected:
        raise LLMInvalidOutputError(
            f"{source} returned unexpected beautify fields: {sorted(unexpected)}"
        )

    try:
        contract = BeautifyOutputContract.model_validate(
            {
                "html_content": payload.get("html_content", ""),
                "prompt_version": payload.get("prompt_version", "beautify-v1"),
                "token_count_input": payload.get("token_count_input"),
                "token_count_output": payload.get("token_count_output"),
            }
        )
    except ValidationError as exc:
        raise LLMInvalidOutputError(
            f"{source} returned invalid beautify output: {exc}"
        ) from exc

    _validate_beautify_html(
        contract.html_content,
        source=source,
        source_markdown=source_markdown,
        forbidden_facts=forbidden_facts,
    )
    return contract.model_dump(exclude_none=True)


def _validate_beautify_html(
    html: str,
    *,
    source: str,
    source_markdown: str,
    forbidden_facts: Sequence[str] | None,
) -> None:
    text = html.strip()
    lowered = text.casefold()
    required_fragments = (
        "<!doctype html",
        "<html",
        "</html>",
        "<head",
        "</head>",
        "<style",
        "</style>",
        "<body",
        "</body>",
    )
    missing = [fragment for fragment in required_fragments if fragment not in lowered]
    if missing:
        raise LLMInvalidOutputError(
            f"{source} returned incomplete beautify HTML: missing {missing}"
        )
    if "```" in text:
        raise LLMInvalidOutputError(
            f"{source} returned beautify HTML with markdown code fences"
        )
    if any(lowered.startswith(prefix) for prefix in _PREAMBLE_PREFIXES):
        raise LLMInvalidOutputError(
            f"{source} returned beautify HTML with an assistant preamble"
        )
    if _UNSAFE_CSS_PATTERN.search(text):
        raise LLMInvalidOutputError(
            f"{source} returned beautify HTML with external CSS/font references"
        )

    parser = _HTMLContractParser()
    parser.feed(text)
    if parser.unsafe_reasons:
        raise LLMInvalidOutputError(
            f"{source} returned unsafe beautify HTML: {parser.unsafe_reasons}"
        )

    source_text = source_markdown.casefold()
    forbidden = list(_KNOWN_HALLUCINATED_FACTS)
    if forbidden_facts:
        forbidden.extend(forbidden_facts)
    hallucinated = [
        fact
        for fact in forbidden
        if fact.casefold() in lowered and fact.casefold() not in source_text
    ]
    if hallucinated:
        raise LLMInvalidOutputError(
            f"{source} returned hallucinated beautify facts: {hallucinated}"
        )
