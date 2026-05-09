"""History tab renders evaluated jobs grouped by status."""
from __future__ import annotations

from pathlib import Path

import httpx
from playwright.sync_api import Page, expect


def test_history_lists_an_evaluated_job(
    live_app: str,
    seeded_profile: dict,
    page: Page,
    shots_dir: Path,
) -> None:
    r = httpx.post(
        f"{live_app}/api/evaluate",
        json={
            "jd_text": "Backend engineer. Python, Postgres. [[score=72]]",
            "profile_id": seeded_profile["id"],
        },
        timeout=30,
    )
    r.raise_for_status()

    page.goto(f"{live_app}/", wait_until="networkidle")
    page.click('button.tab-btn[data-tab="history"]')
    expect(page.locator("#tab-history.active")).to_be_visible()

    expect(page.locator("#history-content")).to_contain_text("72", timeout=10_000)
    page.screenshot(path=str(shots_dir / "01-history.png"), full_page=True)
