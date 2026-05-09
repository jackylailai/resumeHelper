"""Playwright demo — drives the resumeHelper UI end-to-end and saves screenshots.

Run against a local app (uvicorn or docker compose):

    BASE_URL=http://localhost:8000 .venv/bin/python tools/e2e/demo_evaluate_flow.py

Steps:
    1. Open the homepage and screenshot it
    2. Open the JD Database tab (separate page) and screenshot it
    3. Back to Evaluate tab — pick an existing profile, paste a JD, click Evaluate
    4. Wait for the score badge to render and screenshot it

This is a manual demo, NOT a pytest. It exists so the user can see what an
end-to-end browser test would look like before we invest in a full suite.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
SHOTS = Path(__file__).parent / "screenshots"
SHOTS.mkdir(parents=True, exist_ok=True)

JD_TEXT = """\
Senior Backend Engineer — Java / Spring Boot

We are looking for a Senior Backend Engineer with strong experience in
high-concurrency systems. Required:
- 5+ years Java + Spring Boot in production
- Kafka, Redis, PostgreSQL
- AWS (EC2, EKS, Lambda)
- Observability: Prometheus, Grafana, structured logging
- CI/CD with Docker / Kubernetes / GitLab CI
Nice to have: experience scaling traffic to 50k+ QPS, payment / e-commerce
domain knowledge, Terraform.
"""


def ensure_profile_exists() -> None:
    """If the DB has no profiles, seed one via the legacy JSON endpoint
    (POST /api/profile). CI starts with an empty DB so the dropdown
    would otherwise be empty."""
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/profiles", timeout=5) as r:
            payload = json.loads(r.read())
        if payload.get("data"):
            print(f"  profile already present: id={payload['data'][0]['id']}")
            return
    except urllib.error.URLError as exc:
        print(f"  GET /api/profiles failed: {exc}")
        raise

    body = json.dumps({
        "skills_text": (
            "Senior Backend Engineer with 5+ years Java, Spring Boot, "
            "Kafka, Redis, PostgreSQL, AWS (EC2, EKS, Lambda), Docker, "
            "Kubernetes, Prometheus, Grafana. Built systems handling 50k QPS."
        )
    }).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/api/profile",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        payload = json.loads(r.read())
    print(f"  seeded profile id={payload['data']['id']}")


def shot(page: Page, name: str) -> Path:
    path = SHOTS / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    print(f"  screenshot → {path}")
    return path


def step(label: str) -> None:
    print(f"\n=== {label} ===")


def run() -> int:
    step("0. Ensure a baseline profile exists")
    ensure_profile_exists()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()

        step("1. Open homepage")
        page.goto(f"{BASE_URL}/", wait_until="networkidle")
        page.wait_for_selector("#tab-evaluate.active", timeout=5000)
        shot(page, "01-home-evaluate-tab")

        step("2. Open JD Database (separate page)")
        page.goto(f"{BASE_URL}/jobs.html", wait_until="networkidle")
        try:
            page.wait_for_selector("table, .empty", timeout=5000)
        except PWTimeout:
            pass
        shot(page, "02-jd-database")

        step("3. Back to Evaluate, pick a profile, paste JD")
        page.goto(f"{BASE_URL}/", wait_until="networkidle")
        page.wait_for_selector("#tab-evaluate.active", timeout=5000)

        # Wait for profile dropdown to populate from /api/profiles
        page.wait_for_function(
            "() => document.querySelector('#profile-select')"
            "  && document.querySelector('#profile-select').options.length > 0",
            timeout=5000,
        )
        select = page.query_selector("#profile-select")
        opts = select.query_selector_all("option") if select else []
        print(f"  profiles in dropdown: {len(opts)}")
        if opts:
            page.select_option("#profile-select", index=0)

        page.fill("#jd-input", JD_TEXT)
        shot(page, "03-evaluate-form-filled")

        step("4. Click Evaluate, wait for result")
        page.click("#eval-btn")
        # Score badge appears once the API responds
        try:
            page.wait_for_selector("#result-badge:not(:empty)", timeout=120_000)
            time.sleep(0.5)  # let result-detail render
            badge = page.text_content("#result-badge") or ""
            message = page.text_content("#result-message") or ""
            print(f"  score badge: {badge.strip()}")
            print(f"  message: {message.strip()[:120]}")
            shot(page, "04-evaluate-result")
        except PWTimeout:
            print("  TIMEOUT waiting for result — capturing whatever is on screen")
            shot(page, "04-evaluate-timeout")
            err = page.text_content("#eval-error") or ""
            print(f"  eval-error text: {err.strip()[:300]}")
            return 2

        browser.close()
        return 0


if __name__ == "__main__":
    sys.exit(run())
