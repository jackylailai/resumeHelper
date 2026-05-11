from __future__ import annotations

import pytest

from backend.app.services.llm import LLMInvalidOutputError
from backend.app.services.llm.contracts import parse_evaluation_output


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
