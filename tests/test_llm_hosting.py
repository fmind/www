"""LLM self-hosting calculator: input parsing, formulas, view models, and formatting, tested without HTTP."""

from dataclasses import replace
from datetime import UTC, datetime
from math import isclose, isfinite, isnan
from urllib.parse import parse_qs, urlparse, urlsplit

import pytest

import www.sites.economics as economics
from tests.llm_hosting_support import NOW, view
from www.sites.agent import compare_hosting
from www.sites.calculator import build_llm_self_hosting_view
from www.sites.capacity import replicas_for_demand
from www.sites.data import (
    API_BASELINES,
    DEFAULT_HOSTING_INPUTS,
    DEMAND_PRESETS,
    FRONTIER_MODELS,
    GKE_NODE_POOLS,
    QUANTIZATIONS,
)
from www.sites.economics import api_monthly_cost, current_api_baselines, estimate_hosting
from www.sites.formatting import (
    format_budget,
    format_count,
    format_decimal,
    format_number,
    format_usd,
    format_usd2,
    hosting_decision_copy,
    hosting_decision_title,
    task_cost_max,
)
from www.sites.inputs import configuration_issue, hosting_url
from www.sites.models import BillingPlan

# Fleet sizing, billing plans, demand presets, and input validation.


def test_estimate_uses_whole_nodes_and_compute_plus_cluster_cost() -> None:
    model = next(model for model in FRONTIER_MODELS if model.id == "qwen3-8-27b")
    node = next(node for node in GKE_NODE_POOLS if node.id == "a2-ultra-1g")
    quantization = next(item for item in QUANTIZATIONS if item.id == "fp16")
    inputs = replace(
        DEFAULT_HOSTING_INPUTS,
        replicas=2,
        duty_cycle_percent=50,
        memory_overhead_pct=25,
        tokens_per_second=10,
        target_utilization=50,
        output_tokens_request=1000,
    )

    estimate = estimate_hosting(model, node, quantization, inputs)

    assert estimate.required_memory_gb == pytest.approx(55.562855904 * 1.25)
    assert estimate.nodes_per_replica == 1
    assert estimate.total_nodes == 2
    assert estimate.total_gpus == 2
    assert estimate.total_monthly_usd == pytest.approx(
        2 * node.price(inputs.billing_plan).hourly_usd * 730 * 0.5 + 0.1 * 730,
    )
    assert estimate.capacity_tokens_month == 10 * 2 * 0.5 * 730 * 60 * 60 * 0.5


def test_invalid_required_query_values_fall_back_independently() -> None:
    result = view({"model": "unknown", "replicas": "0", "throughput": "NaN"})

    assert result.inputs.model_id == DEFAULT_HOSTING_INPUTS.model_id
    assert result.inputs.replicas == DEFAULT_HOSTING_INPUTS.replicas
    assert result.inputs.tokens_per_second == DEFAULT_HOSTING_INPUTS.tokens_per_second
    assert result.validation == (
        "Model (model) was not recognized; the default was used",
        "Serving replicas (replicas) must be a whole number between 1 and 100,000; the default was used",
        "Assumed output tokens/s per replica (throughput) must be between 0.1 and 1,000,000; the default was used",
    )


@pytest.mark.parametrize("preset", DEMAND_PRESETS, ids=lambda preset: preset.id)
def test_demand_presets_preserve_fleet_and_replace_demand(preset) -> None:
    result = view(
        {
            "preset": preset.id,
            "replicas": "3",
            "quant": "fp16",
            "requests": "999",
        },
    )

    assert result.inputs.replicas == 3
    assert result.inputs.quantization_id == "fp16"
    assert result.estimate.requests_month == preset.requests_per_day * preset.active_days
    assert result.inputs.input_tokens_request == preset.input_tokens
    assert result.inputs.output_tokens_request == preset.output_tokens
    assert result.demand_label == preset.name


def test_manual_demand_remains_custom() -> None:
    result = view({"requests": "7", "days": "2"})

    assert result.demand_label == "Custom demand"
    assert result.estimate.requests_month == 14


def test_api_baselines_charge_both_token_directions_at_actual_demand() -> None:
    result = view({"preset": "small-team"})

    assert [row.monthly_usd for row in result.apis] == pytest.approx([13.2, 35.2, 176, 1.76, 70.4])
    assert result.estimate.demand_fits
    assert result.estimate.output_tokens_month == 2_112_000
    assert result.estimate.input_tokens_month == 7_040_000

    job = view({"preset": "single-job"})
    assert job.apis[0].monthly_usd == pytest.approx(0.675)
    assert job.estimate.total_monthly_usd == result.estimate.total_monthly_usd


@pytest.mark.parametrize("node_id", ["a4-cud-3y", "a2-ultra-1g"])
def test_commitment_charges_idle_time_while_on_demand_can_stop(node_id: str) -> None:
    full = view({"node": node_id})
    partial = view({"node": node_id, "duty": "25"})
    expected_compute = (
        full.estimate.compute_monthly_usd if full.selected_price.committed else full.estimate.compute_monthly_usd / 4
    )

    assert partial.estimate.compute_monthly_usd == expected_compute
    assert partial.estimate.capacity_tokens_month == full.estimate.capacity_tokens_month / 4
    assert partial.estimate.control_monthly_usd == full.estimate.control_monthly_usd


def test_capacity_shortfall_and_unreachable_break_even() -> None:
    overloaded = view({"preset": "service", "throughput": "0.1"})
    assert not overloaded.estimate.demand_fits
    assert overloaded.estimate.demand_capacity_pct > 100
    assert all(not row.break_even_fits for row in overloaded.apis)

    fast = view({"preset": "service", "throughput": "10000"})
    assert fast.estimate.demand_fits
    assert fast.apis[0].break_even_fits
    assert fast.estimate.total_monthly_usd == overloaded.estimate.total_monthly_usd
    assert fast.apis[0].monthly_usd == overloaded.apis[0].monthly_usd

    row = fast.apis[0]
    price = row.per_thousand_requests_usd / 1000
    assert row.break_even_requests * price >= fast.estimate.total_monthly_usd
    assert (row.break_even_requests - 1) * price < fast.estimate.total_monthly_usd


def test_astra_long_context_pricing_boundary_is_provider_specific() -> None:
    short = view({"input-tokens": "272000"})
    long = view({"input-tokens": "272001"})

    assert (short.apis[2].baseline.input_per_million, short.apis[2].baseline.output_per_million) == (
        10,
        50,
    )
    assert (long.apis[2].baseline.input_per_million, long.apis[2].baseline.output_per_million) == (
        20,
        75,
    )
    assert long.apis[0].baseline.input_per_million == short.apis[0].baseline.input_per_million


@pytest.mark.parametrize("key", ["requests", "days", "input-tokens", "tokens", "duty"])
@pytest.mark.parametrize("invalid", ["0", "-1", "NaN", "+Inf", "1e99", "oops"])
def test_demand_input_validation(key: str, invalid: str) -> None:
    result = view({key: invalid})

    assert len(result.validation) == 1
    assert result.inputs == DEFAULT_HOSTING_INPUTS


def test_unknown_preset_keeps_validated_manual_demand() -> None:
    result = view({"preset": "missing", "requests": "7"})

    assert result.validation == ("Workload (preset) was not recognized; the validated demand inputs were kept",)
    assert result.inputs.requests_per_day == 7


def test_checkpoint_precision_changes_memory_and_whole_nodes_determine_cost() -> None:
    small = view()
    by_format = {row.quantization.id: row.estimate for row in small.precisions}
    assert by_format["fp8"].weight_memory_gb == pytest.approx(30.866866928)
    assert by_format["fp16"].weight_memory_gb == pytest.approx(55.562855904)
    assert by_format["fp8"].total_monthly_usd == by_format["fp16"].total_monthly_usd
    large = view({"model": "nemotron-3-5-super-vl", "node": "g4-standard-48", "quant": "nvfp4"})
    by_format = {row.quantization.id: row.estimate for row in large.precisions}
    assert by_format["nvfp4"].total_gpus < by_format["fp16"].total_gpus
    assert by_format["nvfp4"].total_monthly_usd < by_format["fp16"].total_monthly_usd


def test_view_compares_all_catalog_models_in_deterministic_order() -> None:
    result = view({"model": "qwen3-8-27b", "node": "a2-ultra-1g"})
    assert len(result.models) == len(result.comparison) == 12
    assert tuple(row.model for row in result.comparison) == FRONTIER_MODELS
    assert result.estimate.nodes_per_replica == 1
    assert len(API_BASELINES) == 5
    assert isclose(result.estimate.weight_memory_gb, 55.562855904)


def test_query_mapping_uses_first_repeated_value_like_go_url_values() -> None:
    result = build_llm_self_hosting_view({"replicas": ["2", "8"]}, now=NOW)

    assert result.inputs.replicas == 2


def test_current_api_baselines_returns_immutable_date_adjusted_snapshots() -> None:
    adjusted = current_api_baselines(datetime(2027, 1, 1, tzinfo=UTC), DEFAULT_HOSTING_INPUTS)

    assert adjusted[0].input_per_million == API_BASELINES[0].input_per_million * 2
    assert API_BASELINES[0].input_per_million == 0.75


def test_template_decision_helpers_preserve_capacity_before_cost() -> None:
    overloaded = view({"preset": "service", "throughput": "0.1"})
    api_first = view()
    hosting_candidate = view(
        {
            "requests": "1000000",
            "days": "30",
            "input-tokens": "1000",
            "tokens": "300",
            "throughput": "10000",
            "window": "24",
        }
    )

    assert hosting_decision_title(overloaded) == "This fleet cannot cover the modeled demand"
    assert "monthly average cannot establish peak-time capacity" in hosting_decision_copy(overloaded)
    assert hosting_decision_title(api_first) == "Start with an API on cost grounds"
    assert "Claude Haiku 5.5" in hosting_decision_copy(api_first)
    assert hosting_decision_title(hosting_candidate) == "Self-hosting has a cost case to test"


def test_template_quantity_and_task_scale_helpers() -> None:
    result = view()

    assert format_count(1, "node") == "1 node"
    assert format_count(2, "GPU") == "2 GPUs"
    assert task_cost_max(result.tasks) == max(row.per_accepted_usd for row in result.tasks if row.fits)


@pytest.mark.parametrize("node", GKE_NODE_POOLS, ids=lambda node: node.id)
def test_every_published_billing_plan_charges_whole_nodes_and_keeps_idle_commitments(node) -> None:
    # The default model has no TPU recipe; Gemma 4 is verified on both Cloud TPU families.
    model = {"model": "gemma-4-26b-a4b"} if "TPU" in node.gpu else {}
    for price in node.prices:
        full = view(model | {"node": node.id, "billing": price.plan.value, "replicas": "2"})
        partial = view(model | {"node": node.id, "billing": price.plan.value, "replicas": "2", "duty": "25"})
        assert bool(full.validation) == (node.id == "g2-standard-12" or price.plan.value == "flex")
        assert full.selected_price == price
        assert full.estimate.compute_monthly_usd == pytest.approx(full.estimate.total_nodes * price.hourly_usd * 730)
        assert partial.estimate.compute_monthly_usd == pytest.approx(
            full.estimate.compute_monthly_usd * (1 if price.committed else 0.25),
        )
        assert partial.estimate.capacity_tokens_month == full.estimate.capacity_tokens_month / 4
        assert partial.estimate.total_monthly_usd == pytest.approx(
            partial.estimate.compute_monthly_usd + 73,
        )


@pytest.mark.parametrize(
    ("node", "hourly", "one_year", "three_year", "vram"),
    [
        ("g2-standard-12", 1.000416348, 0.630262303, 0.450187356, 24),
        ("g4-standard-48", 4.49993, 3.105, 1.97945, 96),
    ],
)
def test_small_gpu_prices_use_resource_cuds_and_gpu_memory(node, hourly, one_year, three_year, vram) -> None:
    for plan, rate in (("on-demand", hourly), ("cud-1y", one_year), ("cud-3y", three_year)):
        result = view({"node": node, "billing": plan, "quant": "fp4"})
        assert result.selected_node.vram_gb == vram
        assert result.estimate.compute_monthly_usd == pytest.approx(rate * 730 * result.estimate.total_nodes)


@pytest.mark.parametrize(("node", "billing"), [("a4", "on-demand"), ("g2-standard-12", "flex"), ("a3-high", "unknown")])
def test_unsupported_billing_is_visible_and_uses_a_published_rate(node: str, billing: str) -> None:
    result = view({"node": node, "billing": billing})
    assert "billing" in result.validation[0]
    assert result.selected_price in result.selected_node.prices


def test_unsupported_billing_falls_back_to_a_plan_the_scenario_can_use() -> None:
    # A4 lists Flex-start first, but interactive serving rejects it.
    result = view({"model": "glm-5-3", "node": "a4", "billing": "on-demand"})
    assert result.selected_price.label == "1-year resource CUD"
    assert result.validation == (
        f"{result.selected_node.name} does not offer the on-demand billing plan; 1-year resource CUD was used",
    )


def test_unpublished_rate_is_rejected_by_calculation_boundary() -> None:
    from www.sites.models import BillingPlan

    node = next(node for node in GKE_NODE_POOLS if node.id == "a4")
    with pytest.raises(ValueError, match="does not offer on-demand"):
        node.price(BillingPlan.ON_DEMAND)


@pytest.mark.parametrize(("legacy", "billing"), [("a4-cud-3y", "cud-3y"), ("a4-flex", "flex")])
def test_old_a4_links_preserve_their_billing_plan(legacy: str, billing: str) -> None:
    result = view({"node": legacy})
    assert bool(result.validation) == (billing == "flex")
    assert result.inputs.node_pool_id == "a4"
    assert result.inputs.billing_plan.value == billing
    overridden = view({"node": legacy, "billing": "cud-1y"})
    assert overridden.inputs.billing_plan.value == "cud-1y"


@pytest.mark.parametrize("model", FRONTIER_MODELS, ids=lambda model: model.id)
def test_automatic_setup_uses_native_checkpoint_and_a_compatible_topology(model) -> None:
    result = build_llm_self_hosting_view({"model": model.id}, now=NOW)
    assert result.inputs.mode == "simple"
    # The default checkpoint is kept unless no machine with an on-demand rate can serve it.
    default_served = any(
        not configuration_issue(
            replace(result.inputs, quantization_id=model.default_quantization, node_pool_id=node.id)
        )
        for node in GKE_NODE_POOLS
        if any(price.plan is BillingPlan.ON_DEMAND for price in node.prices)
    )
    assert (result.selected_quant.id == model.default_quantization) == default_served
    assert result.selected_quant.id in model.supported_quantizations
    assert not result.validation
    assert not result.estimate.compatibility_issue
    assert result.selected_node.vram_gb * result.estimate.nodes_per_replica >= result.estimate.required_memory_gb
    assert result.estimate.nodes_per_replica == 1 or result.selected_node.multi_host


# API delivery modes, price freshness, scenario links, cost charts, and formatting.


def test_api_modes_include_warmup_and_storage() -> None:
    batch = view({"api-mode": "batch"})
    assert [row.monthly_usd for row in batch.apis] == pytest.approx([6.6, 17.6, 88, 0.88, 35.2])

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
        [0.07237466666666667, 0.1941824, 1.009824, 0.01009824, 0.3883648],
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
    assert len(result.cost_plot.break_evens) == 5

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
        assert f"{format_number(daily)} {'request' if daily == 1 else 'requests'}/day" in frame.label
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
    result = view({"node": "a2-ultra-1g"})

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
        "API pricing mode (api-mode) was not recognized; the default was used",
        "Calls per cache group (cache-requests) must be a whole number between 1 and 1,000,000; the default was used",
        "quality was not recognized; the default was used",
        "Measured p95 first token (measured-first) must be between 0 and 3,600; the default was used",
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


@pytest.mark.parametrize("acceptance", ["1e-8", "1e-304", "1e-310", "1e-1000"])
def test_tiny_acceptance_is_rejected_before_cost_arithmetic(acceptance: str) -> None:
    result = view({"quality": "on", "quality-0-acceptance": acceptance})

    assert result.validation == ("quality-0-acceptance must be zero or at least 0.0000001; the default was used",)
    assert result.inputs.quality[0].acceptance_percent == DEFAULT_HOSTING_INPUTS.quality[0].acceptance_percent
    assert all(isfinite(task.per_accepted_usd) for task in result.tasks)


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


# Fractional quantities, API availability, sensitivity verdicts, and number rounding.


QUALIFIED_VERDICTS = {"Fleet has a cost case", "API costs less", "No API accepts this request"}


@pytest.mark.parametrize("parameter", ["days", "tokens", "input-tokens", "cache-prefix", "tasks"])
def test_whole_quantities_reject_fractions_for_agents(parameter: str) -> None:
    assert view({parameter: "21"}).validation == ()
    with pytest.raises(ValueError, match=rf"\({parameter}\) must be a whole number"):
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


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (9.994, "$9.99"),
        (999.4, "$999"),
        (1250, "$1.3k"),
        (999_949, "$999.9k"),
        (999_960, "$1.0M"),
        (15_972_606.15, "$16.0M"),
        (52_104_000, "$52.1M"),
        (999_960_000, "$1.0B"),
        (12_400_000_000, "$12.4B"),
    ],
)
def test_format_budget_rolls_into_millions_and_billions(value: float, expected: str) -> None:
    assert format_budget(value) == expected


def test_format_number_rounding_agrees_with_format_decimal() -> None:
    for value in (0.5, 1.5, 2.5, 12.5, 999.5):
        assert format_number(value) in {format_decimal(value, 0), "1.0k"}


def test_slider_labels_use_singular_units() -> None:
    frame = view({"days": "1"}).cost_plot.frames[0]
    assert frame.label.startswith("1 request/day · 1 request/month")


# Context limits, multi-host topology, and pilot evidence binding.


def pilot():
    return view(
        {
            "measured-first": "1",
            "measured-complete": "5",
            "measured-concurrency": "8",
            "confirm-pilot": view().current_pilot_config,
        }
    )


def test_context_budget_is_retained_but_cannot_produce_a_hosting_verdict() -> None:
    result = view({"input-tokens": "262144", "tokens": "1"})
    assert result.inputs.input_tokens_request == 262144
    assert result.estimate.context_issue
    assert not result.estimate.qualified
    assert result.estimate.context_issue in result.validation
    assert "context" in hosting_decision_title(result).lower()
    assert all(not cell.fits for row in result.sensitivity for cell in row.cells)
    assert not result.tasks[0].fits
    assert result.tasks[0].request_issue


def test_context_limit_is_inclusive_of_input_and_output() -> None:
    assert view({"input-tokens": "261144", "tokens": "1000"}).estimate.qualified
    assert not view({"input-tokens": "261144", "tokens": "1001"}).estimate.qualified


def test_l4_memory_spanning_hosts_requires_a_configuration_pilot() -> None:
    result = view({"node": "g2-standard-12"})
    assert result.estimate.nodes_per_replica == 3
    assert not result.estimate.topology_confirmed
    assert not result.estimate.qualified
    assert "not supported" in hosting_decision_title(result).lower()
    assert not result.comparison_ready
    assert not result.tasks[0].fits
    assert all(not cell.fits for row in result.sensitivity for cell in row.cells)
    confirmed = view(
        {
            "node": "g2-standard-12",
            "confirm-pilot": result.current_pilot_config,
            "measured-first": "1",
            "measured-complete": "5",
            "measured-concurrency": "8",
        }
    )
    assert not confirmed.estimate.topology_confirmed
    assert not confirmed.estimate.qualified
    assert confirmed.estimate.compatibility_issue
    assert not view({"node": "g2-standard-12", "quant": "fp4"}).estimate.qualified


def test_partial_multi_host_pilot_cannot_qualify_the_configuration() -> None:
    unproved = view({"node": "g2-standard-12"})
    partial = view(
        {
            "node": "g2-standard-12",
            "confirm-pilot": unproved.current_pilot_config,
            "measured-first": "1",
        }
    )
    assert partial.inputs.pilot_config == partial.current_pilot_config
    assert not partial.estimate.topology_confirmed
    assert not partial.estimate.qualified
    assert "unproved" in partial.latency_title


@pytest.mark.parametrize("model", ["qwen3-8-27b", "kimi-k3"])
def test_mcp_comparisons_cannot_borrow_another_configuration_pilot(model: str) -> None:
    parameters = {
        "model": model,
        "node": "a3-ultra",
        "quant": "mxfp4" if model == "kimi-k3" else "fp16",
        "requests": "1",
    }
    baseline = compare_hosting(parameters)
    result = compare_hosting(
        {
            **parameters,
            "confirm-pilot": baseline.pilot_configuration,
            "measured-first": "1",
            "measured-complete": "5",
            "measured-concurrency": str(baseline.inputs.concurrency),
        }
    )
    assert not result.validation
    assert result.estimate.topology_confirmed
    for row in result.model_comparisons:
        if row.estimate.nodes_per_replica > 1:
            assert row.estimate.topology_confirmed == (row.model.id == model)
            if row.model.id != model:
                assert not row.estimate.qualified
    for precision in result.precision_comparisons:
        if precision.estimate.nodes_per_replica > 1:
            assert precision.estimate.topology_confirmed == (precision.quantization.id == result.inputs.quantization_id)
            if precision.quantization.id != result.inputs.quantization_id:
                assert not precision.estimate.qualified


def test_task_profile_capacity_is_independent_from_top_level_demand() -> None:
    result = view({"requests": "10000000"})
    assert not result.estimate.demand_fits
    assert result.tasks[0].fits


@pytest.mark.parametrize("tokens", ["128001", "1000000"])
def test_api_output_limits_disable_unavailable_comparisons(tokens: str) -> None:
    result = view({"tokens": tokens})
    assert all(api.request_issue for api in result.apis)
    assert all(task.request_issue for task in result.tasks[1:])
    assert not result.comparison_ready


def test_api_limits_enforce_combined_context_windows() -> None:
    over_limit = view({"input-tokens": "1000000", "tokens": "60000"})
    assert not over_limit.apis[0].request_issue  # Gemini publishes separate input/output limits.
    assert all(api.request_issue for api in over_limit.apis[1:])

    gemini_limit = view({"input-tokens": "983040", "tokens": "65536"})
    assert not gemini_limit.apis[0].request_issue
    assert gemini_limit.apis[1].request_issue
    assert gemini_limit.apis[2].request_issue == "Input exceeds the 922,000-token limit"

    # Astra caps input at 922,000 tokens inside its 1,050,000-token context window.
    astra_limit = view({"input-tokens": "922000", "tokens": "128000"})
    assert not astra_limit.apis[2].request_issue
    astra_over = view({"input-tokens": "922001", "tokens": "1000"})
    assert astra_over.apis[2].request_issue == "Input exceeds the 922,000-token limit"


def test_pilot_confirmation_survives_a_shared_url() -> None:
    result = pilot()
    assert "meets your latency targets" in result.latency_title
    assert result.inputs.pilot_config == result.current_pilot_config
    shared = view(parse_qs(urlsplit(hosting_url(result.inputs)).query))
    assert shared.inputs == result.inputs
    assert shared.latency_title == result.latency_title
    assert not shared.validation


def test_precision_alternative_clears_pilot_when_automatic_hardware_changes() -> None:
    parameters = {"model": "qwen3-8-27b", "quant": "fp16", "node": "a3-ultra"}
    measured = view(
        parameters
        | {
            "measured-first": "1",
            "measured-complete": "5",
            "measured-concurrency": "8",
            "confirm-pilot": view(parameters).current_pilot_config,
        }
    )
    assert measured.inputs.pilot_config
    alternative = next(row for row in measured.precisions if row.quantization.id == "fp16")
    assert alternative.node.id == "g4-standard-48"
    shared = view(parse_qs(urlsplit(alternative.url).query))
    assert not shared.validation
    assert shared.estimate == alternative.estimate
    assert shared.inputs.measured_first_token == 0
    assert shared.inputs.measured_completion == 0
    assert shared.inputs.measured_concurrency == 0
    assert not shared.inputs.pilot_config


@pytest.mark.parametrize(
    "change",
    [
        {"model": "kimi-k3"},
        {"node": "a2-ultra-1g"},
        {"quant": "fp4"},
        {"input-tokens": "4000"},
        {"tokens": "1000"},
        {"replicas": "2"},
        {"throughput": "500"},
        {"overhead": "35"},
        {"concurrency": "16"},
    ],
)
def test_configuration_changes_invalidate_a_previous_pilot(change: dict[str, str]) -> None:
    query = parse_qs(urlsplit(hosting_url(pilot().inputs)).query)
    query.update({key: [value] for key, value in change.items()})
    result = view(query)
    assert result.inputs.measured_first_token == 0
    assert result.inputs.measured_completion == 0
    assert result.inputs.measured_concurrency == 0
    assert not result.inputs.pilot_config
    assert "unproved" in result.latency_title
    assert any("pilot measurements belong to a different serving configuration" in item for item in result.validation)


def test_billing_and_monthly_demand_do_not_invalidate_runtime_measurements() -> None:
    query = parse_qs(urlsplit(hosting_url(pilot().inputs)).query)
    query.update({"billing": ["cud-3y"], "requests": ["2000"], "days": ["30"], "duty": ["25"]})
    result = view(query)
    assert result.inputs.measured_first_token == 1
    assert "meets your latency targets" in result.latency_title
    assert not result.validation


def test_unbound_legacy_measurements_need_explicit_confirmation() -> None:
    result = view({"measured-first": "1", "measured-complete": "5", "measured-concurrency": "8"})
    assert result.inputs.measured_first_token == 1
    assert "confirm" in result.latency_title.lower()
    assert not result.inputs.pilot_config


def test_sensitivity_links_clear_stale_measurements_before_serializing() -> None:
    result = pilot()
    for row in result.sensitivity:
        for cell in row.cells:
            replay = view(parse_qs(urlsplit(cell.url).query))
            assert not replay.validation
            assert replay.inputs == cell.inputs
            assert bool(cell.inputs.pilot_config) == (cell.inputs.tokens_per_second == result.inputs.tokens_per_second)


def test_stale_confirmation_cannot_rebind_old_measurements_to_new_hardware() -> None:
    result = view(
        {
            "node": "a2-ultra-1g",
            "confirm-pilot": view().current_pilot_config,
            "measured-first": "1",
            "measured-complete": "5",
            "measured-concurrency": "8",
        }
    )
    # The measurements stay for a fresh confirmation but never bind to the new hardware.
    assert not result.inputs.pilot_config
    assert result.inputs.measured_first_token == 1
    assert "confirm" in result.latency_title.lower()
    assert any("check recorded latency again" in item for item in result.validation)


def test_measurements_entered_with_a_concurrency_change_survive_until_confirmed() -> None:
    query = {
        "mode": "advanced",
        "concurrency": "16",
        "measured-concurrency": "16",
        "measured-first": "1",
        "measured-complete": "10",
        "confirm-pilot": view().current_pilot_config,
    }
    pending = view(query)
    assert (pending.inputs.measured_concurrency, pending.inputs.measured_first_token) == (16, 1)
    assert pending.inputs.measured_completion == 10
    assert not pending.inputs.pilot_config

    confirmed = view({**query, "confirm-pilot": pending.current_pilot_config})
    assert confirmed.inputs.pilot_config == pending.current_pilot_config
    assert not confirmed.validation


def test_invalid_pilot_reference_is_not_reflected_into_the_page() -> None:
    result = view({"pilot": "untrusted-value", "measured-first": "1"})
    assert not result.inputs.pilot_config
    assert all("untrusted-value" not in item for item in result.validation)


def test_native_billing_fallback_names_the_hardware_and_replacement() -> None:
    result = view({"node": "a4", "billing": "on-demand"})
    # Flex-start is listed first but cannot serve this interactive scenario.
    assert result.inputs.billing_plan == "cud-1y"
    assert any("A4" in item and "1-year resource CUD" in item for item in result.validation)
    assert not result.estimate.compatibility_issue


# Simple mode, automatic fleets, and source-backed compatibility and pricing boundaries.
# These call the calculator directly: its default mode and the real clock unless `now` is given.


@pytest.mark.parametrize(
    ("preset", "requests", "input_tokens", "output_tokens"),
    [
        ("scheduled-workflow", 75000, 450000000, 112500000),
        ("document-pipeline", 30000, 240000000, 15000000),
        ("automated-support", 45000, 180000000, 13500000),
    ],
)
def test_automated_presets_count_every_model_call(preset, requests, input_tokens, output_tokens) -> None:
    result = build_llm_self_hosting_view({"preset": preset})
    assert not result.validation
    assert result.estimate.requests_month == requests
    assert result.estimate.input_tokens_month == input_tokens
    assert result.estimate.output_tokens_month == output_tokens
    assert build_llm_self_hosting_view(parse_qs(urlsplit(hosting_url(result.inputs)).query)).inputs == result.inputs


def test_operations_budget_is_removed_from_costs_and_agent_parameters() -> None:
    original = build_llm_self_hosting_view({})
    legacy = build_llm_self_hosting_view({"platform": "5000"})
    assert legacy.validation == ("Operations budget is no longer included; totals cover GPU compute and the GKE fee",)
    assert legacy.estimate.total_monthly_usd == original.estimate.total_monthly_usd
    assert legacy.estimate.total_monthly_usd == pytest.approx(
        legacy.estimate.compute_monthly_usd + legacy.estimate.control_monthly_usd
    )
    serialized = compare_hosting({}).model_dump()
    assert "platform_monthly_usd" not in serialized["inputs"]
    assert "platform_monthly_usd" not in serialized["estimate"]
    assert "platform" not in serialized["parameters"]
    with pytest.raises(ValueError, match="Unknown calculator parameter"):
        compare_hosting({"platform": "5000"})


def test_simple_usage_window_sizes_capacity_without_inflating_volume_or_api_bills() -> None:
    steady = build_llm_self_hosting_view({"preset": "scheduled-workflow", "window": "24"})
    workday = build_llm_self_hosting_view({"preset": "scheduled-workflow", "window": "8"})
    peak = build_llm_self_hosting_view({"preset": "scheduled-workflow", "window": "1"})
    assert steady.estimate.qualified
    assert [result.inputs.replicas for result in (steady, workday, peak)] == [1, 3, 17]
    for concentrated in (workday, peak):
        assert not concentrated.validation
        assert concentrated.estimate.demand_fits
        assert concentrated.estimate.daily_demand_fits
        assert concentrated.estimate.qualified
        assert concentrated.estimate.requests_month == steady.estimate.requests_month
        assert concentrated.estimate.compute_monthly_usd == pytest.approx(
            steady.estimate.compute_monthly_usd
            * concentrated.inputs.replicas
            * concentrated.inputs.demand_window_hours
            / 24
        )
        assert [row.monthly_usd for row in concentrated.apis] == [row.monthly_usd for row in steady.apis]
    assert workday.estimate.capacity_requests_day == pytest.approx(steady.estimate.capacity_requests_day)
    assert peak.estimate.capacity_requests_day == pytest.approx(steady.estimate.capacity_requests_day / 24 * 17)
    assert peak.estimate.required_output_tokens_per_second == pytest.approx(2500 * 1500 / 3600)
    assert peak.estimate.usable_output_tokens_per_second == 1105
    assert peak.estimate.capacity_requests_month == 79560
    expanded = build_llm_self_hosting_view(
        {"mode": "advanced", "preset": "scheduled-workflow", "window": "8", "replicas": "3"}
    )
    assert expanded.estimate.qualified
    assert expanded.estimate.compute_monthly_usd == pytest.approx(3 * steady.selected_price.hourly_usd * 730)
    fixed_peak = build_llm_self_hosting_view({"mode": "advanced", "preset": "scheduled-workflow", "window": "1"})
    frame = fixed_peak.cost_plot.frames[fixed_peak.cost_plot.selected]
    assert "beyond this fleet's capacity" in frame.summary
    task_scenario = build_llm_self_hosting_view(
        {"mode": "advanced", "preset": "scheduled-workflow", "window": "1", "tasks": "10000"}
    )
    assert not task_scenario.tasks[0].fits
    assert any(row.break_even_fits for row in peak.apis)


@pytest.mark.parametrize("preset", DEMAND_PRESETS, ids=lambda preset: preset.id)
@pytest.mark.parametrize("window", ["24", "8", "1"])
def test_automatic_fleet_is_minimal_and_survives_mode_and_url_changes(preset, window: str) -> None:
    result = build_llm_self_hosting_view({"preset": preset.id, "window": window})
    assert not result.validation
    assert result.estimate.qualified
    assert result.estimate.window_capacity_pct <= 100
    assert result.estimate.demand_capacity_pct <= 100
    assert build_llm_self_hosting_view(parse_qs(urlsplit(hosting_url(result.inputs)).query)).inputs == result.inputs
    advanced = build_llm_self_hosting_view(parse_qs(urlsplit(result.advanced_url).query))
    assert not advanced.validation
    assert advanced.inputs == replace(result.inputs, mode="advanced")
    assert advanced.estimate == result.estimate
    if result.inputs.replicas > 1:
        smaller = estimate_hosting(
            result.selected_model,
            result.selected_node,
            result.selected_quant,
            replace(result.inputs, replicas=result.inputs.replicas - 1),
        )
        assert not smaller.daily_demand_fits or not smaller.demand_fits


def test_busy_peak_needs_more_than_eight_replicas_and_agent_returns_the_resolved_fleet() -> None:
    result = compare_hosting({"preset": "service", "window": "1"})
    assert result.inputs.replicas == 129
    assert result.estimate.total_nodes == 129
    assert result.comparison_ready


@pytest.mark.parametrize("preset", DEMAND_PRESETS, ids=lambda preset: preset.id)
def test_largest_simple_workload_preserves_its_fleet_in_advanced_mode(preset) -> None:
    result = build_llm_self_hosting_view({"mode": "simple", "preset": preset.id, "requests": "10000000", "window": "1"})
    advanced = build_llm_self_hosting_view(parse_qs(urlsplit(result.advanced_url).query))
    assert not result.validation
    assert not advanced.validation
    assert advanced.inputs == replace(result.inputs, mode="advanced")
    assert advanced.estimate == result.estimate


def test_sizing_also_checks_monthly_capacity_for_a_31_day_workload() -> None:
    inputs = replace(
        DEFAULT_HOSTING_INPUTS,
        requests_per_day=5616,
        active_days=31,
        output_tokens_request=1000,
        demand_window_hours=24,
    )
    assert replicas_for_demand(inputs) == 2


def test_advanced_window_changes_capacity_while_preserving_the_manually_selected_fleet() -> None:
    flat = build_llm_self_hosting_view(
        {"mode": "advanced", "preset": "scheduled-workflow", "replicas": "1", "window": "24"}
    )
    peak = build_llm_self_hosting_view(
        {"mode": "advanced", "preset": "scheduled-workflow", "replicas": "1", "window": "1"}
    )
    assert flat.estimate.qualified
    assert not peak.estimate.qualified
    assert peak.inputs.replicas == flat.inputs.replicas == 1
    assert peak.estimate.total_monthly_usd == flat.estimate.total_monthly_usd
    assert peak.estimate.requests_month == flat.estimate.requests_month


@pytest.mark.parametrize("window", ["0", "-1", "25", "nan", "inf"])
def test_invalid_usage_windows_fail_closed(window: str) -> None:
    for mode in ("simple", "advanced"):
        parameters = {"mode": mode, "window": window}
        result = build_llm_self_hosting_view(parameters)
        assert result.validation
        assert result.inputs.demand_window_hours == 8
        with pytest.raises(ValueError, match="Invalid calculator parameters"):
            compare_hosting(parameters)


def test_custom_advanced_window_returns_to_a_supported_simple_choice() -> None:
    advanced = build_llm_self_hosting_view({"mode": "advanced", "window": "2.5"})
    assert not advanced.validation
    assert advanced.inputs.demand_window_hours == 2.5
    simple = build_llm_self_hosting_view(parse_qs(urlsplit(advanced.simple_url).query))
    assert not simple.validation
    assert simple.inputs.demand_window_hours == 24


@pytest.mark.parametrize("model", FRONTIER_MODELS, ids=lambda model: model.id)
@pytest.mark.parametrize("billing", ["on-demand", "cud-1y", "cud-3y"])
def test_every_simple_model_has_a_supported_checkpoint_and_billing_plan(model, billing: str) -> None:
    result = build_llm_self_hosting_view({"model": model.id, "billing": billing})
    assert not result.validation
    assert result.selected_quant.id in model.supported_quantizations
    assert result.estimate.weight_memory_gb == dict(model.checkpoint_memory)[result.selected_quant.id]
    assert not result.estimate.compatibility_issue
    assert result.selected_price.plan == billing
    assert result.estimate.compute_monthly_usd == pytest.approx(
        result.estimate.total_nodes * result.selected_price.hourly_usd * 730
    )


@pytest.mark.parametrize(
    "parameters",
    [
        {"model": "qwen3-8-27b", "node": "a2-ultra-1g", "quant": "fp8"},
        {"model": "qwen3-8-27b", "node": "g2-standard-12", "quant": "fp16"},
        {"model": "nemotron-3-5-super-vl", "node": "a3-ultra", "quant": "nvfp4"},
        {"model": "nemotron-3-5-super-vl", "node": "g4-standard-48", "quant": "fp16"},
        {"model": "nemotron-3-5-super-vl", "node": "a4", "quant": "nvfp4", "billing": "cud-1y"},
        {"model": "kimi-k3", "node": "g4-standard-48", "quant": "mxfp4"},
        {"model": "glm-5-3", "node": "a3-high", "quant": "fp8"},
        {"model": "glm-5-3-flash", "node": "g4-standard-48", "quant": "fp8"},
        {"model": "mistral-large-4", "node": "a4", "quant": "fp8", "billing": "cud-1y"},
        {"model": "mistral-large-4", "node": "a3-high", "quant": "fp8"},
        {"model": "minimax-m3-1-flash", "node": "tpu7x-standard-4t", "quant": "mixed-nvfp4"},
        {"model": "qwen3-8-27b", "node": "ct6e-standard-8t", "quant": "fp16"},
        {"model": "qwen3-5-4b", "node": "tpu7x-standard-4t", "quant": "fp16"},
        {"model": "gemma-4-26b-a4b", "node": "ct6e-standard-8t", "quant": "fp8"},
        {"model": "gemma-4-26b-a4b", "node": "tpu7x-standard-4t", "quant": "nvfp4"},
        {"model": "muse-spark-open", "node": "a3-high", "quant": "fp16"},
    ],
)
def test_unsupported_combinations_cannot_qualify_or_be_overridden_by_a_pilot(parameters) -> None:
    result = build_llm_self_hosting_view(parameters)
    assert result.estimate.compatibility_issue
    assert not result.estimate.qualified
    assert not result.comparison_ready
    with pytest.raises(ValueError, match="Invalid calculator parameters"):
        compare_hosting(parameters)
    recorded = build_llm_self_hosting_view(
        parameters
        | {
            "confirm-pilot": result.current_pilot_config,
            "measured-concurrency": "8",
            "measured-first": "1",
            "measured-complete": "5",
        }
    )
    assert not recorded.estimate.qualified
    assert recorded.estimate.compatibility_issue


def test_native_fp4_sizes_include_mixed_precision_and_scales() -> None:
    nemotron = build_llm_self_hosting_view({"model": "nemotron-3-5-super-vl", "quant": "nvfp4", "node": "auto"})
    assert nemotron.inputs.node_pool_id == "g4-standard-48"
    assert nemotron.estimate.weight_memory_gb == pytest.approx(75.010189968)
    assert not nemotron.validation
    gemma = build_llm_self_hosting_view({"model": "gemma-4-26b-a4b", "quant": "nvfp4", "node": "auto"})
    assert gemma.estimate.weight_memory_gb == pytest.approx(16.417035012)
    assert gemma.inputs.node_pool_id == "g4-standard-48"
    muse = build_llm_self_hosting_view(
        {"model": "muse-spark-open", "quant": "nvfp4", "node": "auto", "billing": "cud-1y"}
    )
    assert muse.estimate.weight_memory_gb == pytest.approx(533.011023472)
    assert muse.inputs.node_pool_id == "a4"
    minimax = build_llm_self_hosting_view({"model": "minimax-m3-1-flash"})
    assert minimax.estimate.weight_memory_gb == pytest.approx(250.1034112)
    large = build_llm_self_hosting_view({"model": "mistral-large-4", "billing": "cud-1y"})
    assert (large.inputs.node_pool_id, large.inputs.quantization_id) == ("a4", "nvfp4")
    assert large.estimate.weight_memory_gb == pytest.approx(610.030457408)


def test_mistral_large_4_uses_the_verified_checkpoint_for_each_machine() -> None:
    # NVFP4 is verified only on B200, which has no on-demand rate; on-demand falls back to FP8 on 2x H200.
    on_demand = build_llm_self_hosting_view({"model": "mistral-large-4"})
    assert (on_demand.inputs.node_pool_id, on_demand.inputs.quantization_id) == ("a3-ultra", "fp8")
    assert on_demand.estimate.nodes_per_replica == 2
    assert on_demand.estimate.weight_memory_gb == pytest.approx(1060.548427328)
    assert not on_demand.validation
    explicit = build_llm_self_hosting_view({"mode": "advanced", "model": "mistral-large-4", "quant": "nvfp4"})
    assert "No compatible hardware" in explicit.validation[0]


def test_cloud_tpu_trillium_pricing_bf16_requirement_and_recipe_context_limit() -> None:
    for plan, hourly in (("on-demand", 21.6), ("cud-1y", 15.12), ("cud-3y", 9.76)):
        result = build_llm_self_hosting_view(
            {
                "mode": "advanced",
                "model": "gemma-4-26b-a4b",
                "node": "ct6e-standard-8t",
                "quant": "fp16",
                "billing": plan,
            }
        )
        assert not result.validation
        assert result.estimate.qualified
        assert result.estimate.total_gpus == 8
        assert result.estimate.compute_monthly_usd == pytest.approx(hourly * 730)

    over_context = build_llm_self_hosting_view(
        {
            "mode": "advanced",
            "model": "gemma-4-26b-a4b",
            "node": "ct6e-standard-8t",
            "quant": "fp16",
            "input-tokens": "16000",
            "tokens": "500",
        }
    )
    assert "16,384 context" in over_context.estimate.compatibility_issue
    assert not over_context.estimate.qualified


def test_cloud_tpu_multi_host_slices_and_gpu_vs_tpu_demand_comparison() -> None:
    deepseek = build_llm_self_hosting_view({"model": "deepseek-v4-1-flash", "preset": "department"})
    assert deepseek.selected_node.id == "tpu7x-standard-4t"
    assert deepseek.estimate.nodes_per_replica == 1
    assert deepseek.estimate.qualified
    gpu_row, tpu_row = deepseek.accelerators
    assert (gpu_row.family, gpu_row.node.id) == ("GPU", "a3-ultra")
    assert (tpu_row.family, tpu_row.node.id) == ("Cloud TPU", "tpu7x-standard-4t")
    assert tpu_row.estimate.total_monthly_usd < gpu_row.estimate.total_monthly_usd

    trillium_slice = build_llm_self_hosting_view(
        {"mode": "advanced", "model": "qwen3-8-flash-next", "node": "ct6e-standard-8t", "quant": "fp16"}
    )
    assert not trillium_slice.estimate.compatibility_issue
    assert trillium_slice.estimate.nodes_per_replica == 2
    assert trillium_slice.estimate.total_gpus == 16
    assert not trillium_slice.estimate.topology_confirmed

    ironwood_slice = build_llm_self_hosting_view(
        {"mode": "advanced", "model": "glm-5-3", "node": "tpu7x-standard-4t", "quant": "fp8"}
    )
    assert not ironwood_slice.estimate.compatibility_issue
    assert ironwood_slice.estimate.nodes_per_replica == 2
    assert ironwood_slice.estimate.total_gpus == 8
    assert not ironwood_slice.estimate.topology_confirmed

    for row in build_llm_self_hosting_view({"model": "gemma-4-26b-a4b", "preset": "small-team"}).accelerators:
        assert not row.estimate.compatibility_issue
        replayed = build_llm_self_hosting_view(parse_qs(urlsplit(row.url).query))
        assert not replayed.validation
        assert replayed.estimate == row.estimate

    nemotron_over_g4_context = build_llm_self_hosting_view(
        {
            "mode": "advanced",
            "model": "nemotron-3-5-super-vl",
            "quant": "fp16",
            "input-tokens": "20000",
            "tokens": "500",
        }
    )
    gpu_nemotron, tpu_nemotron = nemotron_over_g4_context.accelerators
    assert (gpu_nemotron.quantization.id, gpu_nemotron.node.id) == ("fp16", "a3-ultra")
    assert gpu_nemotron.estimate.qualified
    assert "requires one of the verified node families" in tpu_nemotron.estimate.compatibility_issue
    assert not tpu_nemotron.estimate.qualified

    flex_batch = build_llm_self_hosting_view(
        {
            "mode": "advanced",
            "model": "qwen3-8-flash-next",
            "node": "a4",
            "billing": "flex",
            "api-mode": "batch",
        }
    )
    gpu_flex, tpu_flex = flex_batch.accelerators
    assert gpu_flex.estimate.qualified
    assert "No Cloud TPU machine in this catalog offers the flex billing plan" in tpu_flex.estimate.compatibility_issue
    assert not tpu_flex.estimate.qualified


def test_one_off_demand_cannot_borrow_a_whole_month_of_capacity() -> None:
    result = build_llm_self_hosting_view({"requests": "100000", "days": "1", "tokens": "600"})
    assert result.estimate.demand_fits
    assert not result.estimate.daily_demand_fits
    assert not result.estimate.qualified


def test_flex_start_requires_batch_delivery() -> None:
    parameters = {"model": "gemma-4-26b-a4b", "node": "a4", "billing": "flex"}
    assert build_llm_self_hosting_view(parameters).estimate.compatibility_issue
    # The GPU card names the Flex-start blocker, not an unrelated placeholder machine such as G2.
    gpu, tpu = view(parameters).accelerators
    assert gpu.estimate.compatibility_issue.startswith("Flex-start queues bounded jobs")
    assert not gpu.estimate.qualified
    assert tpu.estimate.compatibility_issue == "No Cloud TPU machine in this catalog offers the flex billing plan"
    assert not build_llm_self_hosting_view(parameters | {"api-mode": "batch"}).estimate.compatibility_issue
    with pytest.raises(ValueError, match="Flex-start"):
        compare_hosting(parameters)


def test_model_recipe_context_limit_is_hardware_specific() -> None:
    result = build_llm_self_hosting_view({"model": "mistral-large-4", "input-tokens": "300000", "tokens": "1"})
    assert "262,144" in result.estimate.compatibility_issue
    assert not result.estimate.qualified


def test_automatic_hardware_respects_a_solvable_recipe_context_limit() -> None:
    result = build_llm_self_hosting_view(
        {
            "mode": "advanced",
            "model": "glm-5-3",
            "quant": "fp8",
            "node": "auto",
            "billing": "cud-1y",
            "input-tokens": "500000",
            "tokens": "1000",
            "requests": "1",
        }
    )
    assert not result.validation
    assert result.selected_node.id == "a4"
    assert result.estimate.qualified


@pytest.mark.parametrize("mode", ["standard", "batch", "cached"])
def test_haiku_long_prompt_prices_apply_to_the_entire_request(mode: str) -> None:
    short = build_llm_self_hosting_view(
        {"input-tokens": "100000", "tokens": "1000", "api-mode": mode, "cache-prefix": "100000"}
    )
    long = build_llm_self_hosting_view(
        {"input-tokens": "100001", "tokens": "1000", "api-mode": mode, "cache-prefix": "100000"}
    )
    first = next(row for row in short.apis if row.baseline.name == "Claude Haiku 5.5")
    second = next(row for row in long.apis if row.baseline.name == "Claude Haiku 5.5")
    assert first.baseline.input_per_million == 0.1
    assert second.baseline.input_per_million == 0.5
    assert second.baseline.output_per_million == 2.5
    assert second.baseline.cache_read_per_million == 0.05
    assert second.baseline.cache_write_per_million == 0.625
    assert second.monthly_usd > first.monthly_usd * 5


def test_claude_cache_minimum_and_freshness_match_refreshed_sources() -> None:
    result = build_llm_self_hosting_view(
        {"api-mode": "cached", "cache-prefix": "512"}, now=datetime(2026, 10, 12, tzinfo=UTC)
    )
    for row in result.apis:
        assert not row.needs_review
        if row.baseline.name.startswith("Claude"):
            assert row.baseline.cache_minimum == 512
            assert "Standard rates applied" not in row.mode_note


def test_simple_mode_rejects_advanced_overrides_for_agents() -> None:
    with pytest.raises(ValueError, match="Advanced parameters require advanced mode"):
        compare_hosting({"mode": "simple", "quant": "nvfp4"})


@pytest.mark.parametrize("parameters", [{"quality": "on"}, {"pilot": "reference"}, {"confirm-pilot": "reference"}])
def test_optional_advanced_flags_select_advanced_mode_and_are_rejected_in_simple_mode(parameters) -> None:
    assert build_llm_self_hosting_view(parameters).inputs.mode == "advanced"
    with pytest.raises(ValueError, match="Advanced parameters require advanced mode"):
        compare_hosting(parameters | {"mode": "simple"})


def test_daily_capacity_gate_reaches_charts_break_even_and_task_workloads() -> None:
    result = build_llm_self_hosting_view(
        {"requests": "100000", "days": "1", "tokens": "600", "quality": "on", "tasks": "100000"}
    )
    assert not result.estimate.daily_demand_fits
    frame = result.cost_plot.frames[result.cost_plot.selected]
    assert "beyond this fleet's capacity" in frame.summary
    assert not result.tasks[0].fits
    for row in result.apis:
        assert row.break_even_fits == (row.break_even_requests <= result.estimate.capacity_requests_day)


def test_invalid_advanced_auto_selection_retains_the_requested_model() -> None:
    parameters = {"mode": "advanced", "model": "nemotron-3-5-super-vl", "quant": "fp8", "node": "auto"}
    result = build_llm_self_hosting_view(parameters)
    assert result.selected_model.id == "nemotron-3-5-super-vl"
    assert result.selected_quant.id == "fp8"
    assert result.estimate.compatibility_issue
    assert not result.estimate.qualified


def test_scheduled_hours_are_not_counted_again_as_daily_downtime() -> None:
    job = build_llm_self_hosting_view({"mode": "advanced", "preset": "single-job", "duty": "0.5", "window": "1"})
    assert job.estimate.qualified
    assert job.estimate.capacity_tokens_month == pytest.approx(65 * 3.65 * 3600)
    assert job.estimate.capacity_requests_day == pytest.approx(65 * 3600 / 1000)
    assert job.estimate.compute_monthly_usd == pytest.approx(4.49993 * 3.65)
    too_short = build_llm_self_hosting_view(
        {"mode": "advanced", "preset": "single-job", "duty": "0.5", "window": "0.1"}
    )
    assert not too_short.estimate.daily_demand_fits
    assert too_short.estimate.demand_fits


def test_workload_defaults_schedule_jobs_and_keep_teams_available() -> None:
    team = build_llm_self_hosting_view()
    assert team.inputs.demand_window_hours == 8
    assert team.inputs.duty_cycle_percent == 100
    job = build_llm_self_hosting_view({"preset": "single-job"})
    assert job.inputs.demand_window_hours == 1
    assert job.inputs.duty_cycle_percent * 730 / 100 == pytest.approx(1)
    assert job.estimate.compute_monthly_usd == pytest.approx(job.selected_price.hourly_usd)
    committed = build_llm_self_hosting_view({"preset": "single-job", "billing": "cud-1y"})
    assert committed.estimate.compute_monthly_usd == pytest.approx(committed.selected_price.hourly_usd * 730)
    assert committed.estimate.capacity_tokens_month == job.estimate.capacity_tokens_month


def test_simple_volume_override_survives_sharing_and_mode_changes() -> None:
    result = build_llm_self_hosting_view({"mode": "simple", "preset": "department", "requests": "123.5"})
    assert result.inputs.requests_per_day == 123.5
    assert result.inputs.active_days == 22
    assert result.estimate.requests_month == 123.5 * 22
    assert result.selected_preset.id == "department"
    assert not result.validation
    shared = build_llm_self_hosting_view(parse_qs(urlsplit(hosting_url(result.inputs)).query))
    assert shared.inputs == result.inputs
    advanced = build_llm_self_hosting_view(parse_qs(urlsplit(result.advanced_url).query))
    assert advanced.inputs == replace(result.inputs, mode="advanced")
    blank = build_llm_self_hosting_view({"mode": "simple", "preset": "department", "requests": ""})
    assert blank.inputs.requests_per_day == 2000
    invalid = build_llm_self_hosting_view({"mode": "simple", "requests": "NaN"})
    assert len(invalid.validation) == 1
    with pytest.raises(ValueError, match=r"Calls per active day \(requests\) must be"):
        compare_hosting({"mode": "simple", "requests": "NaN"})
    overlong_float = build_llm_self_hosting_view({"mode": "simple", "requests": "9" * 129})
    assert len(overlong_float.validation) == 1
    overlong_int = build_llm_self_hosting_view({"mode": "advanced", "replicas": "9" * 129})
    assert len(overlong_int.validation) == 1
    invalid_simple_billing = build_llm_self_hosting_view({"mode": "simple", "billing": "flex"})
    assert invalid_simple_billing.validation == ("Pricing plan (billing) was not recognized; the default was used",)


def test_compact_model_supplies_a_sourced_l4_budget() -> None:
    result = build_llm_self_hosting_view({"model": "qwen3-5-4b"})
    assert not result.validation
    assert result.inputs.node_pool_id == "g2-standard-12"
    assert result.estimate.weight_memory_gb == pytest.approx(9.319737856)
    assert result.estimate.total_monthly_usd == pytest.approx(803.30393404)
    assert result.estimate.qualified


def test_economical_nvfp4_checkpoint_has_a_bounded_context_and_comparable_alternative() -> None:
    result = build_llm_self_hosting_view({"model": "nemotron-3-5-super-vl"})
    assert result.inputs.quantization_id == "nvfp4"
    assert result.inputs.node_pool_id == "g4-standard-48"
    assert result.estimate.total_monthly_usd == pytest.approx(3357.9489)
    alternative = next(row for row in result.precisions if row.quantization.id == "fp16")
    assert alternative.node.id == "a3-ultra"
    assert alternative.estimate.total_monthly_usd > result.estimate.total_monthly_usd
    shared = build_llm_self_hosting_view(parse_qs(urlsplit(alternative.url).query))
    assert shared.estimate == alternative.estimate
    assert not shared.validation
    with pytest.raises(ValueError, match="16,384 context"):
        compare_hosting(
            {
                "model": "nemotron-3-5-super-vl",
                "quant": "nvfp4",
                "node": "g4-standard-48",
                "input-tokens": "16000",
                "tokens": "500",
            }
        )


def test_catalog_entries_are_internally_consistent() -> None:
    node_ids = {node.id for node in GKE_NODE_POOLS}
    quant_ids = {quant.id for quant in QUANTIZATIONS}
    assert len({model.id for model in FRONTIER_MODELS}) == len(FRONTIER_MODELS)
    for model in FRONTIER_MODELS:
        # Every model names its verified hardware; an empty list would allow every machine.
        assert model.required_node_ids, model.id
        assert set(model.required_node_ids) <= node_ids, model.id
        assert model.default_quantization in model.supported_quantizations, model.id
        assert set(model.supported_quantizations) <= quant_ids, model.id
        # Sizes come from the official checkpoint, never parameters x bytes per parameter.
        assert {precision for precision, _ in model.checkpoint_memory} == set(model.supported_quantizations), model.id
        assert {precision for precision, _ in model.checkpoint_urls} <= set(model.supported_quantizations), model.id
        for precision, nodes in model.quantization_node_ids:
            assert precision in model.supported_quantizations, model.id
            assert set(nodes) <= set(model.required_node_ids), model.id
        limited = {node for node, _ in model.node_context_limits} | {node for node, _ in model.node_minimums}
        assert limited <= set(model.required_node_ids), model.id
        assert all(limit <= model.context_tokens for _, limit in model.node_context_limits), model.id


def test_mcp_rejects_a_preset_that_would_replace_explicit_advanced_demand() -> None:
    with pytest.raises(ValueError, match="preset replaces requests, tokens in advanced mode"):
        compare_hosting({"mode": "advanced", "preset": "service", "requests": "500", "tokens": "50"})
    # Simple mode keeps its documented call-volume override, and a preset alone is fine.
    assert compare_hosting({"mode": "simple", "preset": "service", "requests": "500"}).inputs.requests_per_day == 500
    assert compare_hosting({"mode": "advanced", "preset": "service"}).inputs.requests_per_day == 100_000
