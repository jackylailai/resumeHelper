from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.services.llm import LLMInvalidOutputError
from backend.app.services.llm.contracts import (
    parse_evaluation_output,
    parse_structured_extraction_output,
    parse_tailor_output,
    validate_beautify_output,
    validate_structured_extraction_output,
)

_FIXTURES_DIR = Path(__file__).resolve().parents[2] / "evals" / "fixtures"


def test_parse_evaluation_output_accepts_valid_json() -> None:
    result = parse_evaluation_output(
        """
        {
          "score": 88,
          "explanation": "Strong backend match.",
          "strengths": ["Python APIs", "PostgreSQL"],
          "gaps": ["No explicit Kubernetes evidence"]
        }
        """,
        source="test",
        token_count_input=12,
        token_count_output=34,
    )

    assert result.score == 88
    assert result.explanation == "Strong backend match."
    assert result.strengths == ["Python APIs", "PostgreSQL"]
    assert result.gaps == ["No explicit Kubernetes evidence"]
    assert result.token_count_input == 12
    assert result.token_count_output == 34


def test_parse_evaluation_output_accepts_single_json_code_fence() -> None:
    result = parse_evaluation_output(
        """```json
        {"score": 61, "explanation": "Partial match.", "strengths": [], "gaps": []}
        ```""",
        source="test",
    )

    assert result.score == 61


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        '{"score": "88", "explanation": "String score.", "strengths": [], "gaps": []}',
        '{"score": 101, "explanation": "Too high.", "strengths": [], "gaps": []}',
        '{"score": 50, "explanation": "Missing lists."}',
        '{"score": 50, "explanation": "", "strengths": [], "gaps": []}',
        '{"score": 50, "explanation": 123, "strengths": [], "gaps": []}',
        '{"score": 50, "explanation": "ok", "strengths": "Python", "gaps": []}',
        (
            '{"score": 50, "explanation": "ok", "strengths": [], '
            '"gaps": [], "unexpected": true}'
        ),
    ],
)
def test_parse_evaluation_output_rejects_invalid_contract(raw: str) -> None:
    with pytest.raises(LLMInvalidOutputError):
        parse_evaluation_output(raw, source="test")


def test_parse_tailor_output_accepts_valid_json() -> None:
    result = parse_tailor_output(
        """
        {
          "tailoring_suggestions": [" Emphasize API ownership "],
          "tailored_resume": " # Jane Lin\\n\\nFubon Media, April 2024 - Present "
        }
        """,
        source="test",
        token_count_input=10,
        token_count_output=20,
    )

    assert result["tailoring_suggestions"] == ["Emphasize API ownership"]
    assert result["tailored_resume"] == "# Jane Lin\n\nFubon Media, April 2024 - Present"
    assert result["token_count_input"] == 10
    assert result["token_count_output"] == 20


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        '{"tailoring_suggestions": [], "tailored_resume": ""}',
        '{"tailoring_suggestions": ["ok"], "tailored_resume": "```markdown\\n# A\\n```"}',
        '{"tailoring_suggestions": ["ok"], "tailored_resume": "Here is # A"}',
        (
            '{"tailoring_suggestions": ["ok"], "tailored_resume": "# A", '
            '"unexpected": true}'
        ),
        '{"tailored_resume": "# A"}',
        '{"tailoring_suggestions": ["ok"]}',
        '["not", "an", "object"]',
    ],
)
def test_parse_tailor_output_rejects_invalid_contract(raw: str) -> None:
    with pytest.raises(LLMInvalidOutputError):
        parse_tailor_output(raw, source="test")


def test_structured_extraction_contract_accepts_fixture() -> None:
    fixture = json.loads((_FIXTURES_DIR / "extract_cases.json").read_text())

    result = validate_structured_extraction_output(
        fixture["valid_output"],
        source="test",
    )

    assert result["personal"]["name"] == "Jane Lin"
    assert result["work_experience"][0]["employer"] == "Fubon Media"
    assert result["skills"]["frameworks"] == ["FastAPI"]


def test_parse_structured_extraction_output_accepts_json_fence() -> None:
    result = parse_structured_extraction_output(
        """```json
        {"personal": {"name": " Jane Lin "}, "skills": {"languages": ["Python"]}}
        ```""",
        source="test",
    )

    assert result["personal"]["name"] == "Jane Lin"


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[]",
        "{}",
        '{"personal": {"name": ""}}',
        '{"unknown": true}',
        '{"skills": {"languages": ["Python"], "unknown": ["x"]}}',
        '{"work_experience": [{"employer": "Fubon Media", "unknown": "x"}]}',
    ],
)
def test_structured_extraction_contract_rejects_invalid_output(raw: str) -> None:
    with pytest.raises(LLMInvalidOutputError):
        parse_structured_extraction_output(raw, source="test")


def test_structured_extraction_fixture_invalid_outputs_fail() -> None:
    fixture = json.loads((_FIXTURES_DIR / "extract_cases.json").read_text())

    for case in fixture["invalid_outputs"]:
        with pytest.raises(LLMInvalidOutputError):
            validate_structured_extraction_output(case["payload"], source=case["id"])


def test_beautify_contract_accepts_fixture() -> None:
    fixture = json.loads((_FIXTURES_DIR / "beautify_cases.json").read_text())

    result = validate_beautify_output(
        fixture["valid_html"],
        source="test",
        source_markdown=fixture["source_markdown"],
        forbidden_facts=fixture["forbidden_facts"],
    )

    assert result["html_content"].startswith("<!DOCTYPE html>")
    assert result["prompt_version"] == "beautify-v1"


@pytest.mark.parametrize(
    "html",
    [
        "<html><body>missing doctype</body></html>",
        (
            "<!DOCTYPE html><html><head><style>body{}</style></head>"
            "<body><script>alert(1)</script></body></html>"
        ),
        (
            "<!DOCTYPE html><html><head><link rel=\"stylesheet\" href=\"x.css\">"
            "<style>body{}</style></head><body></body></html>"
        ),
        (
            "<!DOCTYPE html><html><head><style>@import url(x.css);</style></head>"
            "<body></body></html>"
        ),
        (
            "<!DOCTYPE html><html><head><style>body{}</style></head>"
            "<body><img src=\"https://example.com/a.png\"></body></html>"
        ),
    ],
)
def test_beautify_contract_rejects_unsafe_html(html: str) -> None:
    with pytest.raises(LLMInvalidOutputError):
        validate_beautify_output(
            html,
            source="test",
            source_markdown="# Jane Lin",
        )


def test_beautify_fixture_invalid_outputs_fail() -> None:
    fixture = json.loads((_FIXTURES_DIR / "beautify_cases.json").read_text())

    for case in fixture["invalid_html"]:
        with pytest.raises(LLMInvalidOutputError):
            validate_beautify_output(
                case["html"],
                source=case["id"],
                source_markdown=fixture["source_markdown"],
                forbidden_facts=fixture["forbidden_facts"],
            )
