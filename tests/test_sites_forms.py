"""Regression tests for calculator form fidelity, API availability, and page semantics."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any

import pytest
from litestar.testing import TestClient

import www.sites.economics as economics
from www.app import create_app
from www.sites.agent import compare_hosting
from www.sites.calculator import build_llm_self_hosting_view
from www.sites.data import API_BASELINES
from www.sites.formatting import format_decimal, format_number
from www.sites.inputs import scenario_parameters

NOW = datetime(2026, 9, 7, tzinfo=UTC)
PAGE = "/sites/llm-self-hosting/"
QUALIFIED_VERDICTS = {"Fleet has a cost case", "API costs less", "No API accepts this request"}

type AppClient = TestClient[Any]


def view(query: dict[str, str] | None = None):
    return build_llm_self_hosting_view(query, now=NOW)


class NumberInputs(HTMLParser):
    """Collect the calculator's number inputs by name."""

    def __init__(self) -> None:
        super().__init__()
        self.inputs: dict[str, dict[str, str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "input" and values.get("type") == "number":
            self.inputs[values["name"]] = values


def number_inputs(html: str) -> dict[str, dict[str, str]]:
    parser = NumberInputs()
    parser.feed(html)
    return parser.inputs


@pytest.fixture(scope="module")
def client() -> Iterator[AppClient]:
    # A fresh app: the MCP session manager inside one instance can only start once per process.
    with TestClient(create_app()) as test_client:
        yield test_client


def test_number_inputs_render_the_exact_shareable_values(client: AppClient) -> None:
    measured = view({"requests": "1234567", "throughput": "123.4567"})
    query = {
        "requests": "1234567",
        "throughput": "123.4567",
        "measured-first": "1",
        "measured-complete": "5",
        "measured-concurrency": "8",
        "confirm-pilot": measured.current_pilot_config,
    }
    original = view(query)
    assert original.inputs.pilot_config

    inputs = number_inputs(client.get(PAGE, params=query).text)

    assert inputs["requests"]["value"] == "1234567"
    assert inputs["throughput"]["value"] == "123.4567"
    # Resubmitting the rendered form keeps the scenario and its bound pilot evidence.
    resubmitted = scenario_parameters(original.inputs) | {name: item["value"] for name, item in inputs.items()}
    replay = view(resubmitted)
    assert replay.inputs == original.inputs
    assert not replay.validation


def test_form_steps_match_server_parsing(client: AppClient) -> None:
    inputs = number_inputs(client.get(PAGE).text)
    assert inputs

    for name, item in inputs.items():
        fractional = format(float(item["min"]) + 0.5, "g")
        result = view({name: fractional})
        if item["step"] == "1":
            assert result.validation == (
                f"{name} must be a whole number between {item['min']} and {item['max']}; the default was used",
            ), name
        else:
            assert item["step"] == "any", name
            assert not result.validation, name


@pytest.mark.parametrize("parameter", ["days", "tokens", "input-tokens", "cache-prefix", "tasks"])
def test_whole_quantities_reject_fractions_for_agents(parameter: str) -> None:
    assert view({parameter: "21"}).validation == ()
    with pytest.raises(ValueError, match=f"{parameter} must be a whole number"):
        compare_hosting({parameter: "21.5"})


def test_unavailable_apis_are_never_the_lowest_or_plotted() -> None:
    result = view({"tokens": "100000"})
    gemini, *available = result.apis
    assert gemini.request_issue
    assert all(not api.request_issue for api in available)

    for row in result.sensitivity:
        for cell in row.cells:
            requests = cell.inputs.requests_per_day * cell.inputs.active_days
            costs = [economics.api_monthly_cost(cell.inputs, api.baseline, requests)[0] for api in available]
            assert cell.cheapest_api_usd == min(costs)

    plot = result.cost_plot
    assert [(line.series, line.name) for line in plot.lines] == [
        (0, "GKE fleet"),
        *((index, api.baseline.name) for index, api in enumerate(result.apis, start=1) if not api.request_issue),
    ]
    assert plot.unavailable == (f"{gemini.baseline.name}: {gemini.request_issue}",)
    assert all(gemini.baseline.name not in tick.label for tick in plot.break_evens)
    assert all(f"{gemini.baseline.name} unavailable" in frame.summary for frame in plot.frames)


def test_no_available_api_is_explicit(client: AppClient) -> None:
    query = {"tokens": "200000", "requests": "1"}
    result = view(query)
    assert all(api.request_issue for api in result.apis)
    assert [line.name for line in result.cost_plot.lines] == ["GKE fleet"]
    cells = [cell for row in result.sensitivity for cell in row.cells]
    assert all(cell.cheapest_api_usd is None for cell in cells)
    assert any(cell.verdict == "No API accepts this request" for cell in cells)

    html = client.get(PAGE, params=query).text
    assert "Lowest API: none accepts this request" in html
    assert "one fixed GKE fleet and 0 managed APIs" in html


@pytest.mark.parametrize(
    "query",
    [
        None,
        {"requests": "4000"},
        {"node": "g2-standard-12"},
        {"input-tokens": "256000", "tokens": "1"},
        {"tokens": "200000", "requests": "1"},
    ],
)
def test_sensitivity_verdict_matches_cell_styling(query: dict[str, str] | None) -> None:
    for row in view(query).sensitivity:
        for cell in row.cells:
            assert cell.fits == (cell.verdict in QUALIFIED_VERDICTS), cell.verdict


def test_chart_styles_scale_with_the_baseline_count(client: AppClient, monkeypatch: pytest.MonkeyPatch) -> None:
    extra = tuple(replace(baseline, name=f"{baseline.name} copy") for baseline in API_BASELINES[:2])
    monkeypatch.setattr(economics, "API_BASELINES", API_BASELINES + extra)

    assert [line.series for line in view().cost_plot.lines] == [0, 1, 2, 3, 4, 5]
    response = client.get(PAGE)
    assert response.status_code == 200
    assert "one fixed GKE fleet and 5 managed APIs" in response.text
    assert response.text.count('<polyline points="') == 6


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.5, "1"),
        (2.5, "3"),
        (999.4, "999"),
        (999.6, "1.0k"),
        (1250, "1.3k"),
        (999_949, "999.9k"),
        (999_960, "1.00M"),
        (999_996_000, "1.00B"),
        (5e15, "5000.00T"),
    ],
)
def test_format_number_rolls_units_and_rounds_like_format_decimal(value: float, expected: str) -> None:
    assert format_number(value) == expected


def test_format_number_rounding_agrees_with_format_decimal() -> None:
    for value in (0.5, 1.5, 2.5, 12.5, 999.5):
        assert format_number(value) in {format_decimal(value, 0), "1.0k"}


def test_slider_labels_use_singular_units() -> None:
    frame = view({"days": "1"}).cost_plot.frames[0]
    assert frame.label.startswith("1 request/day · 1 request/month")


def test_page_semantics_have_one_status_and_valid_figures(client: AppClient) -> None:
    html = client.get(PAGE).text
    start = html.index("data-hosting-calculator")
    calculator = html[start : html.index("<script", start)]
    assert "cost-volume" in calculator

    # One persistent status sits outside the region replaced by updates.
    assert html.count('role="status"') == 1
    assert html.index("data-update-status") < html.index("data-hosting-calculator")
    assert "data-update-status" not in calculator
    # Only the slider summary remains a live output; static metrics are plain text.
    assert calculator.count("<output") == 1
    assert 'role="group" aria-label="API monthly cost cards"' in html
    assert "text-base-content/60" not in html
    for figure in re.findall(r"<figure[^>]*>(.*?)</figure>", html, flags=re.DOTALL):
        if "<figcaption" in figure:
            body = figure.strip()
            assert body.startswith("<figcaption") or body.endswith("</figcaption>")
