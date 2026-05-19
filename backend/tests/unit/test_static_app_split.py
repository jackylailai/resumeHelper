from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STATIC = ROOT / "static"

HOME_SCRIPTS = [
    "/shared.js",
    "/app.js",
    "/features/system-status.js",
    "/features/profile.js",
    "/features/evaluate.js",
    "/features/history.js",
    "/features/submittable.js",
    "/features/resume-modal.js",
    "/features/readiness.js",
    "/features/beautify.js",
]


def _read_static(path: str) -> str:
    return (STATIC / path).read_text(encoding="utf-8")


def _home_script_text() -> str:
    return "\n".join(
        (STATIC / src.lstrip("/")).read_text(encoding="utf-8")
        for src in HOME_SCRIPTS[1:]
    )


def test_home_app_entrypoint_stays_thin() -> None:
    app_js = _read_static("app.js")

    assert len(app_js.splitlines()) < 200
    assert "async function loadProfile" not in app_js
    assert "async function runEvaluate" not in app_js
    assert "async function loadHistory" not in app_js
    assert "function openModal" not in app_js


def test_home_feature_scripts_are_loaded_in_dependency_order() -> None:
    html = _read_static("index.html")
    positions = []

    for src in HOME_SCRIPTS:
        script_tag = f'<script src="{src}"></script>'
        assert script_tag in html
        positions.append(html.index(script_tag))

    assert positions == sorted(positions)
    for src in HOME_SCRIPTS[2:]:
        assert (STATIC / src.lstrip("/")).exists()


def test_inline_handlers_are_defined_by_home_scripts() -> None:
    html = _read_static("index.html")
    script_text = _home_script_text()
    handler_bodies = re.findall(r"\bon\w+=\"([^\"]+)\"", html + "\n" + script_text)
    handler_names = {
        name
        for body in handler_bodies
        for name in re.findall(r"\b([A-Za-z_$][\w$]*)\s*\(", body)
    }

    exposed_functions = set(
        re.findall(r"^(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", script_text, re.M)
    )

    assert handler_names <= exposed_functions
