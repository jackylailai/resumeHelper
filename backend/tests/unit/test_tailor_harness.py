from __future__ import annotations

from pathlib import Path

from backend.app.services.llm.fake import FakeLLMClient
from backend.app.services.tailor_harness import (
    TailorHarnessCase,
    TailorHarnessFixtureSet,
    load_tailor_fixture_set,
    run_tailor_harness,
)


def test_default_fake_tailor_harness_passes() -> None:
    fixture_set, fixture_path = load_tailor_fixture_set()

    report = run_tailor_harness(
        llm=FakeLLMClient(),
        fixture_set=fixture_set,
        fixture_path=fixture_path,
        backend="fake",
        prompt_version="tailor-harness-test",
    )

    assert report.total == 1
    assert report.failed == 0
    assert report.results[0].suggestions_count == 2


def test_tailor_harness_reports_fact_regressions() -> None:
    fixture_set = TailorHarnessFixtureSet(
        version=1,
        name="tailor-regression-test",
        cases=[
            TailorHarnessCase(
                id="required_and_forbidden_facts",
                baseline_text="Jane Lin worked at Fubon Media.",
                job_description="Backend role.",
                required_facts=["Missing Certification"],
                forbidden_facts=["Fubon Media"],
            )
        ],
    )

    report = run_tailor_harness(
        llm=FakeLLMClient(),
        fixture_set=fixture_set,
        fixture_path=Path("inline.json"),
        backend="fake",
        prompt_version="tailor-harness-test",
    )

    assert report.failed == 1
    result = report.results[0]
    assert result.required_fact_misses == ["Missing Certification"]
    assert result.forbidden_fact_hits == ["Fubon Media"]
    assert "missing required fact: Missing Certification" in result.failures
    assert "forbidden fact present: Fubon Media" in result.failures
