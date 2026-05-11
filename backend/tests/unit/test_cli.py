from __future__ import annotations

import argparse
import asyncio
import uuid
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
