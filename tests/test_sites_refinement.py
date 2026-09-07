from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest

from www.sites.calculator import build_llm_self_hosting_view
from www.sites.formatting import hosting_decision_title
from www.sites.inputs import hosting_url

NOW = datetime(2026, 9, 7, tzinfo=UTC)


def view(query=None):
    return build_llm_self_hosting_view(query, now=NOW)


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
    result = view({"input-tokens": "256000", "tokens": "1"})
    assert result.inputs.input_tokens_request == 256000
    assert result.estimate.context_issue
    assert not result.estimate.qualified
    assert result.estimate.context_issue in result.validation
    assert "context" in hosting_decision_title(result).lower()
    assert all(not cell.fits for row in result.sensitivity for cell in row.cells)
    assert not result.tasks[0].fits
    assert result.tasks[0].request_issue


def test_context_limit_is_inclusive_of_input_and_output() -> None:
    assert view({"input-tokens": "255000", "tokens": "1000"}).estimate.qualified
    assert not view({"input-tokens": "255000", "tokens": "1001"}).estimate.qualified


def test_l4_memory_spanning_hosts_requires_a_configuration_pilot() -> None:
    result = view({"node": "g2-standard-12"})
    assert result.estimate.nodes_per_replica == 2
    assert not result.estimate.topology_confirmed
    assert not result.estimate.qualified
    assert "multi-host" in hosting_decision_title(result).lower()
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
    assert confirmed.estimate.topology_confirmed
    assert confirmed.estimate.qualified
    assert view({"node": "g2-standard-12", "quant": "fp4"}).estimate.qualified


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
    assert all(api.request_issue for api in over_limit.apis)

    gemini_limit = view({"input-tokens": "983040", "tokens": "65536"})
    assert not gemini_limit.apis[0].request_issue
    assert gemini_limit.apis[1].request_issue
    assert not gemini_limit.apis[2].request_issue


def test_pilot_confirmation_survives_a_shared_url() -> None:
    result = pilot()
    assert "meets your latency targets" in result.latency_title
    assert result.inputs.pilot_config == result.current_pilot_config
    shared = view(parse_qs(urlsplit(hosting_url(result.inputs)).query))
    assert shared.inputs == result.inputs
    assert shared.latency_title == result.latency_title
    assert not shared.validation


@pytest.mark.parametrize(
    "change",
    [
        {"model": "kimi-k3"},
        {"node": "g4-standard-48"},
        {"quant": "fp4"},
        {"input-tokens": "4000"},
        {"tokens": "1000"},
        {"replicas": "2"},
        {"throughput": "500"},
        {"overhead": "25"},
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
    assert any("pilot measurements were cleared" in item for item in result.validation)


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
            "node": "g4-standard-48",
            "confirm-pilot": view().current_pilot_config,
            "measured-first": "1",
            "measured-complete": "5",
            "measured-concurrency": "8",
        }
    )
    assert not result.inputs.pilot_config
    assert result.inputs.measured_first_token == 0


def test_invalid_pilot_reference_is_not_reflected_into_the_page() -> None:
    result = view({"pilot": "untrusted-value", "measured-first": "1"})
    assert not result.inputs.pilot_config
    assert all("untrusted-value" not in item for item in result.validation)


def test_native_billing_fallback_names_the_hardware_and_replacement() -> None:
    result = view({"node": "a4", "billing": "on-demand"})
    assert result.inputs.billing_plan == "flex"
    assert any("A4" in item and "DWS Flex-start" in item for item in result.validation)
