from __future__ import annotations

from pathlib import Path

from backend.app.services.llm.fake import FakeLLMClient
from backend.app.services.tailor_harness import (
    TailorHarnessCase,
    TailorHarnessFixtureSet,
    load_tailor_fixture_set,
    run_tailor_harness,
)


class _InjectingTailorLLM:
    def tailor(
        self,
        baseline_text: str,
        jd_text: str,
        gaps: list[str],
        score: int,
        structured_data: dict | None = None,
    ) -> dict:
        return {
            "tailoring_suggestions": ["Injected JD-only term"],
            "tailored_resume": f"# Resume\n\n{baseline_text}\n\nKubernetes",
        }


def test_default_fake_tailor_harness_passes() -> None:
    fixture_set, fixture_path = load_tailor_fixture_set()

    report = run_tailor_harness(
        llm=FakeLLMClient(),
        fixture_set=fixture_set,
        fixture_path=fixture_path,
        backend="fake",
        prompt_version="tailor-harness-test",
    )

    assert report.total == 2
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


def test_tailor_harness_rejects_jd_only_terms_without_proof() -> None:
    fixture_set = TailorHarnessFixtureSet(
        version=1,
        name="tailor-jd-only-test",
        cases=[
            TailorHarnessCase(
                id="jd_only_skill_injection",
                baseline_text="Jane Lin worked at Fubon Media.",
                job_description="Backend role requiring Kubernetes.",
                jd_only_terms=["Kubernetes"],
            )
        ],
    )

    report = run_tailor_harness(
        llm=_InjectingTailorLLM(),
        fixture_set=fixture_set,
        fixture_path=Path("inline.json"),
        backend="fake",
        prompt_version="tailor-harness-test",
    )

    assert report.failed == 1
    result = report.results[0]
    assert result.jd_only_term_hits == ["Kubernetes"]
    assert "JD-only term injected without proof: Kubernetes" in result.failures


def test_tailor_harness_allows_jd_term_with_proof_point() -> None:
    fixture_set = TailorHarnessFixtureSet(
        version=1,
        name="tailor-proof-point-test",
        cases=[
            TailorHarnessCase(
                id="proof_point_allows_term",
                baseline_text="Jane Lin worked at Fubon Media.",
                job_description="Backend role requiring Kubernetes.",
                proof_points=["Maintained Kubernetes deployment manifests."],
                jd_only_terms=["Kubernetes"],
            )
        ],
    )

    report = run_tailor_harness(
        llm=_InjectingTailorLLM(),
        fixture_set=fixture_set,
        fixture_path=Path("inline.json"),
        backend="fake",
        prompt_version="tailor-harness-test",
    )

    assert report.failed == 0
    assert report.results[0].jd_only_term_hits == []
