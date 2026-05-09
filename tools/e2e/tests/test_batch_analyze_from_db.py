"""JD Database tab → multi-select listings → run batch evaluate."""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page, expect


def test_batch_analyze_three_listings(
    live_app: str,
    seeded_profile: dict,
    seeded_listings: list[dict],
    page: Page,
    shots_dir: Path,
) -> None:
    page.goto(f"{live_app}/jobs.html", wait_until="networkidle")
    page.wait_for_selector("#job-list .job-list-item", timeout=10_000)

    items = page.locator("#job-list .job-list-item")
    expect(items).to_have_count(len(seeded_listings))
    page.screenshot(path=str(shots_dir / "01-listings.png"), full_page=True)

    # Tick the first three checkboxes
    checkboxes = page.locator("#job-list input[type=checkbox]")
    for i in range(3):
        checkboxes.nth(i).check()

    page.wait_for_function(
        "() => document.querySelector('#profile-select') "
        "&& document.querySelector('#profile-select').options.length > 0",
        timeout=5000,
    )
    page.select_option("#profile-select", index=0)
    page.screenshot(path=str(shots_dir / "02-selected.png"), full_page=True)

    page.click("#score-selected")

    expect(page.locator("#batch-results")).to_be_visible(timeout=60_000)
    expect(page.locator("#batch-status")).to_contain_text("Scored", timeout=60_000)

    results = page.locator("#batch-results .batch-result")
    expect(results).to_have_count(3)

    page.screenshot(path=str(shots_dir / "03-batch-result.png"), full_page=True)
