"""Self-hosting calculator formatting."""

from __future__ import annotations

from collections.abc import Sequence
from math import floor

from .models import (
    LLMSelfHostingView,
    TaskComparison,
)


def _round_away_from_zero(value: float) -> float:
    return float(floor(value + 0.5) if value >= 0 else -floor(-value + 0.5))


def format_decimal(value: float, digits: int) -> str:
    scale = 10**digits
    rounded = _round_away_from_zero(value * scale) / scale
    return f"{rounded:,.{digits}f}"


def format_usd(value: float) -> str:
    return "$" + format_decimal(value, 0)


def format_usd2(value: float) -> str:
    return "$" + format_decimal(value, 2)


def format_number(value: float) -> str:
    if value >= 1e12:
        return f"{value / 1e12:.2f}T"
    if value >= 1e9:
        return f"{value / 1e9:.2f}B"
    if value >= 1e6:
        return f"{value / 1e6:.2f}M"
    if value >= 1e3:
        return f"{value / 1e3:.1f}k"
    return f"{value:.0f}"


def format_count(value: int, noun: str) -> str:
    """Format a whole quantity with a simple English plural."""
    suffix = "" if value == 1 else "s"
    return f"{format_decimal(float(value), 0)} {noun}{suffix}"


def task_cost_max(rows: Sequence[TaskComparison]) -> float:
    """Return the non-zero scale used by the accepted-task comparison bars."""
    return max((row.per_accepted_usd for row in rows if row.fits), default=0.01)


def hosting_decision_title(view: LLMSelfHostingView) -> str:
    """Summarize the immediate economic conclusion without hiding capacity."""
    if view.estimate.context_issue:
        return "The request exceeds this model's context limit"
    if not view.estimate.topology_confirmed:
        return "Confirm this multi-host configuration with a pilot"
    if not view.estimate.demand_fits:
        return "This fleet cannot cover the modeled demand"
    available = tuple(row for row in view.apis if not row.request_issue)
    if not available:
        return "No managed API baseline accepts this request"
    if min(row.monthly_usd for row in available) < view.estimate.total_monthly_usd:
        return "Start with an API on cost grounds"
    return "Self-hosting has a cost case to test"


def hosting_decision_copy(view: LLMSelfHostingView) -> str:
    """Explain the capacity and cost conclusion in decision-ready language."""
    if view.estimate.context_issue:
        return view.estimate.context_issue + ". Reduce the request or choose a model with a larger context window."
    if not view.estimate.topology_confirmed:
        return (
            "The model spans more than one host. Record latency and completion measurements on this exact serving "
            "configuration before using its capacity or cost verdict."
        )
    if not view.estimate.demand_fits:
        return (
            "Do not treat the current fleet bill as a quote for all this work. Increase replicas, measure a faster "
            "configuration, or reduce demand, then recalculate. A monthly average cannot establish peak-time capacity."
        )
    available = tuple(row for row in view.apis if not row.request_issue)
    if not available:
        return "Reduce the input or output budget before comparing this fleet with managed APIs."
    cheapest = min(available, key=lambda row: row.monthly_usd)
    if cheapest.monthly_usd < view.estimate.total_monthly_usd:
        return (
            f"{cheapest.baseline.name} is {format_usd2(cheapest.monthly_usd)}/month for this token mix, versus "
            f"{format_usd2(view.estimate.total_monthly_usd)} for your fleet. Self-hosting needs enough value from "
            "control, residency, customization, or avoided quality failures to cover the difference. Compare task "
            "success before choosing."
        )
    return (
        "The modeled fleet bill is below these API baselines at your demand. This is a candidate for a pilot: verify "
        "quality, sustained throughput, memory, model terms, and an operating owner before committing capacity."
    )
