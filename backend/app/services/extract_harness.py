from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from backend.app.services.llm import LLMInvalidOutputError
from backend.app.services.llm.contracts import validate_structured_extraction_output

DEFAULT_EXTRACT_FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "evals" / "fixtures" / "extract_cases.json"
)


class ExtractInvalidCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    payload: dict[str, Any]

    @field_validator("id")
    @classmethod
    def _strip_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("id must not be blank")
        return value


class ExtractHarnessFixtureSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    name: str = Field(min_length=1)
    description: str = Field(default="")
    valid_output: dict[str, Any]
    invalid_outputs: list[ExtractInvalidCase] = Field(default_factory=list)


@dataclass(frozen=True)
class ExtractHarnessCaseResult:
    id: str
    kind: str  # "valid" | "invalid"
    passed: bool
    failures: list[str]


@dataclass(frozen=True)
class ExtractHarnessReport:
    version: int
    fixture_name: str
    fixture_path: str
    backend: str
    prompt_version: str
    total: int
    passed: int
    failed: int
    results: list[ExtractHarnessCaseResult]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_extract_fixture_set(
    path: Path | None = None,
) -> tuple[ExtractHarnessFixtureSet, Path]:
    fixture_path = path or DEFAULT_EXTRACT_FIXTURE_PATH
    try:
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid extract fixture JSON at {fixture_path}: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"could not read extract fixture at {fixture_path}: {exc}") from exc

    try:
        fixture_set = ExtractHarnessFixtureSet.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"invalid extract fixture schema at {fixture_path}: {exc}") from exc
    return fixture_set, fixture_path


def run_extract_harness(
    *,
    fixture_set: ExtractHarnessFixtureSet,
    fixture_path: Path,
    backend: str,
    prompt_version: str,
) -> ExtractHarnessReport:
    results: list[ExtractHarnessCaseResult] = [_run_valid_case(fixture_set.valid_output)]
    results.extend(_run_invalid_case(case) for case in fixture_set.invalid_outputs)
    passed = sum(1 for result in results if result.passed)
    return ExtractHarnessReport(
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


def write_extract_report_json(report: ExtractHarnessReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_extract_report_markdown(report: ExtractHarnessReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_extract_report_markdown(report), encoding="utf-8")


def format_extract_report_markdown(report: ExtractHarnessReport) -> str:
    lines = [
        f"# Extract Harness Report: {report.fixture_name}",
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


def _run_valid_case(payload: dict[str, Any]) -> ExtractHarnessCaseResult:
    try:
        validate_structured_extraction_output(payload, source="valid_output")
    except LLMInvalidOutputError as exc:
        return ExtractHarnessCaseResult(
            id="valid_output",
            kind="valid",
            passed=False,
            failures=[f"valid fixture rejected: {exc}"],
        )
    return ExtractHarnessCaseResult(
        id="valid_output",
        kind="valid",
        passed=True,
        failures=[],
    )


def _run_invalid_case(case: ExtractInvalidCase) -> ExtractHarnessCaseResult:
    try:
        validate_structured_extraction_output(case.payload, source=case.id)
    except LLMInvalidOutputError:
        return ExtractHarnessCaseResult(
            id=case.id,
            kind="invalid",
            passed=True,
            failures=[],
        )
    return ExtractHarnessCaseResult(
        id=case.id,
        kind="invalid",
        passed=False,
        failures=["invalid payload was accepted by contract"],
    )
