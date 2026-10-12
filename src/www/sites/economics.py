"""Self-hosting calculator economics."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from math import ceil, floor

from .capacity import MONTHLY_HOURS, serving_capacity
from .data import (
    API_BASELINES,
)
from .inputs import configuration_issue, nodes_for_model, pilot_configuration_id, weight_memory_gb
from .models import (
    APIBaseline,
    APIMode,
    FrontierModel,
    GKENodePool,
    HostingEstimate,
    HostingInputs,
    Quantization,
)

CLUSTER_HOURLY_USD = 0.10


def estimate_hosting(
    model: FrontierModel,
    node: GKENodePool,
    quantization: Quantization,
    inputs: HostingInputs,
) -> HostingEstimate:
    weight_memory = weight_memory_gb(model, quantization)
    required_memory = weight_memory * (1 + inputs.memory_overhead_pct / 100)
    nodes_per_replica = nodes_for_model(model, node, required_memory)
    total_nodes = nodes_per_replica * inputs.replicas
    duty = inputs.duty_cycle_percent / 100
    # Stopping a committed VM reduces serving time, never the contractual bill.
    price = node.price(inputs.billing_plan)
    paid_duty = 1 if price.committed else duty
    compute_monthly = total_nodes * price.hourly_usd * MONTHLY_HOURS * paid_duty
    control_monthly = CLUSTER_HOURLY_USD * MONTHLY_HOURS
    total_monthly = compute_monthly + control_monthly
    capacity, capacity_requests_day = serving_capacity(inputs)
    requests = inputs.requests_per_day * inputs.active_days
    output_tokens = requests * inputs.output_tokens_request
    context_issue = ""
    if inputs.input_tokens_request + inputs.output_tokens_request > model.context_tokens:
        context_issue = (
            f"The request needs {inputs.input_tokens_request + inputs.output_tokens_request:,.0f} tokens, "
            f"above {model.name}'s {model.context_tokens:,}-token context limit"
        )
    # Comparison rows may change the model or precision without changing the
    # selected inputs. Pilot evidence belongs only to the actual configuration.
    scenario = replace(inputs, model_id=model.id, node_pool_id=node.id, quantization_id=quantization.id)
    topology_confirmed = nodes_per_replica == 1 or (
        node.multi_host
        and inputs.pilot_config == pilot_configuration_id(scenario)
        and pilot_measurements_complete(inputs)
    )
    compatibility_issue = configuration_issue(scenario)
    daily_demand_fits = inputs.requests_per_day <= capacity_requests_day
    qualified = (
        output_tokens <= capacity
        and daily_demand_fits
        and not context_issue
        and topology_confirmed
        and not compatibility_issue
    )
    return HostingEstimate(
        weight_memory_gb=weight_memory,
        required_memory_gb=required_memory,
        nodes_per_replica=nodes_per_replica,
        total_nodes=total_nodes,
        total_gpus=total_nodes * node.gpu_count,
        compute_monthly_usd=compute_monthly,
        control_monthly_usd=control_monthly,
        total_monthly_usd=total_monthly,
        capacity_tokens_month=capacity,
        capacity_requests_day=capacity_requests_day,
        requests_month=requests,
        input_tokens_month=requests * inputs.input_tokens_request,
        output_tokens_month=output_tokens,
        demand_capacity_pct=output_tokens / capacity * 100,
        window_capacity_pct=inputs.requests_per_day / capacity_requests_day * 100,
        required_output_tokens_per_second=inputs.requests_per_day
        * inputs.output_tokens_request
        / (inputs.demand_window_hours * 60 * 60),
        usable_output_tokens_per_second=inputs.tokens_per_second * inputs.replicas * inputs.target_utilization / 100,
        capacity_requests_month=floor(
            min(capacity / inputs.output_tokens_request, capacity_requests_day * inputs.active_days)
        ),
        per_thousand_requests_usd=total_monthly / requests * 1000,
        demand_fits=output_tokens <= capacity,
        context_issue=context_issue,
        topology_confirmed=topology_confirmed,
        qualified=qualified,
        compatibility_issue=compatibility_issue,
        daily_demand_fits=daily_demand_fits,
    )


def pilot_measurements_complete(inputs: HostingInputs) -> bool:
    """Return whether bound pilot evidence covers the modeled concurrency."""
    return (
        inputs.measured_concurrency >= inputs.concurrency
        and inputs.measured_first_token > 0
        and inputs.measured_completion > 0
    )


def api_request_issue(inputs: HostingInputs, baseline: APIBaseline) -> str:
    """Explain why a request cannot be sent to one managed API baseline."""
    if inputs.input_tokens_request > baseline.input_token_limit:
        return f"Input exceeds the {baseline.input_token_limit:,}-token limit"
    if inputs.output_tokens_request > baseline.output_token_limit:
        return f"Output exceeds the {baseline.output_token_limit:,}-token limit"
    if (
        baseline.context_token_limit
        and inputs.input_tokens_request + inputs.output_tokens_request > baseline.context_token_limit
    ):
        return f"Input plus output exceeds the {baseline.context_token_limit:,}-token context limit"
    return ""


def current_api_baselines(
    now: datetime,
    inputs: HostingInputs,
) -> tuple[APIBaseline, ...]:
    current_date = utc_date(now)
    rows: list[APIBaseline] = []
    for baseline in API_BASELINES:
        row = baseline
        if row.valid_through and current_date > row.valid_through:
            row = replace(
                row,
                input_per_million=row.input_per_million * 2,
                output_per_million=row.output_per_million * 2,
                cache_read_per_million=row.cache_read_per_million * 2,
                cache_storage_per_million_hour=row.cache_storage_per_million_hour * 2,
                note="The announced January 2027 rates are applied. This snapshot needs a fresh source check.",
            )
        if row.name == "GPT-6 Astra" and inputs.input_tokens_request > 272_000:
            row = replace(
                row,
                input_per_million=20,
                output_per_million=75,
                cache_read_per_million=2,
                cache_write_per_million=25,
            )
        if row.name == "Claude Haiku 5.5" and inputs.input_tokens_request > 100_000:
            row = replace(
                row,
                input_per_million=0.5,
                output_per_million=2.5,
                cache_read_per_million=0.05,
                cache_write_per_million=0.625,
            )
        rows.append(row)
    return tuple(rows)


def api_monthly_cost(
    inputs: HostingInputs,
    baseline: APIBaseline,
    requests: float,
) -> tuple[float, float]:
    input_cost = inputs.input_tokens_request * requests * baseline.input_per_million
    output_cost = inputs.output_tokens_request * requests * baseline.output_per_million
    if inputs.api_mode is APIMode.BATCH:
        return (input_cost + output_cost) / 2_000_000, 0
    overhead = 0.0
    if inputs.api_mode is APIMode.CACHED:
        prefix = inputs.cache_prefix_tokens
        if baseline.cache_minimum <= prefix <= inputs.input_tokens_request:
            # A partially filled final group still incurs a complete warm-up.
            writes = min(requests, ceil(requests / inputs.cache_requests))
            reads = requests - writes
            input_cost = (inputs.input_tokens_request - prefix) * requests * baseline.input_per_million
            if baseline.cache_storage_per_million_hour > 0:
                reads = requests
                overhead = writes * prefix * baseline.cache_storage_per_million_hour / 12
            else:
                overhead = writes * prefix * baseline.cache_write_per_million
            input_cost += reads * prefix * baseline.cache_read_per_million + overhead
    return (input_cost + output_cost) / 1_000_000, overhead / 1_000_000


def utc_date(now: datetime) -> str:
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now.astimezone(UTC).date().isoformat()
