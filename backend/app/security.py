from __future__ import annotations

import base64
import secrets

from fastapi import Request

from backend.app.config import Settings

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def write_auth_required(request: Request, settings: Settings) -> bool:
    return (
        settings.management_auth_enabled
        and request.url.path.startswith("/api/")
        and request.method.upper() not in SAFE_METHODS
    )


def is_management_authorized(request: Request, settings: Settings) -> bool:
    authorization = request.headers.get("authorization", "")
    scheme, _, value = authorization.partition(" ")
    scheme = scheme.lower()

    if scheme == "bearer" and settings.management_auth_token:
        return secrets.compare_digest(value.strip(), settings.management_auth_token)

    if scheme == "basic" and settings.management_auth_username and settings.management_auth_password:
        credentials = _decode_basic_credentials(value)
        if credentials is None:
            return False
        username, password = credentials
        return secrets.compare_digest(
            username,
            settings.management_auth_username,
        ) and secrets.compare_digest(password, settings.management_auth_password)

    return False


def _decode_basic_credentials(value: str) -> tuple[str, str] | None:
    try:
        decoded = base64.b64decode(value, validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    username, separator, password = decoded.partition(":")
    if not separator:
        return None
    return username, password
