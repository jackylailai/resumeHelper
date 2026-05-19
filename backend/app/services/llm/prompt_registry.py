"""Named prompt versions for each LLM workflow step."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Literal

from backend.app.config import Settings, get_settings
from backend.app.services.llm.prompt_safety import escape_closing_tags

STEP_EVALUATE = "evaluate"
STEP_TAILOR = "tailor"
STEP_EXTRACT = "extract"
STEP_BEAUTIFY = "beautify"

PromptStep = Literal["evaluate", "tailor", "extract", "beautify"]

DEFAULT_EVALUATE_PROMPT_VERSION = "resume-fit-v1"
DEFAULT_TAILOR_PROMPT_VERSION = "tailor-v1"
DEFAULT_EXTRACT_PROMPT_VERSION = "extract-v1"
DEFAULT_BEAUTIFY_PROMPT_VERSION = "beautify-v1"


@dataclass(frozen=True)
class PromptDefinition:
    step: PromptStep
    prompt_version: str
    env_var: str
    description: str
    source_path: str
    source_hash: str


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_PROMPT_TEMPLATE_PATHS: dict[PromptStep, Path] = {
    STEP_EVALUATE: _REPO_ROOT / "modes" / "score.md",
    STEP_TAILOR: _REPO_ROOT / "modes" / "generate.md",
    STEP_EXTRACT: _REPO_ROOT / "modes" / "extract.md",
    STEP_BEAUTIFY: _REPO_ROOT / "modes" / "beautify.md",
}


def _clean_prompt_version(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def prompt_version_for_step(
    step: PromptStep,
    *,
    settings: Settings | None = None,
    override: str | None = None,
) -> str:
    """Resolve the configured prompt version for a named LLM step."""

    override_value = _clean_prompt_version(override)
    if override_value:
        return override_value

    app_settings = settings or get_settings()
    if step == STEP_EVALUATE:
        return (
            _clean_prompt_version(app_settings.llm_evaluate_prompt_version)
            or _clean_prompt_version(app_settings.llm_prompt_version)
            or DEFAULT_EVALUATE_PROMPT_VERSION
        )
    if step == STEP_TAILOR:
        return (
            _clean_prompt_version(app_settings.llm_tailor_prompt_version)
            or DEFAULT_TAILOR_PROMPT_VERSION
        )
    if step == STEP_EXTRACT:
        return (
            _clean_prompt_version(app_settings.llm_extract_prompt_version)
            or DEFAULT_EXTRACT_PROMPT_VERSION
        )
    if step == STEP_BEAUTIFY:
        return (
            _clean_prompt_version(app_settings.llm_beautify_prompt_version)
            or DEFAULT_BEAUTIFY_PROMPT_VERSION
        )
    raise ValueError(f"Unsupported prompt step: {step}")


def prompt_registry(
    *, settings: Settings | None = None
) -> dict[PromptStep, PromptDefinition]:
    """Return the effective prompt registry for docs, CLIs, and audits."""

    app_settings = settings or get_settings()
    return {
        STEP_EVALUATE: PromptDefinition(
            step=STEP_EVALUATE,
            prompt_version=prompt_version_for_step(STEP_EVALUATE, settings=app_settings),
            env_var="LLM_EVALUATE_PROMPT_VERSION",
            description="Scores a job description against the selected profile.",
            source_path=str(prompt_template_path(STEP_EVALUATE).relative_to(_REPO_ROOT)),
            source_hash=prompt_hash_for_step(STEP_EVALUATE) or "",
        ),
        STEP_TAILOR: PromptDefinition(
            step=STEP_TAILOR,
            prompt_version=prompt_version_for_step(STEP_TAILOR, settings=app_settings),
            env_var="LLM_TAILOR_PROMPT_VERSION",
            description="Generates a tailored resume draft from an evaluation.",
            source_path=str(prompt_template_path(STEP_TAILOR).relative_to(_REPO_ROOT)),
            source_hash=prompt_hash_for_step(STEP_TAILOR) or "",
        ),
        STEP_EXTRACT: PromptDefinition(
            step=STEP_EXTRACT,
            prompt_version=prompt_version_for_step(STEP_EXTRACT, settings=app_settings),
            env_var="LLM_EXTRACT_PROMPT_VERSION",
            description="Extracts structured profile facts from an uploaded resume.",
            source_path=str(prompt_template_path(STEP_EXTRACT).relative_to(_REPO_ROOT)),
            source_hash=prompt_hash_for_step(STEP_EXTRACT) or "",
        ),
        STEP_BEAUTIFY: PromptDefinition(
            step=STEP_BEAUTIFY,
            prompt_version=prompt_version_for_step(STEP_BEAUTIFY, settings=app_settings),
            env_var="LLM_BEAUTIFY_PROMPT_VERSION",
            description="Transforms a tailored resume into the beautified HTML contract.",
            source_path=str(prompt_template_path(STEP_BEAUTIFY).relative_to(_REPO_ROOT)),
            source_hash=prompt_hash_for_step(STEP_BEAUTIFY) or "",
        ),
    }


def prompt_template_path(step: str) -> Path:
    """Return the canonical prompt template path for a workflow step."""

    path = _PROMPT_TEMPLATE_PATHS.get(step)  # type: ignore[arg-type]
    if path is None:
        raise ValueError(f"Unsupported prompt step: {step}")
    return path


def prompt_hash_for_step(step: str) -> str | None:
    """Hash the canonical prompt template, without user/JD content."""

    try:
        return sha256(prompt_template_path(step).read_bytes()).hexdigest()
    except (OSError, ValueError):
        return None


def render_prompt_for_step(step: str, **kwargs: object) -> str:
    """Render a canonical prompt template with escaped untrusted values."""

    text = prompt_template_path(step).read_text(encoding="utf-8")
    for key, value in kwargs.items():
        safe_value = escape_closing_tags(str(value))
        text = text.replace(f"{{{{{key}}}}}", safe_value)
    return text
