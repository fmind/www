"""Self-hosting calculator charts."""

from __future__ import annotations

from dataclasses import replace
from math import ceil, floor, log10

from .economics import api_monthly_cost
from .formatting import format_decimal, format_number, format_usd2
from .inputs import hosting_url
from .models import (
    APIComparison,
    CostFrame,
    CostPlot,
    HostingEstimate,
    HostingInputs,
    PlotLine,
    PlotTick,
)


def _plot_coordinate(value: float) -> str:
    return f"{value:.2f}"


def _chart_number(value: float) -> str:
    for suffix, scale in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("k", 1e3)):
        if value >= scale:
            return f"{value / scale:g}{suffix}"
    return f"{value:g}"


def _per(value: float, unit: str) -> str:
    text = format_number(value) if unit == "day" else format_decimal(value, 0)
    return f"{text} {'request' if text == '1' else 'requests'}/{unit}"


def _sparse_ticks(values: list[float]) -> list[float]:
    # At most five labels keeps the same chart readable on a phone.
    return [values[round(index * (len(values) - 1) / 4)] for index in range(5)] if len(values) > 5 else values


def hosting_cost_plot(
    inputs: HostingInputs,
    estimate: HostingEstimate,
    apis: tuple[APIComparison, ...],
) -> CostPlot:
    capacity = estimate.capacity_tokens_month / inputs.output_tokens_request
    # APIs that cannot accept this request have no meaningful cost curve.
    available = tuple((series, api) for series, api in enumerate(apis, start=1) if not api.request_issue)
    max_break_even = max((api.break_even_requests for _, api in available), default=0.0)
    max_daily = min(
        10_000_000,
        max(
            inputs.requests_per_day * 4,
            max_break_even / inputs.active_days * 1.2,
            capacity / inputs.active_days * 1.2,
        ),
    )
    # Bound the axes with whole decades; geometric sample coordinates are never labels.
    min_requests = 10 ** floor(log10(inputs.active_days))
    max_requests = 10 ** ceil(log10(max(10, max_daily) * inputs.active_days))
    log_span = log10(max_requests / min_requests)

    def x(requests: float) -> str:
        return _plot_coordinate(
            130 + log10(max(min_requests, requests) / min_requests) / log_span * 590,
        )

    max_cost = max(
        (
            estimate.total_monthly_usd,
            *(api_monthly_cost(inputs, api.baseline, max_requests)[0] for _, api in available),
        ),
    )

    max_cost = 10 ** ceil(log10(max(1, max_cost)))

    def y(cost: float) -> str:
        return _plot_coordinate(300 - log10(1 + cost) / log10(1 + max_cost) * 260)

    capacity_x = ""
    capacity_width = ""
    if min_requests <= capacity <= max_requests:
        capacity_x = x(capacity)
        capacity_width = _plot_coordinate(
            720 - float(capacity_x),
        )

    # Slider steps are whole, round daily workloads; preserve the user's exact scenario.
    daily_values = {inputs.requests_per_day}
    daily_values.update(
        float(multiplier * 10**exponent)
        for exponent in range(8)
        for multiplier in (1, 2, 5)
        if multiplier * 10**exponent <= min(10_000_000, max_requests / inputs.active_days)
    )
    break_evens = tuple(
        PlotTick(
            x(api.break_even_requests),
            f"{api.baseline.name}: {format_decimal(api.break_even_requests, 0)} requests/month",
        )
        for _, api in available
        if min_requests <= api.break_even_requests <= max_requests
    )

    paths: dict[int, list[str]] = {series: [] for series in (0, *(series for series, _ in available))}
    frames: list[CostFrame] = []
    selected = 0
    # Curves use a dense sampling independently of the human-readable slider steps.
    for index in range(61):
        requests = min_requests * 10 ** (log_span * index / 60)
        paths[0].append(f"{x(requests)},{y(estimate.total_monthly_usd)}")
        for series, api in available:
            total = api_monthly_cost(inputs, api.baseline, requests)[0]
            paths[series].append(f"{x(requests)},{y(total)}")
    for index, daily in enumerate(sorted(daily_values)):
        scenario = replace(inputs, requests_per_day=daily)
        requests = daily * inputs.active_days
        label = f"{_per(daily, 'day')} · {_per(requests, 'month')}"
        fit = "within modeled capacity" if requests <= capacity else "beyond this fleet's capacity"
        summary = f"{label} · {fit}. GKE fleet {format_usd2(estimate.total_monthly_usd)}"
        for api in apis:
            if api.request_issue:
                summary += f" · {api.baseline.name} unavailable"
            else:
                summary += f" · {api.baseline.name} {format_usd2(api_monthly_cost(inputs, api.baseline, requests)[0])}"
        frames.append(
            CostFrame(
                x=x(requests),
                label=label,
                summary=summary + " per month.",
                url=hosting_url(scenario),
                requests=requests,
            ),
        )
        if daily == inputs.requests_per_day:
            selected = index

    names = {0: "GKE fleet", **{series: api.baseline.name for series, api in available}}
    lines = tuple(
        PlotLine(name=names[series], points=" ".join(points), series=series) for series, points in paths.items()
    )
    request_ticks = [float(10**exponent) for exponent in range(int(log10(min_requests)), int(log10(max_requests)) + 1)]
    cost_ticks = [0.0, *(float(10**exponent) for exponent in range(int(log10(max_cost)) + 1))]
    x_ticks = tuple(PlotTick(x(requests), _chart_number(requests)) for requests in _sparse_ticks(request_ticks))
    y_ticks = tuple(PlotTick(y(cost), f"${_chart_number(cost)}") for cost in _sparse_ticks(cost_ticks))
    return CostPlot(
        capacity_x=capacity_x,
        capacity_width=capacity_width,
        capacity_label=f"{format_decimal(capacity, 0)} requests/month",
        fleet_y=y(estimate.total_monthly_usd),
        lines=lines,
        frames=tuple(frames),
        x_ticks=tuple(x_ticks),
        y_ticks=tuple(y_ticks),
        break_evens=tuple(break_evens),
        selected=selected,
        unavailable=tuple(f"{api.baseline.name}: {api.request_issue}" for api in apis if api.request_issue),
    )
