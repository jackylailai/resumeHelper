from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from math import ceil
from typing import Any

from backend.app.config import Settings

EVALUATE_WORKFLOW = "evaluate"
EVALUATE_LISTINGS_WORKFLOW = "evaluate_listings"
SCRAPE_AFTER_EVALUATE_WORKFLOW = "scrape_after_evaluate"
TAILOR_WORKFLOW = "tailor"

_EVALUATE_PROMPT_OVERHEAD_TOKENS = 800
_EVALUATE_MAX_OUTPUT_TOKENS = 1024
_TAILOR_PROMPT_OVERHEAD_TOKENS = 1200
_TAILOR_MAX_OUTPUT_TOKENS = 4096


@dataclass(frozen=True)
class BatchEstimate:
    workflow: str
    items: int
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    estimated_cost_usd: float | None = None

    @property
    def estimated_total_tokens(self) -> int:
        return self.estimated_input_tokens + self.estimated_output_tokens

    def details(self) -> dict[str, Any]:
        details: dict[str, Any] = {
            "workflow": self.workflow,
            "items": self.items,
            "estimated_input_tokens": self.estimated_input_tokens,
            "estimated_output_tokens": self.estimated_output_tokens,
            "estimated_total_tokens": self.estimated_total_tokens,
        }
        if self.estimated_cost_usd is not None:
            details["estimated_cost_usd"] = self.estimated_cost_usd
        return details


@dataclass(frozen=True)
class GuardrailResult:
    allowed: bool
    code: str | None = None
    message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class QuotaExceededError(RuntimeError):
    def __init__(self, result: GuardrailResult) -> None:
        super().__init__(result.message or "AI quota guard blocked this request")
        self.result = result


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, ceil(len(text) / 4))


def estimate_batch_cost_usd(
    settings: Settings,
    *,
    input_tokens: int,
    output_tokens: int,
) -> float | None:
    input_rate = Decimal(str(settings.llm_input_cost_per_million_tokens))
    output_rate = Decimal(str(settings.llm_output_cost_per_million_tokens))
    if input_rate <= 0 and output_rate <= 0:
        return None
    cost = (
        Decimal(input_tokens) * input_rate
        + Decimal(output_tokens) * output_rate
    ) / Decimal(1_000_000)
    return float(cost.quantize(Decimal("0.000001")))


def cost_usd_to_micros(cost_usd: float | None) -> int | None:
    if cost_usd is None:
        return None
    micros = Decimal(str(cost_usd)) * Decimal(1_000_000)
    return int(micros.to_integral_value())


def estimate_evaluation_batch(
    settings: Settings,
    *,
    workflow: str,
    profile_text: str,
    jd_texts: list[str],
) -> BatchEstimate:
    profile_tokens = estimate_tokens(profile_text)
    input_tokens = sum(
        profile_tokens + estimate_tokens(jd_text) + _EVALUATE_PROMPT_OVERHEAD_TOKENS
        for jd_text in jd_texts
    )
    output_tokens = len(jd_texts) * _EVALUATE_MAX_OUTPUT_TOKENS
    return BatchEstimate(
        workflow=workflow,
        items=len(jd_texts),
        estimated_input_tokens=input_tokens,
        estimated_output_tokens=output_tokens,
        estimated_cost_usd=estimate_batch_cost_usd(
            settings,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
    )


def estimate_tailoring_batch(
    settings: Settings,
    *,
    baseline_text: str,
    jobs: list[dict[str, Any]],
) -> BatchEstimate:
    baseline_tokens = estimate_tokens(baseline_text)
    input_tokens = 0
    for job in jobs:
        input_tokens += (
            baseline_tokens
            + estimate_tokens(str(job.get("jd_text") or ""))
            + estimate_tokens("\n".join(job.get("gaps") or []))
            + _TAILOR_PROMPT_OVERHEAD_TOKENS
        )
    output_tokens = len(jobs) * _TAILOR_MAX_OUTPUT_TOKENS
    return BatchEstimate(
        workflow=TAILOR_WORKFLOW,
        items=len(jobs),
        estimated_input_tokens=input_tokens,
        estimated_output_tokens=output_tokens,
        estimated_cost_usd=estimate_batch_cost_usd(
            settings,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
    )


def enforce_batch_guardrails(
    settings: Settings,
    *,
    workflow: str,
    estimate: BatchEstimate,
    max_items: int,
) -> None:
    result = check_batch_guardrails(
        settings,
        workflow=workflow,
        estimate=estimate,
        max_items=max_items,
    )
    if not result.allowed:
        raise QuotaExceededError(result)


def check_batch_guardrails(
    settings: Settings,
    *,
    workflow: str,
    estimate: BatchEstimate,
    max_items: int,
) -> GuardrailResult:
    if (
        estimate.items > 0
        and not settings.ai_provider_calls_enabled
        and settings.llm_backend != "fake"
    ):
        return _blocked(
            "ai_provider_calls_disabled",
            "AI provider calls are disabled by configuration.",
            estimate,
            {"setting": "AI_PROVIDER_CALLS_ENABLED"},
        )
    if max_items > 0 and estimate.items > max_items:
        return _blocked(
            "ai_batch_item_limit_exceeded",
            f"{workflow} requested {estimate.items} items; limit is {max_items}.",
            estimate,
            {"max_items": max_items},
        )
    if (
        settings.max_batch_estimated_tokens > 0
        and estimate.estimated_total_tokens > settings.max_batch_estimated_tokens
    ):
        return _blocked(
            "ai_batch_token_limit_exceeded",
            (
                f"{workflow} estimated {estimate.estimated_total_tokens} tokens; "
                f"limit is {settings.max_batch_estimated_tokens}."
            ),
            estimate,
            {"max_estimated_tokens": settings.max_batch_estimated_tokens},
        )
    if (
        settings.max_batch_estimated_cost_usd > 0
        and estimate.estimated_cost_usd is not None
        and estimate.estimated_cost_usd > settings.max_batch_estimated_cost_usd
    ):
        return _blocked(
            "ai_batch_cost_limit_exceeded",
            (
                f"{workflow} estimated ${estimate.estimated_cost_usd:.6f}; "
                f"limit is ${settings.max_batch_estimated_cost_usd:.6f}."
            ),
            estimate,
            {"max_estimated_cost_usd": settings.max_batch_estimated_cost_usd},
        )
    return GuardrailResult(allowed=True, details=estimate.details())


def _blocked(
    code: str,
    message: str,
    estimate: BatchEstimate,
    extra: dict[str, Any],
) -> GuardrailResult:
    details = estimate.details()
    details.update(extra)
    return GuardrailResult(
        allowed=False,
        code=code,
        message=message,
        details=details,
    )
