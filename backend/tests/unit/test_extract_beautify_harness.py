from __future__ import annotations

from backend.app.services.beautify_harness import (
    load_beautify_fixture_set,
    run_beautify_harness,
)
from backend.app.services.extract_harness import (
    load_extract_fixture_set,
    run_extract_harness,
)


def test_default_extract_harness_fixture_passes() -> None:
    fixture_set, fixture_path = load_extract_fixture_set()

    report = run_extract_harness(
        fixture_set=fixture_set,
        fixture_path=fixture_path,
        backend="fake",
        prompt_version="extract-harness-test",
    )

    assert report.failed == 0
    assert report.total == 4


def test_default_beautify_harness_fixture_passes() -> None:
    fixture_set, fixture_path = load_beautify_fixture_set()

    report = run_beautify_harness(
        fixture_set=fixture_set,
        fixture_path=fixture_path,
        backend="fake",
        prompt_version="beautify-harness-test",
    )

    assert report.failed == 0
    assert report.total == 10
