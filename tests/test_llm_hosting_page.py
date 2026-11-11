"""LLM self-hosting calculator page: rendered forms, sections, and HTML semantics over HTTP."""

import re
from collections.abc import Callable
from dataclasses import replace
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from litestar import Litestar
from litestar.testing import TestClient

import www.sites.calculator as calculator
import www.sites.economics as economics
import www.sites.inputs as hosting_inputs
from tests.llm_hosting_support import view
from www.sites.agent import compare_hosting
from www.sites.calculator import build_llm_self_hosting_view
from www.sites.data import API_BASELINES, DEFAULT_HOSTING_INPUTS, DEMAND_PRESETS, FRONTIER_MODELS, GKE_NODE_POOLS
from www.sites.economics import CLUSTER_HOURLY_USD
from www.sites.formatting import format_usd2
from www.sites.inputs import find_node_pool, hosting_url, scenario_parameters
from www.sites.models import BillingPlan

PAGE = "/sites/llm-self-hosting/?mode=advanced"

type AppClient = TestClient[Any]


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
            (message,) = result.validation
            bounds = f"between {int(item['min']):,} and {int(item['max']):,}; the default was used"
            # Every field is labelled: "Label (key) must be ...".
            assert message.endswith(f"({name}) must be a whole number {bounds}"), name
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
    expected = len(API_BASELINES) + len(extra)

    assert [line.series for line in view().cost_plot.lines] == list(range(expected + 1))
    response = client.get(PAGE)
    assert response.status_code == 200
    assert f"one fixed GKE fleet and {expected} managed APIs" in response.text
    assert response.text.count('<polyline points="') == expected + 1


def test_method_and_sources_render_catalog_prices(client: AppClient) -> None:
    html = client.get(PAGE).text

    fee = format_usd2(CLUSTER_HOURLY_USD)
    assert f"{fee}/hour GKE cluster fee" in html
    assert f"{fee} per cluster-hour management fee" in html
    # The TPU source note names on-demand chip prices; keep it in step with the catalog rates.
    for node in (pool for pool in GKE_NODE_POOLS if pool.chip == "TPU"):
        hourly = node.price(BillingPlan.ON_DEMAND).hourly_usd
        chip_price = f"{node.gpu_count} × {format_usd2(hourly / node.gpu_count)}/chip-hour"  # noqa: RUF001
        assert chip_price in node.operational
        assert f"{node.id}, {chip_price}" in html


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


def api_table(html: str) -> str:
    start = html.index("Monthly costs and break-even at the selected input and output token mix")
    return html[start : html.index("</table>", start)]


def test_blocked_fleets_replace_break_even_capacity_verdicts(client: AppClient) -> None:
    # A100 lacks native FP8 kernels: no break-even exists, and the fleet is not merely too small.
    unsupported = client.get(PAGE, params={"node": "a2-ultra-1g", "quant": "fp8"}).text
    assert "Beyond this fleet" not in unsupported
    assert "Within modeled capacity" not in unsupported
    assert unsupported.count('<dd class="font-semibold">Unsupported configuration</dd>') == len(API_BASELINES)
    assert api_table(unsupported).count("<td>Unsupported configuration</td>") == len(API_BASELINES)

    query = {"input-tokens": "300000", "tokens": "1000"}
    assert view(query).estimate.context_issue
    accepted = sum(not api.request_issue for api in view(query).apis)
    over_context = client.get(PAGE, params=query).text
    assert "Beyond this fleet" not in over_context
    assert api_table(over_context).count("<td>Exceeds model context</td>") == accepted > 0

    # An unconfirmed multi-host fleet needs a pilot in both the cards and the table.
    multi_host = client.get(PAGE, params={"mode": "advanced", "model": "kimi-k3-1-pro"}).text
    assert "Beyond this fleet" not in multi_host
    assert multi_host.count("Capacity needs a multi-host pilot") == 2 * len(API_BASELINES)


def test_shared_url_with_removed_quality_lab_parameters_renders_without_a_message(client: AppClient) -> None:
    legacy = {"quality": "on", "tasks": "250", "review-rate": "60", "quality-0-acceptance": "1e-310"}
    response = client.get(PAGE, params={"requests": "500"} | legacy)
    assert response.status_code == 200
    assert "Some inputs need attention" not in response.text

    def calculator(html: str) -> str:
        # The rest of the document carries a per-response CSP nonce.
        start = html.index("data-hosting-calculator")
        return html[start : html.index("<script", start)]

    assert calculator(response.text) == calculator(client.get(PAGE, params={"requests": "500"}).text)


def test_unknown_billing_text_is_not_reflected_into_the_page(client: AppClient) -> None:
    response = client.get(PAGE, params={"node": "a3-high", "billing": "untrusted-text"})
    assert response.status_code == 200
    assert "Pricing plan (billing) was not recognized; the default was used" in response.text
    assert "untrusted-text" not in response.text


def test_catalog_hides_footprints_of_unsupported_checkpoints(client: AppClient) -> None:
    # Each row is sized on its own machine, so only a recipe limit can block one here.
    html = client.get(PAGE, params={"input-tokens": "250000", "tokens": "1000"}).text
    rows = re.findall(r"<tr>(.*?)</tr>", html[html.index('id="frontier-table"') :], flags=re.DOTALL)
    nemotron = next(row for row in rows if ">Nemotron 3.5 Super VL</a>" in row)  # Recipes stop at 114,688 tokens.
    qwen = next(row for row in rows if ">Qwen3.5 4B</a>" in row)
    assert nemotron.count("<td>—</td>") == 2
    assert " GB</td>" not in nemotron
    assert " GB</td>" in qwen
    assert "<td>—</td>" not in qwen
    # The fleet cell names the row's own machine and precision, not the visitor's selection.
    assert "1 node / 1 GPU" in qwen
    assert f"{find_node_pool('g2-standard-12').name} · 16-bit</span>" in qwen


def test_assumption_copy_renders_the_inputs_and_snapshot(client: AppClient, monkeypatch: pytest.MonkeyPatch) -> None:
    cached = client.get(PAGE, params={"api-mode": "cached"}).text
    assert (
        "Minimum: 512 for Claude Haiku 5.5, Claude Sonnet 5.5, Claude Opus 5.5, Claude Fable 5.2; "
        "1,024 for GPT-6 Luna, GPT-6.1 Terra, GPT-6.1 Sol, GPT-6 Astra; "
        "4,096 for Gemini 3.8 Flash, Gemini 3.5 Flash-Lite, Gemini 4 Argon, Gemini 4 Carbon. "
        "Ineligible requests use standard rates."
    ) in cached
    assert (
        "Assumes no misses within each group: "
        "30-minute minimum retention for GPT-6 Luna, GPT-6.1 Terra, GPT-6.1 Sol, GPT-6 Astra; "
        "best-effort implicit prefix reuse (explicit caching unsupported) for Gemini 4 Argon, Gemini 4 Carbon; "
        "five-minute explicit GenerateContent storage for Gemini 3.8 Flash, Gemini 3.5 Flash-Lite; "
        "five-minute writes for Claude Haiku 5.5, Claude Sonnet 5.5, Claude Opus 5.5, Claude Fable 5.2."
    ) in cached
    monkeypatch.setattr(
        economics,
        "API_BASELINES",
        tuple(replace(row, cache_minimum=2048) if row.name == "GPT-6 Astra" else row for row in API_BASELINES),
    )
    assert "; 2,048 for GPT-6 Astra; " in client.get(PAGE, params={"api-mode": "cached"}).text

    defaults = replace(DEFAULT_HOSTING_INPUTS, tokens_per_second=250, target_utilization=80, memory_overhead_pct=10)
    monkeypatch.setattr(hosting_inputs, "DEFAULT_HOSTING_INPUTS", defaults)
    simple = client.get("/sites/llm-self-hosting/").text
    assert "Assumes 250 generated tokens/s per model copy, with 80% usable." in simple
    assert "GB weights + 10% reserve = " in simple


def test_monthly_hours_come_from_the_server_constant(client: AppClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # Only the view's copy changes here; a literal 730 left in a template would keep its text.
    monkeypatch.setattr(calculator, "MONTHLY_HOURS", 700.0)
    query = {"preset": "document-pipeline", "billing": "cud-1y"}
    hourly = build_llm_self_hosting_view(query).selected_price.hourly_usd
    simple = client.get("/sites/llm-self-hosting/", params=query).text
    assert f"{format_usd2(hourly * 700)}/node/month, even while idle" in simple
    # Thirty 8-hour days fill about a third of the month: 240 h of 730 becomes 230.1 h of 700.
    assert "8 h per active day, 230.1 h/month" in simple
    assert "Your commitment still bills 700 hours/month" in simple
    assert "Commitments bill 700 hours/month" in simple
    assert "100% = 700 h/month" in client.get(PAGE).text


# Simple-mode choices, section order, and fixed-fleet explanations.


def test_simple_mode_has_basic_choices_and_a_clean_shareable_url(client: AppClient) -> None:
    result = build_llm_self_hosting_view(
        {"preset": "department", "model": "nemotron-3-5-super-vl", "billing": "cud-3y"}
    )
    assert result.inputs.mode == "simple"
    assert result.inputs.quantization_id == "nvfp4"
    assert result.inputs.node_pool_id == "g4-standard-48"
    assert result.inputs.memory_overhead_pct == 25
    assert result.estimate.requests_month == 220000
    assert not result.validation
    parameters = parse_qs(urlsplit(hosting_url(result.inputs)).query)
    assert set(parameters) == {"mode", "preset", "model", "billing", "window"}
    assert build_llm_self_hosting_view(parameters).inputs == result.inputs
    html = client.get("/sites/llm-self-hosting/").text
    for name in ("preset", "model", "billing", "window", "advanced-mode"):
        assert f'id="{name}"' in html
    for name in ("platform", "quant", "node", "throughput", "latency-settings", "cost-volume"):
        assert f'id="{name}"' not in html


def test_presets_and_models_are_presented_from_smallest_to_largest(client: AppClient) -> None:
    assert [preset.id for preset in DEMAND_PRESETS] == [
        "small-team",
        "document-pipeline",
        "department",
        "service",
    ]
    assert [model.parameters_b for model in FRONTIER_MODELS] == sorted(model.parameters_b for model in FRONTIER_MODELS)
    html = client.get("/sites/llm-self-hosting/").text
    preset_positions = [html.index(f'value="{preset.id}"') for preset in DEMAND_PRESETS]
    model_positions = [html.index(f'value="{model.id}"') for model in FRONTIER_MODELS]
    assert preset_positions == sorted(preset_positions)
    assert model_positions == sorted(model_positions)
    assert "22,000 calls/month" in html
    assert "= 5 calls/day for 200 employees" in html
    assert "1,000, 10,000, or 100,000" in html
    # Simple mode explains sizes in the picker, including mixture-of-experts active parameters.
    assert '<option value="qwen3-5-4b">Qwen3.5 4B · 4B</option>' in html
    assert '<option value="nemotron-3-5-super-vl">Nemotron 3.5 Super VL · 120B / 12B active</option>' in html
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
        # The quality lab was removed, along with its link in the page navigation.
        assert "quality-lab" not in html
        assert 'name="tasks"' not in html


def test_simple_outputs_explain_load_cost_and_fixed_fleet_break_even(client: AppClient) -> None:
    # Gemma 4 runs on both GPUs and Cloud TPU, so both comparison cards price a fleet.
    scenario = {"model": "gemma-4-26b-a4b", "preset": "document-pipeline", "window": "1"}
    result = build_llm_self_hosting_view(scenario)
    for row in result.apis:
        assert row.break_even_fits == (row.break_even_requests <= result.estimate.capacity_requests_month)
    html = client.get("/sites/llm-self-hosting/", params=scenario).text
    assert "Try a scenario" not in html
    assert "Compare costs" not in html
    for text in (
        "3 replicas",
        "Illustrative setup",
        "GPU vs. Cloud TPU · this demand",
        "CT6e · 8\u00d7 TPU v6e · 256 GB",
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


def test_simple_mode_explains_a_checkpoint_fallback(client: AppClient) -> None:
    simple = "/sites/llm-self-hosting/"
    html = client.get(simple, params={"model": "mistral-large-4"}).text
    assert "runs the default NVFP4 checkpoint, so this estimate uses FP8." in html
    committed = client.get(simple, params={"model": "mistral-large-4", "billing": "cud-1y"}).text
    assert "No machine on this pricing plan" not in committed
    # One whole copy covers half to twice the assumed speed, so the range collapses to one budget.
    assert "the same setup would still cost" in html


def test_setup_notes_come_from_the_selected_checkpoint_and_machine(client: AppClient) -> None:
    html = client.get("/sites/llm-self-hosting/", params={"model": "nemotron-3-5-super-vl"}).text
    assert "The economical NVFP4 checkpoint needs quality testing." in html
    assert "The verified recipe caps this setup at 16,384 context tokens" in html
    # No NVFP4 note or context cap for the default BF16 model on G4.
    default = client.get("/sites/llm-self-hosting/").text
    assert "needs quality testing" not in default
    assert "The verified recipe caps this setup" not in default


def test_simple_form_offers_the_workload_default_plan_and_names_batch_pricing(client: AppClient) -> None:
    team = client.get("/sites/llm-self-hosting/").text
    assert '<option value="auto" selected>Workload default · on-demand</option>' in team
    assert '<option value="flex"' not in team
    assert "Standard text rates, ordered by price." in team
    assert "Other plans for this workload:" in team
    pipeline = client.get("/sites/llm-self-hosting/?mode=simple&preset=document-pipeline").text
    assert '<option value="auto" selected>Workload default · Flex-start or on-demand</option>' in pipeline
    assert '<option value="flex">Flex-start · queued batch jobs only</option>' in pipeline
    assert "Batch rates, half the standard price for asynchronous jobs, ordered by price." in pipeline
    assert "queues each start and runs nodes for at most seven days" in pipeline
    assert 'data-plan="Flex-start or on-demand"' in pipeline
    # An explicit plan stays selected instead of the workload default.
    explicit = client.get("/sites/llm-self-hosting/?mode=simple&preset=document-pipeline&billing=flex").text
    assert '<option value="auto">Workload default' in explicit
    assert '<option value="flex" selected>' in explicit
    # Advanced mode offers Flex-start on every machine that publishes the rate, and never the automatic plan.
    advanced = client.get(PAGE + "&node=g4-standard-48").text
    assert '<option value="flex">Flex-start · queued batch jobs only</option>' in advanced
    assert ">Workload default ·" not in advanced
    assert '<option value="flex"' not in client.get(PAGE + "&node=g2-standard-12").text
