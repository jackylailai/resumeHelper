from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

from backend.app import cli


class _SessionContext:
    def __enter__(self):
        return object()

    def __exit__(self, *_exc):
        return None


def test_scrape_evaluate_all_with_linkedin_uses_all_source_scope(monkeypatch):
    captured = {}

    def fake_create_scrape_runs(_db, *, source: str, keyword: str, limit: int):
        assert source == "all_with_linkedin"
        assert keyword == "backend"
        assert limit == 1
        return [SimpleNamespace(id=uuid.uuid4())]

    async def fake_execute_scrape_runs(_db, _run_ids):
        return [
            SimpleNamespace(
                source="104",
                status="succeeded",
                inserted=0,
                updated=0,
                skipped=0,
                failed=0,
                error_summary=None,
            )
        ]

    def fake_evaluate_listings(args):
        captured["source"] = args.source
        return 0

    monkeypatch.setattr(cli, "SessionLocal", lambda: _SessionContext())
    monkeypatch.setattr(cli, "create_scrape_runs", fake_create_scrape_runs)
    monkeypatch.setattr(cli, "execute_scrape_runs", fake_execute_scrape_runs)
    monkeypatch.setattr(cli, "_evaluate_listings", fake_evaluate_listings)

    result = asyncio.run(
        cli._scrape(
            argparse.Namespace(
                source="all_with_linkedin",
                keyword=" backend ",
                limit=1,
                evaluate=True,
                profile_id=None,
                evaluate_limit=100,
                no_tailor=True,
                quiet=True,
            )
        )
    )

    assert result == 0
    assert captured["source"] is None


def test_eval_harness_cli_writes_json_and_markdown_reports(tmp_path: Path) -> None:
    report_json = tmp_path / "report.json"
    report_md = tmp_path / "report.md"

    result = cli.main(
        [
            "eval-harness",
            "--backend",
            "fake",
            "--report-json",
            str(report_json),
            "--report-md",
            str(report_md),
            "--quiet",
        ]
    )

    assert result == 0
    payload = json.loads(report_json.read_text(encoding="utf-8"))
    assert payload["backend"] == "fake"
    assert payload["failed"] == 0
    assert payload["results"]
    assert "Eval Harness Report" in report_md.read_text(encoding="utf-8")


def test_prompt_replay_cli_writes_json_and_markdown_reports(tmp_path: Path) -> None:
    report_json = tmp_path / "prompt-replay.json"
    report_md = tmp_path / "prompt-replay.md"

    result = cli.main(
        [
            "prompt-replay",
            "--backend",
            "fake",
            "--old-prompt-version",
            "resume-fit-v1",
            "--new-prompt-version",
            "resume-fit-v2",
            "--case-id",
            "high_backend_fit",
            "--report-json",
            str(report_json),
            "--report-md",
            str(report_md),
            "--quiet",
        ]
    )

    assert result == 0
    payload = json.loads(report_json.read_text(encoding="utf-8"))
    assert payload["old_prompt_version"] == "resume-fit-v1"
    assert payload["new_prompt_version"] == "resume-fit-v2"
    assert payload["total"] == 1
    assert "Prompt Replay Report" in report_md.read_text(encoding="utf-8")


def test_prompt_registry_cli_prints_source_hashes(capsys) -> None:  # type: ignore[no-untyped-def]
    result = cli.main(["prompt-registry", "--json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    evaluate = next(row for row in payload if row["step"] == "evaluate")
    assert evaluate["prompt_version"] == "resume-fit-v1"
    assert evaluate["source_path"].replace("\\", "/") == "modes/score.md"
    assert len(evaluate["source_hash"]) == 64
