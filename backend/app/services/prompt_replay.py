from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from backend.app.services.eval_harness import (
    EvaluationHarnessCaseResult,
    EvaluationHarnessFixtureSet,
    EvaluationHarnessReport,
    run_evaluation_harness,
)
from backend.app.services.llm import LLMClient


@dataclass(frozen=True)
class PromptReplayCaseDelta:
    id: str
    old_score: int | None
    new_score: int | None
    score_delta: int | None
    old_status: str | None
    new_status: str | None
    status_changed: bool
    old_passed: bool
    new_passed: bool
    pass_changed: bool
    old_failures: list[str]
    new_failures: list[str]


@dataclass(frozen=True)
class PromptReplayReport:
    fixture_name: str
    fixture_path: str
    backend: str
    model: str | None
    old_prompt_version: str
    new_prompt_version: str
    total: int
    changed: int
    old_passed: int
    new_passed: int
    old_failed: int
    new_failed: int
    deltas: list[PromptReplayCaseDelta]
    old_report: EvaluationHarnessReport
    new_report: EvaluationHarnessReport

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compare_evaluation_prompt_versions(
    *,
    llm: LLMClient,
    fixture_set: EvaluationHarnessFixtureSet,
    fixture_path: Path,
    backend: str,
    model: str | None,
    old_prompt_version: str,
    new_prompt_version: str,
    case_ids: list[str] | None = None,
) -> PromptReplayReport:
    selected_fixture_set = _select_cases(fixture_set, case_ids)
    old_report = run_evaluation_harness(
        llm=llm,
        fixture_set=selected_fixture_set,
        fixture_path=fixture_path,
        backend=backend,
        prompt_version=old_prompt_version,
    )
    new_report = run_evaluation_harness(
        llm=llm,
        fixture_set=selected_fixture_set,
        fixture_path=fixture_path,
        backend=backend,
        prompt_version=new_prompt_version,
    )
    old_by_id = {result.id: result for result in old_report.results}
    new_by_id = {result.id: result for result in new_report.results}
    deltas = [
        _case_delta(old_by_id[result_id], new_by_id[result_id])
        for result_id in old_by_id
    ]
    changed = sum(
        1
        for delta in deltas
        if delta.score_delta not in {None, 0}
        or delta.status_changed
        or delta.pass_changed
    )
    return PromptReplayReport(
        fixture_name=selected_fixture_set.name,
        fixture_path=str(fixture_path),
        backend=backend,
        model=model,
        old_prompt_version=old_prompt_version,
        new_prompt_version=new_prompt_version,
        total=len(deltas),
        changed=changed,
        old_passed=old_report.passed,
        new_passed=new_report.passed,
        old_failed=old_report.failed,
        new_failed=new_report.failed,
        deltas=deltas,
        old_report=old_report,
        new_report=new_report,
    )


def write_prompt_replay_json(report: PromptReplayReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_prompt_replay_markdown(report: PromptReplayReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_prompt_replay_markdown(report), encoding="utf-8")


def format_prompt_replay_markdown(report: PromptReplayReport) -> str:
    model_line = report.model or ""
    lines = [
        f"# Prompt Replay Report: {report.fixture_name}",
        "",
        f"- backend: `{report.backend}`",
        f"- model: `{model_line}`",
        f"- old_prompt_version: `{report.old_prompt_version}`",
        f"- new_prompt_version: `{report.new_prompt_version}`",
        f"- fixtures: `{report.fixture_path}`",
        f"- old_result: {report.old_passed}/{report.total} passed",
        f"- new_result: {report.new_passed}/{report.total} passed",
        f"- changed_cases: {report.changed}/{report.total}",
        "",
        "| Case | Old Score | New Score | Delta | Old Status | New Status | Old | New |",
        "|------|-----------|-----------|-------|------------|------------|-----|-----|",
    ]
    for delta in report.deltas:
        score_delta = "" if delta.score_delta is None else f"{delta.score_delta:+d}"
        old_result = "PASS" if delta.old_passed else "FAIL"
        new_result = "PASS" if delta.new_passed else "FAIL"
        lines.append(
            "| "
            f"{delta.id} | {delta.old_score} | {delta.new_score} | "
            f"{score_delta} | {delta.old_status} | {delta.new_status} | "
            f"{old_result} | {new_result} |"
        )
    lines.append("")
    return "\n".join(lines)


def _select_cases(
    fixture_set: EvaluationHarnessFixtureSet,
    case_ids: list[str] | None,
) -> EvaluationHarnessFixtureSet:
    if not case_ids:
        return fixture_set
    wanted = set(case_ids)
    cases = [case for case in fixture_set.cases if case.id in wanted]
    found = {case.id for case in cases}
    missing = sorted(wanted - found)
    if missing:
        raise ValueError(f"unknown eval fixture case id(s): {', '.join(missing)}")
    return fixture_set.model_copy(update={"cases": cases})


def _case_delta(
    old: EvaluationHarnessCaseResult,
    new: EvaluationHarnessCaseResult,
) -> PromptReplayCaseDelta:
    score_delta = None
    if old.score is not None and new.score is not None:
        score_delta = new.score - old.score
    return PromptReplayCaseDelta(
        id=old.id,
        old_score=old.score,
        new_score=new.score,
        score_delta=score_delta,
        old_status=old.status,
        new_status=new.status,
        status_changed=old.status != new.status,
        old_passed=old.passed,
        new_passed=new.passed,
        pass_changed=old.passed != new.passed,
        old_failures=old.failures,
        new_failures=new.failures,
    )
