"""Self-hosting calculator formatting."""

from math import floor

from .economics import HostingVerdict, hosting_verdict
from .models import APIComparison, LLMSelfHostingView


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


_NUMBER_UNITS = (("", 1.0, 0), ("k", 1e3, 1), ("M", 1e6, 2), ("B", 1e9, 2), ("T", 1e12, 2))


def _scaled(value: float, scale: float, digits: int) -> float:
    factor = 10**digits
    return _round_away_from_zero(value / scale * factor) / factor


_BUDGET_UNITS = (("k", 1e3), ("M", 1e6), ("B", 1e9))


def format_budget(value: float) -> str:
    """Keep planning headlines coarse while retaining readable small API bills."""
    if value < 10:
        return format_usd2(value)
    if value < 1000:
        return format_usd(value)
    # Choose the unit after rounding so $999,960 becomes $1.0M rather than $1,000.0k.
    suffix, scale = next(
        (unit for unit in _BUDGET_UNITS[:-1] if _scaled(value, unit[1], 1) < 1000),
        _BUDGET_UNITS[-1],
    )
    return "$" + format_decimal(value / scale, 1) + suffix


def format_input(value: float) -> str:
    """Echo a visitor's input without hiding its decimals: 12.5 stays 12.5, not 13."""
    return format_decimal(value, 2).rstrip("0").rstrip(".")


def format_number(value: float) -> str:
    """Abbreviate a quantity, rounding half away from zero like `format_decimal`."""
    # Choose the unit after rounding so 999.6 becomes 1.0k rather than 1000.
    suffix, scale, digits = next(
        (unit for unit in _NUMBER_UNITS[:-1] if abs(_scaled(value, unit[1], unit[2])) < 1000),
        _NUMBER_UNITS[-1],
    )
    return f"{_scaled(value, scale, digits):.{digits}f}{suffix}"


def format_count(value: int, noun: str) -> str:
    """Format a whole quantity with a simple English plural."""
    suffix = "" if value == 1 else "s"
    return f"{format_decimal(float(value), 0)} {noun}{suffix}"


_DECISION_TITLES = {
    "unsupported": "This configuration is not supported",
    "context": "The request exceeds this model's context limit",
    "topology": "Confirm this multi-host configuration with a pilot",
    "capacity": "This fleet cannot cover the modeled demand",
    "no-api": "No managed API baseline accepts this request",
    "api-cheaper": "Start with an API on cost grounds",
    "fleet-case": "Self-hosting has a cost case to test",
}
_DECISION_COPY = {
    "topology": (
        "The model spans more than one host. Record latency and completion measurements on this exact serving "
        "configuration before using its capacity or cost verdict."
    ),
    "capacity": (
        "Do not treat the current fleet bill as a quote for all this work. Increase replicas, measure a faster "
        "configuration, or reduce demand, then recalculate. A monthly average cannot establish peak-time capacity."
    ),
    "no-api": "Reduce the input or output budget before comparing this fleet with managed APIs.",
    "fleet-case": (
        "The modeled fleet bill is below these API baselines at your demand. This is a candidate for a pilot: verify "
        "quality, sustained throughput, memory, model terms, and an operating owner before committing capacity."
    ),
}


def _decision(view: LLMSelfHostingView) -> tuple[HostingVerdict, APIComparison | None]:
    cheapest = min((row for row in view.apis if not row.request_issue), key=lambda row: row.monthly_usd, default=None)
    return hosting_verdict(view.estimate, None if cheapest is None else cheapest.monthly_usd), cheapest


def hosting_decision_title(view: LLMSelfHostingView) -> str:
    """Summarize the immediate economic conclusion without hiding capacity."""
    return _DECISION_TITLES[_decision(view)[0]]


def hosting_decision_copy(view: LLMSelfHostingView) -> str:
    """Explain the capacity and cost conclusion in decision-ready language."""
    verdict, cheapest = _decision(view)
    if verdict == "unsupported":
        return (
            view.estimate.compatibility_issue
            + ". Choose compatible hardware or the model's published checkpoint format."
        )
    if verdict == "context":
        return view.estimate.context_issue + ". Reduce the request or choose a model with a larger context window."
    if verdict == "api-cheaper" and cheapest:
        return (
            f"{cheapest.baseline.name} starts at {format_budget(cheapest.monthly_usd)}/month for this token budget. "
            "Self-hosting may still be worth paying for control, residency, or customization. "
            "Test task quality before choosing."
        )
    return _DECISION_COPY[verdict]
