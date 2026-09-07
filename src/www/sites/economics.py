"""Self-hosting calculator economics."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from math import ceil

from .data import (
    API_BASELINES,
)
from .models import (
    APIBaseline,
    APIMode,
    FrontierModel,
    GKENodePool,
    HostingEstimate,
    HostingInputs,
    Quantization,
)

# Source-faithful UI copy intentionally uses multiplication signs.

MONTHLY_HOURS = 730.0
SECONDS_PER_MONTH = MONTHLY_HOURS * 60 * 60
SECONDS_PER_DAY = 24 * 60 * 60
CLUSTER_HOURLY_USD = 0.10


def estimate_hosting(
    model: FrontierModel,
    node: GKENodePool,
    quantization: Quantization,
    inputs: HostingInputs,
) -> HostingEstimate:
    weight_memory = model.parameters_b * quantization.bytes_per_param
    required_memory = weight_memory * (1 + inputs.memory_overhead_pct / 100)
    nodes_per_replica = max(1, ceil(required_memory / node.vram_gb))
    total_nodes = nodes_per_replica * inputs.replicas
    duty = inputs.duty_cycle_percent / 100
    # Stopping a committed VM reduces serving time, never the contractual bill.
    price = node.price(inputs.billing_plan)
    paid_duty = 1 if price.committed else duty
    compute_monthly = total_nodes * price.hourly_usd * MONTHLY_HOURS * paid_duty
    control_monthly = CLUSTER_HOURLY_USD * MONTHLY_HOURS
    total_monthly = compute_monthly + control_monthly + inputs.platform_monthly_usd
    capacity = inputs.tokens_per_second * inputs.replicas * (inputs.target_utilization / 100) * SECONDS_PER_MONTH * duty
    capacity_requests_day = (
        inputs.tokens_per_second
        * inputs.replicas
        * (inputs.target_utilization / 100)
        * SECONDS_PER_DAY
        * duty
        / inputs.output_tokens_request
    )
    requests = inputs.requests_per_day * inputs.active_days
    output_tokens = requests * inputs.output_tokens_request
    return HostingEstimate(
        weight_memory_gb=weight_memory,
        required_memory_gb=required_memory,
        nodes_per_replica=nodes_per_replica,
        total_nodes=total_nodes,
        total_gpus=total_nodes * node.gpu_count,
        compute_monthly_usd=compute_monthly,
        control_monthly_usd=control_monthly,
        platform_monthly_usd=inputs.platform_monthly_usd,
        total_monthly_usd=total_monthly,
        capacity_tokens_month=capacity,
        capacity_requests_day=capacity_requests_day,
        requests_month=requests,
        input_tokens_month=requests * inputs.input_tokens_request,
        output_tokens_month=output_tokens,
        demand_capacity_pct=output_tokens / capacity * 100,
        per_thousand_requests_usd=total_monthly / requests * 1000,
        demand_fits=output_tokens <= capacity,
    )


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
