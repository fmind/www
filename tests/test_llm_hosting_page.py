"""LLM self-hosting calculator page: rendered forms, sections, and HTML semantics over HTTP."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import replace
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from litestar import Litestar
from litestar.testing import TestClient

import www.sites.economics as economics
from tests.llm_hosting_support import view
from www.sites.agent import compare_hosting
from www.sites.calculator import build_llm_self_hosting_view
from www.sites.data import API_BASELINES, DEMAND_PRESETS, FRONTIER_MODELS
from www.sites.inputs import hosting_url, scenario_parameters

PAGE = "/sites/llm-self-hosting/?mode=advanced"

type AppClient = TestClient[Any]


@pytest.fixture(scope="module")
def client(make_app: Callable[[], Litestar]) -> Iterator[AppClient]:
    # One app per module: the MCP session manager inside an instance can only start once per process.
    with TestClient(make_app()) as test_client:
        yield test_client


# Advanced form fidelity, API availability, and page semantics.


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


def test_chart_styles_scale_with_the_baseline_count(client: AppClient, monkeypatch: pytest.MonkeyPatch) -> None:
    extra = tuple(replace(baseline, name=f"{baseline.name} copy") for baseline in API_BASELINES[:2])
    monkeypatch.setattr(economics, "API_BASELINES", API_BASELINES + extra)

    assert [line.series for line in view().cost_plot.lines] == list(range(8))
    response = client.get(PAGE)
    assert response.status_code == 200
    assert "one fixed GKE fleet and 7 managed APIs" in response.text
    assert response.text.count('<polyline points="') == 8


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


def test_page_links_only_to_rendered_sections_and_states_editable_assumptions(client: AppClient) -> None:
    incompatible = client.get(f"{PAGE}&node=a2-ultra-1g&quant=fp8").text
    assert 'id="cost-explorer"' not in incompatible
    assert 'href="#cost-explorer"' not in incompatible
    compatible = client.get(PAGE).text
    assert 'id="cost-explorer"' in compatible
    assert 'href="#cost-explorer"' in compatible
    custom = client.get(f"{PAGE}&overhead=0&throughput=250&utilization=80").text
    assert "Model weights plus 0% reserve" in custom
    assert "Capacity assumes 250 output tokens/s per model copy, with 80% usable" in custom


# Simple-mode choices, section order, and fixed-fleet explanations.


def test_simple_mode_has_basic_choices_and_a_clean_shareable_url(client: AppClient) -> None:
    result = build_llm_self_hosting_view({"preset": "department", "model": "mistral-small-4", "billing": "cud-3y"})
    assert result.inputs.mode == "simple"
    assert result.inputs.quantization_id == "nvfp4"
    assert result.inputs.node_pool_id == "g4-standard-48"
    assert result.inputs.memory_overhead_pct == 25
    assert result.estimate.requests_month == 44000
    assert not result.validation
    parameters = parse_qs(urlsplit(hosting_url(result.inputs)).query)
    assert set(parameters) == {"mode", "preset", "model", "billing", "window"}
    assert build_llm_self_hosting_view(parameters).inputs == result.inputs
    html = client.get("/sites/llm-self-hosting/").text
    for name in ("preset", "model", "billing", "window", "advanced-mode"):
        assert f'id="{name}"' in html
    for name in ("platform", "quant", "node", "throughput", "quality-settings", "cost-volume"):
        assert f'id="{name}"' not in html


def test_presets_and_models_are_presented_from_smallest_to_largest(client: AppClient) -> None:
    assert [preset.id for preset in DEMAND_PRESETS] == [
        "single-job",
        "small-team",
        "document-pipeline",
        "department",
        "automated-support",
        "scheduled-workflow",
        "service",
    ]
    assert [model.parameters_b for model in FRONTIER_MODELS] == sorted(model.parameters_b for model in FRONTIER_MODELS)
    html = client.get("/sites/llm-self-hosting/").text
    preset_positions = [html.index(f'value="{preset.id}"') for preset in DEMAND_PRESETS]
    model_positions = [html.index(f'value="{model.id}"') for model in FRONTIER_MODELS]
    assert preset_positions == sorted(preset_positions)
    assert model_positions == sorted(model_positions)
    assert "3,520 calls/month" in html
    # Simple mode explains sizes in the picker, including mixture-of-experts active parameters.
    assert '<option value="qwen3-5-4b">Qwen3.5 4B · 4B</option>' in html
    assert '<option value="mistral-small-4">Mistral Small 4 · 119B / 6.5B active</option>' in html
    assert "B = billion, T = trillion" in html


@pytest.mark.parametrize("mode", ["simple", "advanced"])
def test_hosting_page_keeps_every_section_open_with_setup_before_method(client: AppClient, mode: str) -> None:
    html = client.get(f"/sites/llm-self-hosting/?mode={mode}").text
    assert "<details" not in html
    assert "<summary" not in html
    method = html.index('id="hosting-method-title"')
    assert method < html.index('id="hosting-sources-title"')
    if mode == "simple":
        assert html.index('id="hosting-break-even-title"') < html.index('id="recommended-fleet-title"') < method
    else:
        assert 'id="recommended-fleet"' not in html
        assert 'id="latency-settings"' in html
        assert 'id="quality-settings"' in html


def test_simple_outputs_explain_load_cost_and_fixed_fleet_break_even(client: AppClient) -> None:
    result = build_llm_self_hosting_view({"preset": "scheduled-workflow", "window": "1"})
    for row in result.apis:
        assert row.break_even_fits == (row.break_even_requests <= result.estimate.capacity_requests_month)
    html = client.get("/sites/llm-self-hosting/", params={"preset": "scheduled-workflow", "window": "1"}).text
    assert "Try a scenario" not in html
    assert "Compare costs" not in html
    for text in (
        "17 replicas",
        "Illustrative setup",
        "not measured GPU utilization",
        "Break-even holds this setup",
        "Scheduled workload",
        "Output budgets include reasoning",
        "Exact estimate",
    ):
        assert text in html


def test_auto_flex_start_returns_validation_without_crashing_the_web_page(make_app: Callable[[], Litestar]) -> None:
    parameters = {"mode": "advanced", "node": "auto", "billing": "flex"}
    result = build_llm_self_hosting_view(parameters)
    assert result.validation
    # Its own app, so a server exception would surface as the 500 response this page must avoid.
    with TestClient(make_app(), raise_server_exceptions=False) as client:
        response = client.get("/sites/llm-self-hosting/", params=parameters)
        assert response.status_code == 200
        assert "No compatible hardware" in response.text
    with pytest.raises(ValueError, match="Invalid calculator parameters"):
        compare_hosting(parameters)
