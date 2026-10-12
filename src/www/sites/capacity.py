"""Shared serving assumptions for automatic sizing and fixed-fleet estimates."""

from __future__ import annotations

from dataclasses import replace
from math import ceil

from .models import HostingInputs

MONTHLY_HOURS = 730.0


def serving_capacity(inputs: HostingInputs) -> tuple[float, float]:
    """Return monthly output tokens and requests per active-day window."""
    usable_rate = inputs.tokens_per_second * inputs.replicas * inputs.target_utilization / 100
    # Paid hours can be scheduled inside active windows. Applying the monthly
    # running fraction to each window would count downtime a second time.
    running_hours = MONTHLY_HOURS * (inputs.duty_cycle_percent / 100)
    return (
        usable_rate * running_hours * 3600,
        usable_rate * inputs.demand_window_hours * 60 * 60 / inputs.output_tokens_request,
    )


def replicas_for_demand(inputs: HostingInputs) -> int:
    """Round up complete model copies to cover both monthly and window demand."""
    monthly_tokens, daily_requests = serving_capacity(replace(inputs, replicas=1))
    return max(
        1,
        ceil(inputs.requests_per_day * inputs.active_days * inputs.output_tokens_request / monthly_tokens),
        ceil(inputs.requests_per_day / daily_requests),
    )
