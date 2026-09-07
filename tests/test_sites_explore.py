from __future__ import annotations

from datetime import UTC, datetime
from math import isnan
from urllib.parse import parse_qs, urlparse

import pytest

from www.sites.calculator import build_llm_self_hosting_view
from www.sites.data import DEFAULT_HOSTING_INPUTS
from www.sites.economics import api_monthly_cost, current_api_baselines
from www.sites.formatting import format_decimal, format_number, format_usd, format_usd2
from www.sites.inputs import hosting_url

NOW = datetime(2026, 9, 5, 12, tzinfo=UTC)


def view(query: dict[str, str] | dict[str, list[str]] | None = None):
    return build_llm_self_hosting_view(query, now=NOW)


def test_api_modes_include_warmup_and_storage() -> None:
    batch = view({"api-mode": "batch"})
    assert [row.monthly_usd for row in batch.apis] == pytest.approx([6.6, 17.6, 88])

    cached = view(
        {
            "api-mode": "cached",
            "cache-prefix": "4096",
            "input-tokens": "6000",
            "tokens": "500",
            "requests": "20",
            "days": "1",
        },
    )
    assert [row.monthly_usd for row in cached.apis] == pytest.approx(
        [0.07237466666666667, 0.2019648, 1.009824],
    )
    for baseline in current_api_baselines(NOW, cached.inputs):
        _, one_group = api_monthly_cost(cached.inputs, baseline, 20)
        _, partial_group = api_monthly_cost(cached.inputs, baseline, 21)
        assert partial_group == one_group * 2

    fallback = view({"api-mode": "cached"})
    assert fallback.apis[0].monthly_usd == 13.2
    assert "Standard rates applied" in fallback.apis[0].mode_note
    assert fallback.apis[1].monthly_usd < 35.2

    invalid_prefix = view({"api-mode": "cached", "cache-prefix": "9999"})
    assert invalid_prefix.apis[1].monthly_usd == 35.2


def test_cached_break_even_is_first_whole_request() -> None:
    result = view({"api-mode": "cached", "cache-prefix": "4096", "input-tokens": "6000"})

    for row in result.apis:
        before, _ = api_monthly_cost(result.inputs, row.baseline, row.break_even_requests - 1)
        at, _ = api_monthly_cost(result.inputs, row.baseline, row.break_even_requests)
        assert before < result.estimate.total_monthly_usd <= at


def test_price_expiry_and_review_are_visible() -> None:
    before = build_llm_self_hosting_view(
        now=datetime(2026, 12, 31, 23, 59, tzinfo=UTC),
    )
    after = build_llm_self_hosting_view(
        now=datetime(2027, 1, 1, tzinfo=UTC),
    )

    assert after.apis[0].monthly_usd == before.apis[0].monthly_usd * 2
    assert after.apis[1].monthly_usd == before.apis[1].monthly_usd
    assert after.apis[0].needs_review
    assert "overdue" in after.apis[0].freshness
    assert not view().apis[0].needs_review


def test_scenario_links_preserve_every_assumption() -> None:
    result = view(
        {
            "quality": "on",
            "api-mode": "cached",
            "quality-2-calls": "2.5",
            "measured-first": "1.3",
            "cache-requests": "7",
        },
    )

    for raw in (hosting_url(result.inputs), result.cost_plot.frames[result.cost_plot.selected].url):
        round_trip = view(parse_qs(urlparse(raw).query))
        assert round_trip.inputs == result.inputs
        assert not round_trip.validation

    for row_index, row in enumerate(result.sensitivity):
        for column_index, cell in enumerate(row.cells):
            candidate = view(parse_qs(urlparse(cell.url).query))
            assert candidate.inputs == cell.inputs
            assert not candidate.validation
            if row_index == column_index == 1:
                assert candidate.inputs == result.inputs


def test_cost_explorer_frames_use_billing_and_capacity() -> None:
    result = view()
    current = result.cost_plot.frames[result.cost_plot.selected]
    assert current.requests == result.estimate.requests_month
    assert "$13.20" in current.summary
    assert result.cost_plot.capacity_x
    assert len(result.cost_plot.break_evens) == 3

    previous = 0.0
    for frame in result.cost_plot.frames:
        assert frame.requests > previous
        assert "NaN" not in frame.x
        previous = frame.requests

    extreme = view({"requests": "10000000", "days": "31", "throughput": "0.1"})
    selected = extreme.cost_plot.frames[extreme.cost_plot.selected]
    assert selected.requests == 310_000_000
    assert "beyond" in selected.summary


@pytest.mark.parametrize(
    "query",
    [
        None,
        {"days": "1"},
        {"requests": "651.4", "days": "31"},
        {"api-mode": "cached", "input-tokens": "6000", "cache-prefix": "4096"},
        {"requests": "10000000", "node": "a4", "billing": "cud-3y", "model": "kimi-k3"},
    ],
)
def test_cost_chart_has_round_labels_and_workloads_with_exact_costs(query) -> None:
    result = view(query)
    for tick in (*result.cost_plot.x_ticks, *result.cost_plot.y_ticks):
        assert "." not in tick.label
    assert len(result.cost_plot.x_ticks) <= 5
    assert len(result.cost_plot.y_ticks) <= 5
    for index, frame in enumerate(result.cost_plot.frames):
        parsed = parse_qs(urlparse(frame.url).query)
        daily = float(parsed["requests"][0])
        if index != result.cost_plot.selected:
            assert daily.is_integer()
            assert str(int(daily)).rstrip("0") in {"1", "2", "5"}
        assert 1 <= daily <= 10_000_000
        assert frame.requests == daily * result.inputs.active_days
        assert "requests/day" in frame.label
        for api in result.apis:
            cost = api_monthly_cost(result.inputs, api.baseline, frame.requests)[0]
            assert f"{api.baseline.name} {format_usd2(cost)}" in frame.summary
        assert 130 <= float(frame.x) <= 720
    current = result.cost_plot.frames[result.cost_plot.selected]
    assert view(parse_qs(urlparse(current.url).query)).inputs == result.inputs
    for line in result.cost_plot.lines:
        for point in line.points.split():
            x, y = map(float, point.split(","))
            assert 130 <= x <= 720
            assert 40 <= y <= 300


def test_selected_node_describes_hardware_separately_from_billing() -> None:
    result = view()

    assert result.selected_node.name == "A2 Ultra · 1\u00d7 A100 · 80 GB"
    assert result.selected_price.label == "On-demand"
    assert result.selected_node.gpu == "1\u00d7 NVIDIA A100 80GB"


def test_accepted_task_cost_includes_retries_review_and_capacity() -> None:
    result = view(
        {
            "quality": "on",
            "tasks": "1000",
            "review-rate": "60",
            "quality-1-acceptance": "50",
            "quality-1-calls": "2",
            "quality-1-review": "3",
        },
    )
    row = result.tasks[1]
    assert row.requests == 2000
    assert row.accepted == 500
    assert row.model_usd == 7.5
    assert row.review_usd == 3000
    assert row.per_accepted_usd == 6.015

    overloaded = view({"tasks": "10000000", "quality-0-calls": "100"})
    assert not overloaded.tasks[0].fits


def test_latency_does_not_follow_monthly_capacity() -> None:
    result = view()
    assert result.estimate.demand_fits
    assert result.latency_title == "Responsiveness is still unproved"

    query = {
        "measured-concurrency": "8",
        "measured-first": "1.5",
        "measured-complete": "25",
        "confirm-pilot": view().current_pilot_config,
    }
    assert view(query).latency_title == "The recorded pilot meets your latency targets"
    query["measured-first"] = "3"
    assert view(query).latency_title == "The recorded pilot misses a latency target"
    query["measured-concurrency"] = "7"
    assert view(query).latency_title == "Responsiveness is still unproved"


def test_optional_input_validation_uses_explicit_defaults() -> None:
    result = view(
        {
            "api-mode": "free",
            "cache-requests": "0",
            "measured-first": "NaN",
            "quality-0-acceptance": "-1",
            "quality-1-calls": "0.5",
            "quality": "yes",
        },
    )

    assert len(result.validation) == 6
    assert result.inputs == DEFAULT_HOSTING_INPUTS
    assert result.validation == (
        "api-mode was not recognized; the default was used",
        "cache-requests must be between 1 and 1000000; the default was used",
        "quality was not recognized; the default was used",
        "measured-first must be between 0 and 3600; the default was used",
        "quality-0-acceptance must be between 0 and 100; the default was used",
        "quality-1-calls must be between 1 and 100; the default was used",
    )


@pytest.mark.parametrize("invalid", [" 2", "2 ", "1_0", "2.0", "\u0662"])
def test_integer_syntax_matches_go_boundary(invalid: str) -> None:
    result = view({"replicas": invalid})

    assert result.inputs.replicas == DEFAULT_HOSTING_INPUTS.replicas
    assert len(result.validation) == 1


def test_scenario_url_uses_shortest_round_trip_decimal_without_exponents() -> None:
    result = view({"quality-0-acceptance": "0.0000001"})

    raw = hosting_url(result.inputs)
    assert "quality-0-acceptance=0.0000001" in raw
    assert view(parse_qs(urlparse(raw).query)).inputs == result.inputs


def test_zero_acceptance_and_inconsistent_latency_do_not_imply_success() -> None:
    result = view(
        {
            "quality": "on",
            "quality-0-acceptance": "0",
            "measured-first": "10",
            "measured-complete": "5",
            "measured-concurrency": "8",
        },
    )

    assert result.tasks[0].accepted == 0
    assert not isnan(result.tasks[0].per_accepted_usd)
    assert len(result.validation) == 1
    assert result.inputs.measured_first_token == 0
    assert result.latency_title == "Responsiveness is still unproved"


@pytest.mark.parametrize(
    ("function", "value", "expected"),
    [
        (format_decimal, (1234.125, 2), "1,234.13"),
        (format_decimal, (-1234.5, 0), "-1,235"),
        (format_number, (2_500_000,), "2.50M"),
        (format_number, (1200,), "1.2k"),
        (format_usd, (1234.5,), "$1,235"),
        (format_usd2, (13.2,), "$13.20"),
    ],
)
def test_template_formatting_helpers(function, value: tuple[float, ...], expected: str) -> None:
    assert function(*value) == expected
