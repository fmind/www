from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from math import ceil, isclose

import pytest

from www.sites.calculator import build_llm_self_hosting_view
from www.sites.data import (
    API_BASELINES,
    DEFAULT_HOSTING_INPUTS,
    DEMAND_PRESETS,
    FRONTIER_MODELS,
    GKE_NODE_POOLS,
    QUANTIZATIONS,
)
from www.sites.economics import current_api_baselines, estimate_hosting
from www.sites.formatting import format_count, hosting_decision_copy, hosting_decision_title, task_cost_max

NOW = datetime(2026, 9, 5, 12, tzinfo=UTC)


def view(query: dict[str, str] | None = None):
    return build_llm_self_hosting_view(query, now=NOW)


def test_estimate_uses_whole_nodes_and_complete_monthly_cost() -> None:
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
        platform_monthly_usd=1000,
    )

    estimate = estimate_hosting(model, node, quantization, inputs)

    assert estimate.required_memory_gb == 67.5
    assert estimate.nodes_per_replica == 1
    assert estimate.total_nodes == 2
    assert estimate.total_gpus == 2
    assert estimate.total_monthly_usd == pytest.approx(
        2 * node.price(inputs.billing_plan).hourly_usd * 730 * 0.5 + 0.1 * 730 + 1000,
    )
    assert estimate.capacity_tokens_month == 10 * 2 * 0.5 * 730 * 60 * 60 * 0.5


def test_invalid_required_query_values_fall_back_independently() -> None:
    result = view({"model": "unknown", "replicas": "0", "throughput": "NaN"})

    assert result.inputs.model_id == DEFAULT_HOSTING_INPUTS.model_id
    assert result.inputs.replicas == DEFAULT_HOSTING_INPUTS.replicas
    assert result.inputs.tokens_per_second == DEFAULT_HOSTING_INPUTS.tokens_per_second
    assert result.validation == (
        "model was not recognized; the default was used",
        "replicas must be between 1 and 8; the default was used",
        "throughput must be between 0.1 and 1e+06; the default was used",
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

    assert [row.monthly_usd for row in result.apis] == pytest.approx([13.2, 35.2, 176])
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
    assert partial.estimate.platform_monthly_usd == full.estimate.platform_monthly_usd
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

    assert result.validation == ("preset was not recognized; the validated demand inputs were kept",)
    assert result.inputs.requests_per_day == 7


def test_precision_changes_memory_but_only_whole_nodes_change_bill() -> None:
    small = view()
    assert small.precisions[0].estimate.weight_memory_gb * 4 == small.precisions[2].estimate.weight_memory_gb
    assert small.precisions[0].estimate.total_monthly_usd == small.precisions[2].estimate.total_monthly_usd

    large = view({"model": "kimi-k3", "node": "a4-cud-3y"})
    assert large.precisions[0].estimate.total_nodes < large.precisions[2].estimate.total_nodes
    assert large.precisions[0].estimate.total_monthly_usd < large.precisions[2].estimate.total_monthly_usd


def test_view_compares_all_ranked_models_in_deterministic_order() -> None:
    result = view({"model": "qwen3-8-27b", "node": "a2-ultra-1g"})

    assert len(result.models) == len(result.comparison) == 10
    assert [row.model.rank for row in result.comparison] == list(range(1, 11))
    assert result.estimate.nodes_per_replica == 1
    assert len(API_BASELINES) == 3
    assert isclose(result.estimate.weight_memory_gb, 27)


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
    hosting_candidate = view({"preset": "service", "throughput": "10000"})

    assert hosting_decision_title(overloaded) == "This fleet cannot cover the modeled demand"
    assert "monthly average cannot establish peak-time capacity" in hosting_decision_copy(overloaded)
    assert hosting_decision_title(api_first) == "Start with an API on cost grounds"
    assert api_first.apis[0].baseline.name in hosting_decision_copy(api_first)
    assert hosting_decision_title(hosting_candidate) == "Self-hosting has a cost case to test"


def test_template_quantity_and_task_scale_helpers() -> None:
    result = view()

    assert format_count(1, "node") == "1 node"
    assert format_count(2, "GPU") == "2 GPUs"
    assert task_cost_max(result.tasks) == max(row.per_accepted_usd for row in result.tasks if row.fits)


@pytest.mark.parametrize("node", GKE_NODE_POOLS, ids=lambda node: node.id)
def test_every_published_billing_plan_charges_whole_nodes_and_keeps_idle_commitments(node) -> None:
    for price in node.prices:
        full = view({"node": node.id, "billing": price.plan.value, "replicas": "2"})
        partial = view({"node": node.id, "billing": price.plan.value, "replicas": "2", "duty": "25"})
        assert not full.validation
        assert full.selected_price == price
        assert full.estimate.compute_monthly_usd == pytest.approx(full.estimate.total_nodes * price.hourly_usd * 730)
        assert partial.estimate.compute_monthly_usd == pytest.approx(
            full.estimate.compute_monthly_usd * (1 if price.committed else 0.25),
        )
        assert partial.estimate.capacity_tokens_month == full.estimate.capacity_tokens_month / 4
        assert partial.estimate.total_monthly_usd == pytest.approx(
            partial.estimate.compute_monthly_usd + 73 + 1000,
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
        assert result.estimate.total_nodes == 1
        assert result.estimate.compute_monthly_usd == pytest.approx(rate * 730)


@pytest.mark.parametrize(("node", "billing"), [("a4", "on-demand"), ("g2-standard-12", "flex"), ("a3-high", "unknown")])
def test_unsupported_billing_is_visible_and_uses_a_published_rate(node: str, billing: str) -> None:
    result = view({"node": node, "billing": billing})
    assert len(result.validation) == 1
    assert "billing" in result.validation[0]
    assert result.selected_price == result.selected_node.prices[0]


def test_unpublished_rate_is_rejected_by_calculation_boundary() -> None:
    from www.sites.models import BillingPlan

    node = next(node for node in GKE_NODE_POOLS if node.id == "a4")
    with pytest.raises(ValueError, match="does not offer on-demand"):
        node.price(BillingPlan.ON_DEMAND)


@pytest.mark.parametrize(("legacy", "billing"), [("a4-cud-3y", "cud-3y"), ("a4-flex", "flex")])
def test_old_a4_links_preserve_their_billing_plan(legacy: str, billing: str) -> None:
    result = view({"node": legacy})
    assert not result.validation
    assert result.inputs.node_pool_id == "a4"
    assert result.inputs.billing_plan.value == billing
    overridden = view({"node": legacy, "billing": "cud-1y"})
    assert overridden.inputs.billing_plan.value == "cud-1y"


@pytest.mark.parametrize("model", FRONTIER_MODELS)
def test_static_hardware_reference_fits_fixed_minimum_and_uses_catalog(model) -> None:
    result = view({"model": model.id})
    reference = result.hardware_guidance
    assert reference.node in GKE_NODE_POOLS
    required = model.parameters_b * 0.5 * 1.25
    assert reference.node.vram_gb * reference.nodes_per_replica >= required
    assert reference.nodes_per_replica == 1 or reference.node.multi_host
    for node in GKE_NODE_POOLS:
        hosts = max(1, ceil(required / node.vram_gb))
        if hosts == 1 or node.multi_host:
            assert (reference.nodes_per_replica, reference.node.vram_gb * reference.nodes_per_replica) <= (
                hosts,
                node.vram_gb * hosts,
            )


@pytest.mark.parametrize("model", FRONTIER_MODELS)
def test_hardware_reference_depends_only_on_model(model) -> None:
    initial = view({"model": model.id})
    changed = view(
        {
            "model": model.id,
            "node": "a4",
            "billing": "cud-3y",
            "quant": "fp16",
            "overhead": "50",
            "replicas": "3",
            "duty": "25",
            "requests": "734",
            "throughput": "1",
            "measured-first": "1",
            "measured-complete": "4",
            "measured-concurrency": "8",
            "quality": "on",
        }
    )
    assert changed.hardware_guidance == initial.hardware_guidance
    assert changed.inputs.node_pool_id == "a4"
    assert changed.inputs.measured_first_token == 1
    assert not changed.validation
