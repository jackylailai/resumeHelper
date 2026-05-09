"""Paste-JD evaluate flow → score badge + status messaging."""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page, expect


def test_evaluate_pasted_jd_renders_score_and_message(
    live_app: str,
    seeded_profile: dict,
    page: Page,
    shots_dir: Path,
) -> None:
    page.goto(live_app, wait_until="networkidle")
    expect(page.locator("#tab-evaluate.active")).to_be_visible()
    page.screenshot(path=str(shots_dir / "01-home.png"), full_page=True)

    page.wait_for_function(
        "() => document.querySelector('#profile-select') "
        "&& document.querySelector('#profile-select').options.length > 0",
        timeout=5000,
    )
    page.select_option("#profile-select", index=0)

    jd = (
        "Senior Backend Engineer — Python/FastAPI, AWS, Postgres, Kafka. "
        "[[score=72]]"
    )
    page.fill("#jd-input", jd)
    page.screenshot(path=str(shots_dir / "02-form-filled.png"), full_page=True)

    page.click("#eval-btn")
    badge = page.locator("#result-badge")
    expect(badge).to_have_text("72/100", timeout=30_000)
    expect(page.locator("#result-message")).to_contain_text("Tailoring")

    page.screenshot(path=str(shots_dir / "03-result.png"), full_page=True)
