from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass

from fastapi import Request

from backend.app.config import Settings


@dataclass(frozen=True)
class RateLimitRule:
    key: str
    limit: int
    window_seconds: int = 60


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    window_seconds: int
    retry_after_seconds: int = 0


@dataclass
class _Window:
    started_at: float
    count: int
    window_seconds: int


class FixedWindowRateLimiter:
    def __init__(self) -> None:
        self._windows: dict[tuple[str, str], _Window] = {}
        self._lock = threading.Lock()
        self._checks = 0

    def check(
        self,
        *,
        route_key: str,
        client_id: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        now = time.monotonic()
        bucket_key = (route_key, client_id)
        with self._lock:
            self._checks += 1
            if self._checks % 256 == 0:
                self._prune_expired(now)

            window = self._windows.get(bucket_key)
            if window is None or now - window.started_at >= window_seconds:
                self._windows[bucket_key] = _Window(
                    started_at=now,
                    count=1,
                    window_seconds=window_seconds,
                )
                return RateLimitDecision(
                    allowed=True,
                    limit=limit,
                    window_seconds=window_seconds,
                )

            if window.count < limit:
                window.count += 1
                return RateLimitDecision(
                    allowed=True,
                    limit=limit,
                    window_seconds=window_seconds,
                )

            retry_after = max(1, math.ceil(window_seconds - (now - window.started_at)))
            return RateLimitDecision(
                allowed=False,
                limit=limit,
                window_seconds=window_seconds,
                retry_after_seconds=retry_after,
            )

    def _prune_expired(self, now: float) -> None:
        expired = [
            bucket_key
            for bucket_key, window in self._windows.items()
            if now - window.started_at >= window.window_seconds
        ]
        for bucket_key in expired:
            del self._windows[bucket_key]


def rate_limit_rule_for(request: Request, settings: Settings) -> RateLimitRule | None:
    if request.method.upper() != "POST":
        return None

    path = request.url.path.rstrip("/")
    if path == "/api/evaluate":
        return _rule("evaluate", settings.rate_limit_evaluate_per_minute)
    if path == "/api/evaluate/bulk":
        return _rule("evaluate_bulk", settings.rate_limit_evaluate_bulk_per_minute)
    if path in {"/api/evaluate/by-listings", "/api/evaluate/pending-listings"}:
        return _rule("evaluate_batch", settings.rate_limit_evaluate_batch_per_minute)
    if path == "/api/scrape/run":
        return _rule("scrape_run", settings.rate_limit_scrape_run_per_minute)
    if path.endswith("/beautify"):
        return _rule("beautify", settings.rate_limit_beautify_per_minute)
    if path == "/api/callback":
        return _rule("callback", settings.rate_limit_callback_per_minute)
    return None


def _rule(key: str, limit: int) -> RateLimitRule | None:
    if limit <= 0:
        return None
    return RateLimitRule(key=key, limit=limit)


def client_identifier(request: Request) -> str:
    if request.client is None or not request.client.host:
        return "unknown"
    return request.client.host
