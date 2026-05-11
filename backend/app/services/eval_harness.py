from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from backend.app.models.job_analysis import (
    STATUS_NEEDS_TAILORING,
    STATUS_READY_TO_SUBMIT,
    STATUS_SKIP,
    THRESHOLD_HIGH,
    THRESHOLD_MID,
)
from backend.app.services.llm import LLMClient

DEFAULT_EVALUATE_FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "evals" / "fixtures" / "evaluate_cases.json"
)

_VALID_STATUSES = {
    STATUS_READY_TO_SUBMIT,
    STATUS_NEEDS_TAILORING,
    STATUS_SKIP,
}


class EvaluationHarnessCase(BaseModel):
    """One deterministic LLM evaluation regression case."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    profile: str = Field(min_length=1)
    job_description: str = Field(min_length=1)
    expected_status: str = Field(min_length=1)
    expected_score_min: int = Field(ge=0, le=100)
    expected_score_max: int = Field(ge=0, le=100)
    required_terms: list[str] = Field(default_factory=list)
    forbidden_terms: list[str] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("id", "profile", "job_description", "expected_status")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("required_terms", "forbidden_terms")
    @classmethod
    def _strip_terms(cls, value: list[str]) -> list[str]:
        return [term.strip() for term in value if term.strip()]

    @field_validator("expected_status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        if value not in _VALID_STATUSES:
            raise ValueError(f"expected_status must be one of {sorted(_VALID_STATUSES)}")
        return value

    @model_validator(mode="after")
    def _validate_score_range(self) -> EvaluationHarnessCase:
        if self.expected_score_min > self.expected_score_max:
            raise ValueError("expected_score_min must be <= expected_score_max")
        return self


class EvaluationHarnessFixtureSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    name: str = Field(min_length=1)
    description: str = Field(default="")
    cases: list[EvaluationHarnessCase] = Field(min_length=1)


@dataclass(frozen=True)
class EvaluationHarnessCaseResult:
    id: str
    passed: bool
    failures: list[str]
    expected_status: str
    expected_score_min: int
    expected_score_max: int
    score: int | None = None
    status: str | None = None
    explanation: str = ""
    strengths: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvaluationHarnessReport:
    version: int
    fixture_name: str
    fixture_path: str
    backend: str
    prompt_version: str
    total: int
    passed: int
    failed: int
    results: list[EvaluationHarnessCaseResult]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_evaluation_fixture_set(
    path: Path | None = None,
) -> tuple[EvaluationHarnessFixtureSet, Path]:
    fixture_path = path or DEFAULT_EVALUATE_FIXTURE_PATH
    try:
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid eval fixture JSON at {fixture_path}: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"could not read eval fixture at {fixture_path}: {exc}") from exc

    try:
        fixture_set = EvaluationHarnessFixtureSet.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"invalid eval fixture schema at {fixture_path}: {exc}") from exc
    return fixture_set, fixture_path


def status_for_score(score: int) -> str:
    if score >= THRESHOLD_HIGH:
        return STATUS_READY_TO_SUBMIT
    if score >= THRESHOLD_MID:
        return STATUS_NEEDS_TAILORING
    return STATUS_SKIP


def run_evaluation_harness(
    *,
    llm: LLMClient,
    fixture_set: EvaluationHarnessFixtureSet,
    fixture_path: Path,
    backend: str,
    prompt_version: str,
) -> EvaluationHarnessReport:
    results = [
        _run_evaluation_case(
            llm=llm,
            case=case,
            prompt_version=prompt_version,
        )
        for case in fixture_set.cases
    ]
    passed = sum(1 for result in results if result.passed)
    return EvaluationHarnessReport(
        version=fixture_set.version,
        fixture_name=fixture_set.name,
        fixture_path=str(fixture_path),
        backend=backend,
        prompt_version=prompt_version,
        total=len(results),
        passed=passed,
        failed=len(results) - passed,
        results=results,
    )


def write_report_json(report: EvaluationHarnessReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_report_markdown(report: EvaluationHarnessReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_report_markdown(report), encoding="utf-8")


def format_report_markdown(report: EvaluationHarnessReport) -> str:
    lines = [
        f"# Eval Harness Report: {report.fixture_name}",
        "",
        f"- backend: `{report.backend}`",
        f"- prompt_version: `{report.prompt_version}`",
        f"- fixtures: `{report.fixture_path}`",
        f"- result: {report.passed}/{report.total} passed",
        "",
        "| Case | Result | Score | Status | Failures |",
        "|------|--------|-------|--------|----------|",
    ]
    for result in report.results:
        outcome = "PASS" if result.passed else "FAIL"
        failures = "<br>".join(result.failures) if result.failures else ""
        lines.append(
            "| "
            f"{result.id} | {outcome} | {result.score} | "
            f"{result.status} | {failures} |"
        )
    lines.append("")
    return "\n".join(lines)


def _run_evaluation_case(
    *,
    llm: LLMClient,
    case: EvaluationHarnessCase,
    prompt_version: str,
) -> EvaluationHarnessCaseResult:
    try:
        result = llm.evaluate(case.profile, case.job_description, prompt_version)
    except Exception as exc:
        return EvaluationHarnessCaseResult(
            id=case.id,
            passed=False,
            failures=[f"{type(exc).__name__}: {exc}"],
            expected_status=case.expected_status,
            expected_score_min=case.expected_score_min,
            expected_score_max=case.expected_score_max,
        )

    failures = _validate_result_contract(result)
    score_value = getattr(result, "score", None)
    score = score_value if isinstance(score_value, int) else None
    status = status_for_score(score) if score is not None else None

    if score is not None and not (
        case.expected_score_min <= score <= case.expected_score_max
    ):
        failures.append(
            "score "
            f"{score} outside expected range "
            f"{case.expected_score_min}-{case.expected_score_max}"
        )
    if status != case.expected_status:
        failures.append(f"status {status} != expected {case.expected_status}")

    explanation = result.explanation if isinstance(result.explanation, str) else ""
    strengths = result.strengths if isinstance(result.strengths, list) else []
    gaps = result.gaps if isinstance(result.gaps, list) else []
    combined_output = "\n".join([explanation, *strengths, *gaps]).casefold()
    for term in case.required_terms:
        if term.casefold() not in combined_output:
            failures.append(f"missing required term: {term}")
    for term in case.forbidden_terms:
        if term.casefold() in combined_output:
            failures.append(f"forbidden term present: {term}")

    return EvaluationHarnessCaseResult(
        id=case.id,
        passed=not failures,
        failures=failures,
        expected_status=case.expected_status,
        expected_score_min=case.expected_score_min,
        expected_score_max=case.expected_score_max,
        score=score,
        status=status,
        explanation=explanation,
        strengths=strengths,
        gaps=gaps,
    )


def _validate_result_contract(result: Any) -> list[str]:
    failures: list[str] = []
    score = getattr(result, "score", None)
    explanation = getattr(result, "explanation", None)
    strengths = getattr(result, "strengths", None)
    gaps = getattr(result, "gaps", None)
    if not isinstance(score, int) or not 0 <= score <= 100:
        failures.append("score must be an integer from 0 to 100")
    if not isinstance(explanation, str) or not explanation.strip():
        failures.append("explanation must be a non-empty string")
    if not _is_string_list(strengths):
        failures.append("strengths must be a list of non-empty strings")
    if not _is_string_list(gaps):
        failures.append("gaps must be a list of non-empty strings")
    return failures


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and bool(item.strip()) for item in value
    )
