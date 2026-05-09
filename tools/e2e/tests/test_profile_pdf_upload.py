"""Profile tab → upload a PDF → confirm new entry shows in the list."""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page, expect

from backend.tests.unit.test_parsing import make_minimal_pdf


def test_profile_pdf_upload_appears_in_list(
    live_app: str,
    page: Page,
    shots_dir: Path,
    tmp_path: Path,
) -> None:
    pdf = tmp_path / "e2e-resume.pdf"
    pdf.write_bytes(make_minimal_pdf("E2E Engineer skills: Python FastAPI Docker"))

    page.goto(f"{live_app}/", wait_until="networkidle")
    page.click('button.tab-btn[data-tab="profile"]')
    expect(page.locator("#tab-profile.active")).to_be_visible()
    page.screenshot(path=str(shots_dir / "01-profile-tab.png"), full_page=True)

    page.click("text=Add Profile")
    page.fill("#new-profile-name", "E2E Engineer")
    page.set_input_files("#new-profile-pdf", str(pdf))
    page.screenshot(path=str(shots_dir / "02-add-form.png"), full_page=True)

    page.click("text=Save Profile")

    expect(page.locator("#profiles-list")).to_contain_text("E2E Engineer", timeout=15_000)
    page.screenshot(path=str(shots_dir / "03-list-after.png"), full_page=True)
