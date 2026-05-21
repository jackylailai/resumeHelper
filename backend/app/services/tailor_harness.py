from __future__ import annotations

import inspect
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from backend.app.services.llm import LLMClient, LLMInvalidOutputError
from backend.app.services.llm.contracts import validate_tailor_output

DEFAULT_TAILOR_FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "evals" / "fixtures" / "tailor_cases.json"
)


class TailorHarnessCase(BaseModel):
    """One deterministic tailoring factuality regression case."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    baseline_text: str = Field(min_length=1)
    job_description: str = Field(min_length=1)
    score: int = Field(ge=0, le=100, default=72)
    gaps: list[str] = Field(default_factory=list)
    structured_data: dict[str, Any] | None = None
    proof_points: list[str] = Field(default_factory=list)
    required_facts: list[str] = Field(default_factory=list)
    forbidden_facts: list[str] = Field(default_factory=list)
    jd_only_terms: list[str] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("id", "baseline_text", "job_description")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator(
        "gaps",
        "proof_points",
        "required_facts",
        "forbidden_facts",
        "jd_only_terms",
    )
    @classmethod
    def _strip_list_items(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]


class TailorHarnessFixtureSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    name: str = Field(min_length=1)
    description: str = Field(default="")
    cases: list[TailorHarnessCase] = Field(min_length=1)


@dataclass(frozen=True)
class TailorHarnessCaseResult:
    id: str
    passed: bool
    failures: list[str]
    required_fact_misses: list[str] = field(default_factory=list)
    forbidden_fact_hits: list[str] = field(default_factory=list)
    jd_only_term_hits: list[str] = field(default_factory=list)
    suggestions_count: int = 0
    tailored_resume_chars: int = 0


@dataclass(frozen=True)
class TailorHarnessReport:
    version: int
    fixture_name: str
    fixture_path: str
    backend: str
    prompt_version: str
    total: int
    passed: int
    failed: int
    results: list[TailorHarnessCaseResult]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_tailor_fixture_set(
    path: Path | None = None,
) -> tuple[TailorHarnessFixtureSet, Path]:
    fixture_path = path or DEFAULT_TAILOR_FIXTURE_PATH
    try:
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid tailor fixture JSON at {fixture_path}: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"could not read tailor fixture at {fixture_path}: {exc}") from exc

    try:
        fixture_set = TailorHarnessFixtureSet.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"invalid tailor fixture schema at {fixture_path}: {exc}") from exc
    return fixture_set, fixture_path


def run_tailor_harness(
    *,
    llm: LLMClient,
    fixture_set: TailorHarnessFixtureSet,
    fixture_path: Path,
    backend: str,
    prompt_version: str,
) -> TailorHarnessReport:
    results = [
        _run_tailor_case(
            llm=llm,
            case=case,
        )
        for case in fixture_set.cases
    ]
    passed = sum(1 for result in results if result.passed)
    return TailorHarnessReport(
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


def write_tailor_report_json(report: TailorHarnessReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_tailor_report_markdown(report: TailorHarnessReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_tailor_report_markdown(report), encoding="utf-8")


def format_tailor_report_markdown(report: TailorHarnessReport) -> str:
    lines = [
        f"# Tailor Harness Report: {report.fixture_name}",
        "",
        f"- backend: `{report.backend}`",
        f"- prompt_version: `{report.prompt_version}`",
        f"- fixtures: `{report.fixture_path}`",
        f"- result: {report.passed}/{report.total} passed",
        "",
        (
            "| Case | Result | Required Misses | Forbidden Hits | JD-only Hits | "
            "Suggestions | Chars | Failures |"
        ),
        "|------|--------|-----------------|----------------|--------------|-------------|-------|----------|",
    ]
    for result in report.results:
        outcome = "PASS" if result.passed else "FAIL"
        failures = "<br>".join(result.failures) if result.failures else ""
        required_misses = "<br>".join(result.required_fact_misses)
        forbidden_hits = "<br>".join(result.forbidden_fact_hits)
        jd_only_hits = "<br>".join(result.jd_only_term_hits)
        lines.append(
            "| "
            f"{result.id} | {outcome} | {required_misses} | {forbidden_hits} | "
            f"{jd_only_hits} | "
            f"{result.suggestions_count} | {result.tailored_resume_chars} | "
            f"{failures} |"
        )
    lines.append("")
    return "\n".join(lines)


def _run_tailor_case(
    *,
    llm: LLMClient,
    case: TailorHarnessCase,
) -> TailorHarnessCaseResult:
    try:
        tailor = getattr(llm, "tailor", None)
        if tailor is None:
            raise LLMInvalidOutputError("active LLM client does not implement tailor")
        kwargs: dict[str, Any] = {
            "baseline_text": case.baseline_text,
            "jd_text": case.job_description,
            "gaps": case.gaps,
            "score": case.score,
            "structured_data": case.structured_data,
        }
        if "proof_points" in inspect.signature(tailor).parameters:
            kwargs["proof_points"] = "\n".join(case.proof_points) or "(none)"
        raw_result = tailor(**kwargs)
        result = validate_tailor_output(raw_result, source=llm.__class__.__name__)
    except Exception as exc:
        return TailorHarnessCaseResult(
            id=case.id,
            passed=False,
            failures=[f"{type(exc).__name__}: {exc}"],
        )

    suggestions = result["tailoring_suggestions"]
    tailored_resume = result["tailored_resume"]
    folded_resume = tailored_resume.casefold()

    required_misses = [
        fact for fact in case.required_facts if fact.casefold() not in folded_resume
    ]
    forbidden_hits = [
        fact for fact in case.forbidden_facts if fact.casefold() in folded_resume
    ]
    evidence_text = "\n".join([case.baseline_text, *case.proof_points]).casefold()
    jd_only_hits = [
        term
        for term in case.jd_only_terms
        if term.casefold() in folded_resume and term.casefold() not in evidence_text
    ]
    failures = [f"missing required fact: {fact}" for fact in required_misses]
    failures.extend(f"forbidden fact present: {fact}" for fact in forbidden_hits)
    failures.extend(
        f"JD-only term injected without proof: {term}" for term in jd_only_hits
    )

    return TailorHarnessCaseResult(
        id=case.id,
        passed=not failures,
        failures=failures,
        required_fact_misses=required_misses,
        forbidden_fact_hits=forbidden_hits,
        jd_only_term_hits=jd_only_hits,
        suggestions_count=len(suggestions),
        tailored_resume_chars=len(tailored_resume),
    )
