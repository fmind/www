"""Default teammate flow and source-backed compatibility/pricing boundaries."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest
from litestar.testing import TestClient

from www.app import create_app
from www.sites.agent import compare_hosting
from www.sites.calculator import build_llm_self_hosting_view as view
from www.sites.capacity import replicas_for_demand
from www.sites.data import DEFAULT_HOSTING_INPUTS, DEMAND_PRESETS, FRONTIER_MODELS
from www.sites.economics import estimate_hosting
from www.sites.inputs import hosting_url


def test_simple_mode_has_basic_choices_and_a_clean_shareable_url() -> None:
    result = view({"preset": "department", "model": "mistral-small-4", "billing": "cud-3y"})
    assert result.inputs.mode == "simple"
    assert result.inputs.quantization_id == "nvfp4"
    assert result.inputs.node_pool_id == "g4-standard-48"
    assert result.inputs.memory_overhead_pct == 25
    assert result.estimate.requests_month == 44000
    assert not result.validation
    parameters = parse_qs(urlsplit(hosting_url(result.inputs)).query)
    assert set(parameters) == {"mode", "preset", "model", "billing", "window"}
    assert view(parameters).inputs == result.inputs
    with TestClient(create_app()) as client:
        html = client.get("/sites/llm-self-hosting/").text
        for name in ("preset", "model", "billing", "window", "advanced-mode"):
            assert f'id="{name}"' in html
        for name in ("platform", "quant", "node", "throughput", "quality-settings", "cost-volume"):
            assert f'id="{name}"' not in html


def test_presets_and_models_are_presented_from_smallest_to_largest() -> None:
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
    with TestClient(create_app()) as client:
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
def test_hosting_page_keeps_every_section_open_with_setup_before_method(mode: str) -> None:
    with TestClient(create_app()) as client:
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


@pytest.mark.parametrize(
    ("preset", "requests", "input_tokens", "output_tokens"),
    [
        ("scheduled-workflow", 75000, 450000000, 112500000),
        ("document-pipeline", 30000, 240000000, 15000000),
        ("automated-support", 45000, 180000000, 13500000),
    ],
)
def test_automated_presets_count_every_model_call(preset, requests, input_tokens, output_tokens) -> None:
    result = view({"preset": preset})
    assert not result.validation
    assert result.estimate.requests_month == requests
    assert result.estimate.input_tokens_month == input_tokens
    assert result.estimate.output_tokens_month == output_tokens
    assert view(parse_qs(urlsplit(hosting_url(result.inputs)).query)).inputs == result.inputs


def test_operations_budget_is_removed_from_costs_and_agent_parameters() -> None:
    original = view({})
    legacy = view({"platform": "5000"})
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
    steady = view({"preset": "scheduled-workflow", "window": "24"})
    workday = view({"preset": "scheduled-workflow", "window": "8"})
    peak = view({"preset": "scheduled-workflow", "window": "1"})
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
    expanded = view({"mode": "advanced", "preset": "scheduled-workflow", "window": "8", "replicas": "3"})
    assert expanded.estimate.qualified
    assert expanded.estimate.compute_monthly_usd == pytest.approx(3 * steady.selected_price.hourly_usd * 730)
    fixed_peak = view({"mode": "advanced", "preset": "scheduled-workflow", "window": "1"})
    frame = fixed_peak.cost_plot.frames[fixed_peak.cost_plot.selected]
    assert "beyond this fleet's capacity" in frame.summary
    task_scenario = view({"mode": "advanced", "preset": "scheduled-workflow", "window": "1", "tasks": "10000"})
    assert not task_scenario.tasks[0].fits
    assert any(row.break_even_fits for row in peak.apis)


@pytest.mark.parametrize("preset", DEMAND_PRESETS, ids=lambda preset: preset.id)
@pytest.mark.parametrize("window", ["24", "8", "1"])
def test_automatic_fleet_is_minimal_and_survives_mode_and_url_changes(preset, window: str) -> None:
    result = view({"preset": preset.id, "window": window})
    assert not result.validation
    assert result.estimate.qualified
    assert result.estimate.window_capacity_pct <= 100
    assert result.estimate.demand_capacity_pct <= 100
    assert view(parse_qs(urlsplit(hosting_url(result.inputs)).query)).inputs == result.inputs
    advanced = view(parse_qs(urlsplit(result.advanced_url).query))
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
    result = view({"mode": "simple", "preset": preset.id, "requests": "10000000", "window": "1"})
    advanced = view(parse_qs(urlsplit(result.advanced_url).query))
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
    flat = view({"mode": "advanced", "preset": "scheduled-workflow", "replicas": "1", "window": "24"})
    peak = view({"mode": "advanced", "preset": "scheduled-workflow", "replicas": "1", "window": "1"})
    assert flat.estimate.qualified
    assert not peak.estimate.qualified
    assert peak.inputs.replicas == flat.inputs.replicas == 1
    assert peak.estimate.total_monthly_usd == flat.estimate.total_monthly_usd
    assert peak.estimate.requests_month == flat.estimate.requests_month


def test_simple_outputs_explain_load_cost_and_fixed_fleet_break_even() -> None:
    result = view({"preset": "scheduled-workflow", "window": "1"})
    for row in result.apis:
        assert row.break_even_fits == (row.break_even_requests <= result.estimate.capacity_requests_month)
    with TestClient(create_app()) as client:
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


@pytest.mark.parametrize("window", ["0", "-1", "25", "nan", "inf"])
def test_invalid_usage_windows_fail_closed(window: str) -> None:
    for mode in ("simple", "advanced"):
        parameters = {"mode": mode, "window": window}
        result = view(parameters)
        assert result.validation
        assert result.inputs.demand_window_hours == 8
        with pytest.raises(ValueError, match="Invalid calculator parameters"):
            compare_hosting(parameters)


def test_custom_advanced_window_returns_to_a_supported_simple_choice() -> None:
    advanced = view({"mode": "advanced", "window": "2.5"})
    assert not advanced.validation
    assert advanced.inputs.demand_window_hours == 2.5
    simple = view(parse_qs(urlsplit(advanced.simple_url).query))
    assert not simple.validation
    assert simple.inputs.demand_window_hours == 24


@pytest.mark.parametrize("model", FRONTIER_MODELS, ids=lambda model: model.id)
@pytest.mark.parametrize("billing", ["on-demand", "cud-1y", "cud-3y"])
def test_every_simple_model_has_a_supported_checkpoint_and_billing_plan(model, billing: str) -> None:
    result = view({"model": model.id, "billing": billing})
    if model.deployment_issue:
        assert result.validation
        assert result.selected_model.id != model.id
        return
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
        {"model": "mistral-small-4", "node": "a3-ultra", "quant": "nvfp4"},
        {"model": "mistral-small-4", "node": "g4-standard-48", "quant": "fp16"},
        {"model": "kimi-k3", "node": "g4-standard-48", "quant": "mxfp4"},
        {"model": "glm-5-3", "node": "a3-high", "quant": "fp8"},
        {"model": "glm-5-3-flash", "node": "g4-standard-48", "quant": "fp8"},
        {"model": "deepseek-v4-pro", "node": "a3-high", "quant": "mixed-fp4"},
        {"model": "k2-horizon-375b-a23b", "node": "a3-high", "quant": "fp16"},
    ],
)
def test_unsupported_combinations_cannot_qualify_or_be_overridden_by_a_pilot(parameters) -> None:
    result = view(parameters)
    assert result.estimate.compatibility_issue
    assert not result.estimate.qualified
    assert not result.comparison_ready
    with pytest.raises(ValueError, match="Invalid calculator parameters"):
        compare_hosting(parameters)
    recorded = view(
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
    mistral = view({"model": "mistral-small-4", "quant": "nvfp4", "node": "auto"})
    assert mistral.inputs.node_pool_id == "g4-standard-48"
    assert mistral.estimate.weight_memory_gb == pytest.approx(70.801904048)
    assert not mistral.validation
    muse = view({"model": "muse-glimmer", "quant": "nvfp4", "node": "auto"})
    assert muse.estimate.weight_memory_gb == pytest.approx(24.669346036)
    assert muse.estimate.required_memory_gb > 24
    deepseek = view({"model": "deepseek-v4-pro"})
    assert deepseek.estimate.weight_memory_gb == pytest.approx(892.727580904)


def test_one_off_demand_cannot_borrow_a_whole_month_of_capacity() -> None:
    result = view({"requests": "100000", "days": "1", "tokens": "600"})
    assert result.estimate.demand_fits
    assert not result.estimate.daily_demand_fits
    assert not result.estimate.qualified


def test_flex_start_requires_batch_delivery() -> None:
    parameters = {"node": "a4", "billing": "flex"}
    assert view(parameters).estimate.compatibility_issue
    assert not view(parameters | {"api-mode": "batch"}).estimate.compatibility_issue
    with pytest.raises(ValueError, match="Flex-start"):
        compare_hosting(parameters)


def test_model_recipe_context_limit_is_hardware_specific() -> None:
    result = view({"model": "deepseek-v4-pro", "input-tokens": "800000", "tokens": "1"})
    assert "800,000" in result.estimate.compatibility_issue
    assert not result.estimate.qualified


def test_automatic_hardware_respects_a_solvable_recipe_context_limit() -> None:
    result = view(
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
    short = view({"input-tokens": "100000", "tokens": "1000", "api-mode": mode, "cache-prefix": "100000"})
    long = view({"input-tokens": "100001", "tokens": "1000", "api-mode": mode, "cache-prefix": "100000"})
    first = next(row for row in short.apis if row.baseline.name == "Claude Haiku 5.5")
    second = next(row for row in long.apis if row.baseline.name == "Claude Haiku 5.5")
    assert first.baseline.input_per_million == 0.1
    assert second.baseline.input_per_million == 0.5
    assert second.baseline.output_per_million == 2.5
    assert second.baseline.cache_read_per_million == 0.05
    assert second.baseline.cache_write_per_million == 0.625
    assert second.monthly_usd > first.monthly_usd * 5


def test_claude_cache_minimum_and_freshness_match_refreshed_sources() -> None:
    result = view({"api-mode": "cached", "cache-prefix": "512"}, now=datetime(2026, 10, 12, tzinfo=UTC))
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
    assert view(parameters).inputs.mode == "advanced"
    with pytest.raises(ValueError, match="Advanced parameters require advanced mode"):
        compare_hosting(parameters | {"mode": "simple"})


def test_auto_flex_start_returns_validation_without_crashing_the_web_page() -> None:
    parameters = {"mode": "advanced", "node": "auto", "billing": "flex"}
    result = view(parameters)
    assert result.validation
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        response = client.get("/sites/llm-self-hosting/", params=parameters)
        assert response.status_code == 200
        assert "No compatible hardware" in response.text
    with pytest.raises(ValueError, match="Invalid calculator parameters"):
        compare_hosting(parameters)


def test_daily_capacity_gate_reaches_charts_break_even_and_task_workloads() -> None:
    result = view({"requests": "100000", "days": "1", "tokens": "600", "quality": "on", "tasks": "100000"})
    assert not result.estimate.daily_demand_fits
    frame = result.cost_plot.frames[result.cost_plot.selected]
    assert "beyond this fleet's capacity" in frame.summary
    assert not result.tasks[0].fits
    for row in result.apis:
        assert row.break_even_fits == (row.break_even_requests <= result.estimate.capacity_requests_day)


def test_invalid_advanced_auto_selection_retains_the_requested_model() -> None:
    parameters = {"mode": "advanced", "model": "mistral-small-4", "quant": "fp16", "node": "auto"}
    result = view(parameters)
    assert result.selected_model.id == "mistral-small-4"
    assert result.selected_quant.id == "fp16"
    assert result.estimate.compatibility_issue
    assert not result.estimate.qualified


def test_scheduled_hours_are_not_counted_again_as_daily_downtime() -> None:
    job = view({"mode": "advanced", "preset": "single-job", "duty": "0.5", "window": "1"})
    assert job.estimate.qualified
    assert job.estimate.capacity_tokens_month == pytest.approx(65 * 3.65 * 3600)
    assert job.estimate.capacity_requests_day == pytest.approx(65 * 3600 / 1000)
    assert job.estimate.compute_monthly_usd == pytest.approx(4.49993 * 3.65)
    too_short = view({"mode": "advanced", "preset": "single-job", "duty": "0.5", "window": "0.1"})
    assert not too_short.estimate.daily_demand_fits
    assert too_short.estimate.demand_fits


def test_workload_defaults_schedule_jobs_and_keep_teams_available() -> None:
    team = view()
    assert team.inputs.demand_window_hours == 8
    assert team.inputs.duty_cycle_percent == 100
    job = view({"preset": "single-job"})
    assert job.inputs.demand_window_hours == 1
    assert job.inputs.duty_cycle_percent * 730 / 100 == pytest.approx(1)
    assert job.estimate.compute_monthly_usd == pytest.approx(job.selected_price.hourly_usd)
    committed = view({"preset": "single-job", "billing": "cud-1y"})
    assert committed.estimate.compute_monthly_usd == pytest.approx(committed.selected_price.hourly_usd * 730)
    assert committed.estimate.capacity_tokens_month == job.estimate.capacity_tokens_month


def test_simple_volume_override_survives_sharing_and_mode_changes() -> None:
    result = view({"mode": "simple", "preset": "department", "requests": "123.5"})
    assert result.inputs.requests_per_day == 123.5
    assert result.inputs.active_days == 22
    assert result.estimate.requests_month == 123.5 * 22
    assert result.selected_preset.id == "department"
    assert not result.validation
    shared = view(parse_qs(urlsplit(hosting_url(result.inputs)).query))
    assert shared.inputs == result.inputs
    advanced = view(parse_qs(urlsplit(result.advanced_url).query))
    assert advanced.inputs == replace(result.inputs, mode="advanced")
    blank = view({"mode": "simple", "preset": "department", "requests": ""})
    assert blank.inputs.requests_per_day == 2000
    invalid = view({"mode": "simple", "requests": "NaN"})
    assert len(invalid.validation) == 1
    with pytest.raises(ValueError, match="requests must be"):
        compare_hosting({"mode": "simple", "requests": "NaN"})


def test_compact_model_supplies_a_sourced_l4_budget() -> None:
    result = view({"model": "qwen3-5-4b"})
    assert not result.validation
    assert result.inputs.node_pool_id == "g2-standard-12"
    assert result.estimate.weight_memory_gb == pytest.approx(9.319737856)
    assert result.estimate.total_monthly_usd == pytest.approx(803.30393404)
    assert result.estimate.qualified


def test_economical_mistral_checkpoint_has_a_bounded_context_and_comparable_alternative() -> None:
    result = view({"model": "mistral-small-4"})
    assert result.inputs.quantization_id == "nvfp4"
    assert result.inputs.node_pool_id == "g4-standard-48"
    assert result.estimate.total_monthly_usd == pytest.approx(3357.9489)
    alternative = next(row for row in result.precisions if row.quantization.id == "fp8")
    assert alternative.node.id == "a3-ultra"
    assert alternative.estimate.total_monthly_usd > result.estimate.total_monthly_usd
    shared = view(parse_qs(urlsplit(alternative.url).query))
    assert shared.estimate == alternative.estimate
    assert not shared.validation
    with pytest.raises(ValueError, match="16,384 context"):
        compare_hosting(
            {
                "model": "mistral-small-4",
                "quant": "nvfp4",
                "node": "g4-standard-48",
                "input-tokens": "16000",
                "tokens": "500",
            }
        )
