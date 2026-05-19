from __future__ import annotations

from pathlib import Path

from backend.app.config import Settings
from backend.app.services.eval_harness import load_evaluation_fixture_set
from backend.app.services.llm.fake import FakeLLMClient
from backend.app.services.llm.prompt_registry import (
    STEP_BEAUTIFY,
    STEP_EVALUATE,
    STEP_EXTRACT,
    STEP_TAILOR,
    prompt_registry,
    prompt_version_for_step,
)
from backend.app.services.prompt_replay import (
    compare_evaluation_prompt_versions,
    format_prompt_replay_markdown,
)


def test_prompt_registry_resolves_step_specific_versions(tmp_path: Path) -> None:
    settings = Settings(
        database_url="postgresql://test:test@localhost:5432/test",
        storage_dir=tmp_path / "storage",
        llm_prompt_version="legacy-evaluate-v1",
        llm_evaluate_prompt_version="",
        llm_tailor_prompt_version="tailor-v2",
        llm_extract_prompt_version="extract-v3",
        llm_beautify_prompt_version="beautify-v4",
    )

    assert prompt_version_for_step(STEP_EVALUATE, settings=settings) == "legacy-evaluate-v1"
    assert prompt_version_for_step(STEP_TAILOR, settings=settings) == "tailor-v2"
    assert prompt_version_for_step(STEP_EXTRACT, settings=settings) == "extract-v3"
    assert prompt_version_for_step(STEP_BEAUTIFY, settings=settings) == "beautify-v4"
    assert (
        prompt_version_for_step(
            STEP_EVALUATE,
            settings=settings,
            override=" evaluate-experiment ",
        )
        == "evaluate-experiment"
    )

    registry = prompt_registry(settings=settings)
    assert registry[STEP_EVALUATE].env_var == "LLM_EVALUATE_PROMPT_VERSION"
    assert registry[STEP_TAILOR].prompt_version == "tailor-v2"


def test_prompt_replay_compares_selected_evaluate_cases() -> None:
    fixture_set, fixture_path = load_evaluation_fixture_set()

    report = compare_evaluation_prompt_versions(
        llm=FakeLLMClient(),
        fixture_set=fixture_set,
        fixture_path=fixture_path,
        backend="fake",
        model=None,
        old_prompt_version="resume-fit-v1",
        new_prompt_version="resume-fit-v2",
        case_ids=["high_backend_fit"],
    )

    assert report.total == 1
    assert report.old_prompt_version == "resume-fit-v1"
    assert report.new_prompt_version == "resume-fit-v2"
    assert report.deltas[0].id == "high_backend_fit"
    assert report.deltas[0].old_passed is True
    assert report.deltas[0].new_passed is True

    markdown = format_prompt_replay_markdown(report)
    assert "Prompt Replay Report" in markdown
    assert "resume-fit-v2" in markdown
