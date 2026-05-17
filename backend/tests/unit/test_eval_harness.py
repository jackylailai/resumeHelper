from __future__ import annotations

from pathlib import Path

from backend.app.models.job_analysis import STATUS_READY_TO_SUBMIT
from backend.app.services.eval_harness import (
    EvaluationHarnessCase,
    EvaluationHarnessFixtureSet,
    load_evaluation_fixture_set,
    run_evaluation_harness,
)
from backend.app.services.llm.fake import FakeLLMClient


def test_default_fake_evaluation_harness_passes() -> None:
    fixture_set, fixture_path = load_evaluation_fixture_set()

    report = run_evaluation_harness(
        llm=FakeLLMClient(),
        fixture_set=fixture_set,
        fixture_path=fixture_path,
        backend="fake",
        prompt_version="eval-harness-test",
    )

    assert report.total == 6
    assert report.failed == 0
    assert [result.status for result in report.results] == [
        "ready_to_submit",
        "needs_tailoring",
        "skip",
        # #139 adversarial cases — fake backend honours `[[score=72]]`
        # markers in the JD and routes to needs_tailoring regardless of
        # the prompt-injection text appended to each fixture.
        "needs_tailoring",
        "needs_tailoring",
        "needs_tailoring",
    ]


def test_evaluation_harness_reports_score_regressions() -> None:
    fixture_set = EvaluationHarnessFixtureSet(
        version=1,
        name="regression-test",
        cases=[
            EvaluationHarnessCase(
                id="expected_high_but_low",
                profile="Python backend engineer",
                job_description="Backend role. [[score=20]]",
                expected_status=STATUS_READY_TO_SUBMIT,
                expected_score_min=85,
                expected_score_max=100,
            )
        ],
    )

    report = run_evaluation_harness(
        llm=FakeLLMClient(),
        fixture_set=fixture_set,
        fixture_path=Path("inline.json"),
        backend="fake",
        prompt_version="eval-harness-test",
    )

    assert report.failed == 1
    assert "outside expected range" in report.results[0].failures[0]
    assert "status skip != expected ready_to_submit" in report.results[0].failures
