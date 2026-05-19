from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from backend.app.services.llm import LLMInvalidOutputError
from backend.app.services.llm.contracts import validate_beautify_output

DEFAULT_BEAUTIFY_FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "evals" / "fixtures" / "beautify_cases.json"
)


class BeautifyInvalidCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    html: str = Field(min_length=1)

    @field_validator("id")
    @classmethod
    def _strip_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("id must not be blank")
        return value


class BeautifyHarnessFixtureSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    name: str = Field(min_length=1)
    description: str = Field(default="")
    source_markdown: str = Field(min_length=1)
    valid_html: str = Field(min_length=1)
    forbidden_facts: list[str] = Field(default_factory=list)
    invalid_html: list[BeautifyInvalidCase] = Field(default_factory=list)

    @field_validator("forbidden_facts")
    @classmethod
    def _strip_forbidden(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]


@dataclass(frozen=True)
class BeautifyHarnessCaseResult:
    id: str
    kind: str  # "valid" | "invalid"
    passed: bool
    failures: list[str]


@dataclass(frozen=True)
class BeautifyHarnessReport:
    version: int
    fixture_name: str
    fixture_path: str
    backend: str
    prompt_version: str
    total: int
    passed: int
    failed: int
    results: list[BeautifyHarnessCaseResult]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_beautify_fixture_set(
    path: Path | None = None,
) -> tuple[BeautifyHarnessFixtureSet, Path]:
    fixture_path = path or DEFAULT_BEAUTIFY_FIXTURE_PATH
    try:
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid beautify fixture JSON at {fixture_path}: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"could not read beautify fixture at {fixture_path}: {exc}") from exc

    try:
        fixture_set = BeautifyHarnessFixtureSet.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"invalid beautify fixture schema at {fixture_path}: {exc}") from exc
    return fixture_set, fixture_path


def run_beautify_harness(
    *,
    fixture_set: BeautifyHarnessFixtureSet,
    fixture_path: Path,
    backend: str,
    prompt_version: str,
) -> BeautifyHarnessReport:
    results: list[BeautifyHarnessCaseResult] = [_run_valid_case(fixture_set)]
    results.extend(_run_invalid_case(case, fixture_set) for case in fixture_set.invalid_html)
    passed = sum(1 for result in results if result.passed)
    return BeautifyHarnessReport(
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


def write_beautify_report_json(report: BeautifyHarnessReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_beautify_report_markdown(report: BeautifyHarnessReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_beautify_report_markdown(report), encoding="utf-8")


def format_beautify_report_markdown(report: BeautifyHarnessReport) -> str:
    lines = [
        f"# Beautify Harness Report: {report.fixture_name}",
        "",
        f"- backend: `{report.backend}`",
        f"- prompt_version: `{report.prompt_version}`",
        f"- fixtures: `{report.fixture_path}`",
        f"- result: {report.passed}/{report.total} passed",
        "",
        "| Case | Kind | Result | Failures |",
        "|------|------|--------|----------|",
    ]
    for result in report.results:
        outcome = "PASS" if result.passed else "FAIL"
        failures = "<br>".join(result.failures) if result.failures else ""
        lines.append(f"| {result.id} | {result.kind} | {outcome} | {failures} |")
    lines.append("")
    return "\n".join(lines)


def _run_valid_case(fixture_set: BeautifyHarnessFixtureSet) -> BeautifyHarnessCaseResult:
    try:
        validate_beautify_output(
            fixture_set.valid_html,
            source="valid_html",
            source_markdown=fixture_set.source_markdown,
            forbidden_facts=fixture_set.forbidden_facts,
        )
    except LLMInvalidOutputError as exc:
        return BeautifyHarnessCaseResult(
            id="valid_html",
            kind="valid",
            passed=False,
            failures=[f"valid fixture rejected: {exc}"],
        )
    return BeautifyHarnessCaseResult(
        id="valid_html",
        kind="valid",
        passed=True,
        failures=[],
    )


def _run_invalid_case(
    case: BeautifyInvalidCase,
    fixture_set: BeautifyHarnessFixtureSet,
) -> BeautifyHarnessCaseResult:
    try:
        validate_beautify_output(
            case.html,
            source=case.id,
            source_markdown=fixture_set.source_markdown,
            forbidden_facts=fixture_set.forbidden_facts,
        )
    except LLMInvalidOutputError:
        return BeautifyHarnessCaseResult(
            id=case.id,
            kind="invalid",
            passed=True,
            failures=[],
        )
    return BeautifyHarnessCaseResult(
        id=case.id,
        kind="invalid",
        passed=False,
        failures=["invalid html was accepted by contract"],
    )
