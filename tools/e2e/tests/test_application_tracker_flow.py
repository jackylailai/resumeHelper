"""JD Database -> Application Tracker flow with update controls."""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page, expect


def test_application_tracker_from_scored_listing(
    live_app: str,
    seeded_profile: dict,
    seeded_listings: list[dict],
    page: Page,
    shots_dir: Path,
) -> None:
    page.goto(f"{live_app}/jobs.html", wait_until="networkidle")
    page.wait_for_selector("#job-list .job-list-item", timeout=10_000)

    page.wait_for_function(
        "() => document.querySelector('#profile-select') "
        "&& document.querySelector('#profile-select').options.length > 0",
        timeout=5000,
    )
    page.select_option("#profile-select", index=0)

    first_checkbox = page.locator("#job-list input[type=checkbox]").first
    first_checkbox.check()
    page.click("#score-selected")
    expect(page.locator("#batch-status")).to_contain_text("Scored", timeout=60_000)

    first_row = page.locator("#job-list .job-row").first
    first_row.click()
    expect(page.locator("#detail")).to_be_visible(timeout=10_000)
    expect(page.locator("#track-application")).to_be_enabled(timeout=10_000)
    page.screenshot(path=str(shots_dir / "01-scored-listing-detail.png"), full_page=True)

    page.click("#track-application")
    expect(page.locator("#track-status")).to_contain_text("tracker", timeout=10_000)

    page.goto(f"{live_app}/applications.html", wait_until="networkidle")
    expect(page.locator("#applications-body tr")).to_have_count(1, timeout=10_000)
    expect(page.locator("#applications-body")).to_contain_text("Planned")
    page.screenshot(path=str(shots_dir / "02-applications-list.png"), full_page=True)

    page.locator("#applications-body select").first.select_option("applied")
    expect(page.locator("#tracker-status")).to_contain_text("Saved", timeout=10_000)
    page.locator('#applications-body input[type="date"]').first.fill("2026-06-01")
    expect(page.locator("#tracker-status")).to_contain_text("Saved", timeout=10_000)
    page.screenshot(path=str(shots_dir / "03-applications-updated.png"), full_page=True)
