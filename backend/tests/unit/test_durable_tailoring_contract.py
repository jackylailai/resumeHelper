from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
OPENAPI = ROOT / "specs" / "001-resume-upload-rating" / "contracts" / "openapi.yaml"
TAILORING_STATUSES = [
    "queued",
    "running",
    "retry_wait",
    "cancel_requested",
    "cancelled",
    "succeeded",
    "failed",
]


def _contract() -> dict:
    return yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))


def _properties(contract: dict, schema: str) -> dict:
    return contract["components"]["schemas"][schema]["properties"]


def _assert_tailoring_metadata(properties: dict) -> None:
    assert properties["tailoring_job_id"]["format"] == "uuid"
    assert properties["tailoring_job_id"]["nullable"] is True
    assert properties["tailoring_status"]["enum"] == TAILORING_STATUSES
    assert properties["tailoring_status"]["nullable"] is True


def test_openapi_exposes_tailoring_job_polling_endpoint() -> None:
    contract = _contract()

    operations = contract["paths"]["/api/jobs/{job_id}"]
    operation = operations["get"]

    assert operation["tags"] == ["jobs"]
    assert operation["parameters"][0]["name"] == "job_id"
    assert operation["parameters"][0]["schema"]["format"] == "uuid"
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert response_schema["$ref"] == "#/components/schemas/TailoringJobEnvelope"
    assert operations["post"]["summary"] == "Request cancellation for a durable AI job"
    response_schema = operations["post"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]
    assert response_schema["$ref"] == "#/components/schemas/TailoringJobEnvelope"


def test_openapi_tailoring_job_schema_has_terminal_state_and_progress_fields() -> None:
    properties = _properties(_contract(), "TailoringJob")

    assert properties["status"]["enum"] == TAILORING_STATUSES
    assert properties["kind"]["enum"] == [
        "tailor",
        "evaluate",
        "evaluate_bulk",
        "evaluate_listing",
        "evaluate_pending_listings",
    ]
    assert properties["input_payload"]["additionalProperties"] is True
    assert properties["result_payload"]["nullable"] is True
    assert properties["result_payload"]["additionalProperties"] is True
    for field in [
        "error_code",
        "error_message",
        "progress_current",
        "progress_total",
        "run_after",
        "attempts",
        "max_attempts",
    ]:
        assert field in properties


def test_evaluate_and_history_contracts_expose_tailoring_metadata() -> None:
    contract = _contract()

    for schema in [
        "EvaluateOut",
        "BulkEvaluateResult",
        "EvaluateByListingsResult",
        "HistoryItem",
    ]:
        _assert_tailoring_metadata(_properties(contract, schema))

    history_detail = contract["components"]["schemas"]["HistoryDetail"]
    assert history_detail["allOf"][0]["$ref"] == "#/components/schemas/HistoryItem"
