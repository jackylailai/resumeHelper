#!/usr/bin/env python
"""Download the latest GitHub Actions E2E screenshot artifact.

The E2E workflow uploads `tools/e2e/screenshots/` as an artifact named
`e2e-screenshots`. This script copies the latest non-expired artifact into the
docs asset tree so user-facing guides can reference stable screenshots.

Authentication order:
1. GITHUB_TOKEN
2. GH_TOKEN
3. `git credential fill` for github.com
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "docs" / "assets" / "e2e-screenshots"


def _github_token() -> str | None:
    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        value = os.environ.get(name)
        if value:
            return value

    powershell_token = _github_token_from_powershell()
    if powershell_token:
        return powershell_token

    try:
        proc = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            text=True,
            capture_output=True,
            check=True,
            cwd=PROJECT_ROOT,
        )
    except (OSError, subprocess.CalledProcessError):
        return _github_token_from_powershell()

    for line in proc.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    return _github_token_from_powershell()


def _github_token_from_powershell() -> str | None:
    if os.name != "nt":
        return None
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if not powershell:
        return None
    script = (
        "$credText = \"protocol=https`nhost=github.com`n`n\" | "
        "git credential fill;"
        "foreach ($line in $credText) { "
        "if ($line -match '^password=(.*)$') { $matches[1]; break } "
        "}"
    )
    try:
        proc = subprocess.run(
            [powershell, "-NoProfile", "-Command", script],
            text=True,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    token = proc.stdout.strip()
    return token or None


def _request_json(url: str, token: str | None) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers=_headers(token),
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read().decode("utf-8")
        return json.loads(payload)
    except (OSError, json.JSONDecodeError):
        if os.name == "nt":
            try:
                return _request_json_with_powershell(url, token)
            except (OSError, subprocess.CalledProcessError):
                pass
        return json.loads(_request_bytes_fallback(url, token).decode("utf-8"))


def _request_bytes(url: str, token: str | None) -> bytes:
    request = urllib.request.Request(
        url,
        headers=_headers(token),
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read()
    except OSError:
        return _request_bytes_fallback(url, token)


def _request_bytes_fallback(url: str, token: str | None) -> bytes:
    if os.name == "nt":
        try:
            return _request_bytes_with_powershell(url, token)
        except (OSError, subprocess.CalledProcessError):
            pass
    return _request_bytes_with_curl(url, token)


def _request_bytes_with_powershell(url: str, token: str | None) -> bytes:
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if not powershell:
        raise RuntimeError("PowerShell is not available")

    with tempfile.NamedTemporaryFile(delete=False) as fh:
        out_path = Path(fh.name)
    script = (
        "$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8;"
        "$headers = @{"
        "Accept='application/vnd.github+json';"
        "'X-GitHub-Api-Version'='2022-11-28';"
        "'User-Agent'='resumeHelper-e2e-screenshot-downloader'"
        "};"
        "if ($env:GH_DOWNLOAD_TOKEN) { "
        "$headers.Authorization = 'Bearer ' + $env:GH_DOWNLOAD_TOKEN "
        "};"
        "Invoke-WebRequest -Method Get -Uri $env:GH_DOWNLOAD_URL "
        "-Headers $headers -OutFile $env:GH_DOWNLOAD_OUT"
    )
    env = {
        **os.environ,
        "GH_DOWNLOAD_URL": url,
        "GH_DOWNLOAD_OUT": str(out_path),
        "GH_DOWNLOAD_TOKEN": token or "",
    }
    try:
        subprocess.run(
            [powershell, "-NoProfile", "-Command", script],
            check=True,
            capture_output=True,
            env=env,
        )
        return out_path.read_bytes()
    finally:
        out_path.unlink(missing_ok=True)


def _request_json_with_powershell(url: str, token: str | None) -> dict[str, Any]:
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if not powershell:
        raise RuntimeError("PowerShell is not available")

    with tempfile.NamedTemporaryFile(delete=False) as fh:
        out_path = Path(fh.name)
    script = (
        "$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8;"
        "$headers = @{"
        "Accept='application/vnd.github+json';"
        "'X-GitHub-Api-Version'='2022-11-28';"
        "'User-Agent'='resumeHelper-e2e-screenshot-downloader'"
        "};"
        "if ($env:GH_DOWNLOAD_TOKEN) { "
        "$headers.Authorization = 'Bearer ' + $env:GH_DOWNLOAD_TOKEN "
        "};"
        "$result = Invoke-RestMethod -Method Get -Uri $env:GH_DOWNLOAD_URL "
        "-Headers $headers;"
        "$result | ConvertTo-Json -Depth 20 | "
        "Set-Content -Encoding UTF8 -LiteralPath $env:GH_DOWNLOAD_OUT"
    )
    env = {
        **os.environ,
        "GH_DOWNLOAD_URL": url,
        "GH_DOWNLOAD_OUT": str(out_path),
        "GH_DOWNLOAD_TOKEN": token or "",
    }
    try:
        subprocess.run(
            [powershell, "-NoProfile", "-Command", script],
            check=True,
            capture_output=True,
            env=env,
        )
        return json.loads(out_path.read_text(encoding="utf-8-sig"))
    finally:
        out_path.unlink(missing_ok=True)


def _request_bytes_with_curl(url: str, token: str | None) -> bytes:
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if not curl:
        raise RuntimeError("curl is required after urllib download failed")

    args = [
        curl,
        "-L",
        "-k",
        "-sS",
        "-H",
        "Accept: application/vnd.github+json",
        "-H",
        "X-GitHub-Api-Version: 2022-11-28",
        "-H",
        "User-Agent: resumeHelper-e2e-screenshot-downloader",
    ]
    if token:
        args.extend(["-H", f"Authorization: Bearer {token}"])
    args.append(url)
    proc = subprocess.run(args, capture_output=True, check=True)
    return proc.stdout


def _headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "resumeHelper-e2e-screenshot-downloader",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _latest_artifact(repo: str, artifact_name: str, token: str | None) -> dict[str, Any]:
    url = (
        f"https://api.github.com/repos/{repo}/actions/artifacts"
        f"?name={artifact_name}&per_page=20"
    )
    payload = _request_json(url, token)
    artifacts = [
        artifact
        for artifact in payload.get("artifacts", [])
        if not artifact.get("expired")
    ]
    if not artifacts:
        raise RuntimeError(f"No non-expired artifact named {artifact_name!r} found")
    return artifacts[0]


def download(repo: str, artifact_name: str, output: Path) -> int:
    token = _github_token()
    artifact = _latest_artifact(repo, artifact_name, token)
    blob = _request_bytes(artifact["archive_download_url"], token)

    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(BytesIO(blob)) as archive:
        archive.extractall(output)
        count = len([name for name in archive.namelist() if not name.endswith("/")])

    print(
        f"Downloaded artifact {artifact['id']} ({artifact_name}) "
        f"from {artifact['created_at']} to {output}"
    )
    print(f"Extracted {count} files")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="jackylailai/resumeHelper")
    parser.add_argument("--artifact-name", default="e2e-screenshots")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    try:
        return download(args.repo, args.artifact_name, args.output)
    except Exception as exc:  # noqa: BLE001
        print(f"download failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
