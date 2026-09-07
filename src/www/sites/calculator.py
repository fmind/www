"""Self-hosting calculator calculator."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from .charts import hosting_cost_plot
from .data import (
    DEMAND_PRESETS,
    FRONTIER_MODELS,
    GKE_NODE_POOLS,
    GKE_SOURCE_URL,
    INDEX_VERSION,
    MODEL_SNAPSHOT,
    MODEL_SOURCE_URL,
    PRICE_SOURCE_URL,
    QUANTIZATIONS,
)
from .economics import (
    api_monthly_cost,
    api_request_issue,
    current_api_baselines,
    estimate_hosting,
    pilot_measurements_complete,
    utc_date,
)
from .formatting import format_decimal, format_usd2
from .inputs import (
    Query,
    find_model,
    find_node_pool,
    find_quantization,
    hosting_url,
    parse_inputs,
    pilot_configuration_id,
)
from .models import (
    APIBaseline,
    APIComparison,
    APIMode,
    FrontierModel,
    GKENodePool,
    HardwareGuidance,
    HostingEstimate,
    HostingInputs,
    LLMSelfHostingView,
    ModelComparison,
    PrecisionComparison,
    SensitivityCell,
    SensitivityRow,
    TaskComparison,
)

# Source-faithful UI copy intentionally uses multiplication signs.
# ruff: noqa: RUF001


def _api_mode_note(inputs: HostingInputs, baseline: APIBaseline) -> str:
    if inputs.api_mode is APIMode.BATCH:
        return (
            "Batch: 50% off input and output. Asynchronous jobs, up to 24 hours; "
            "unsuitable for live chat. No cache discount combined here."
        )
    if inputs.api_mode is APIMode.CACHED:
        if not (baseline.cache_minimum <= inputs.cache_prefix_tokens <= inputs.input_tokens_request):
            return (
                "Standard rates applied: caching needs at least "
                f"{format_decimal(baseline.cache_minimum, 0)} shared prefix tokens, "
                "within the request's input budget."
            )
        if baseline.cache_storage_per_million_hour > 0:
            return (
                f"Explicit Gemini cache: {format_usd2(baseline.cache_read_per_million)}/M "
                f"cached input + {format_usd2(baseline.cache_storage_per_million_hour)}/M "
                "token-hours stored; five-minute storage charged for every group. Use "
                "GenerateContent, not the Interactions-only implicit cache."
            )
        return (
            f"Cache: {format_usd2(baseline.cache_write_per_million)}/M prefix tokens "
            f"on the first call, {format_usd2(baseline.cache_read_per_million)}/M on "
            "reuse. Calls must share an exact prefix within five minutes; Astra retains "
            "it for at least 30 minutes."
        )
    return "Standard uncached text rates. Immediate requests; no batch or cache discount assumed."


def _compare_apis(
    inputs: HostingInputs,
    estimate: HostingEstimate,
    baselines: tuple[APIBaseline, ...],
) -> tuple[APIComparison, ...]:
    rows: list[APIComparison] = []
    for baseline in baselines:
        monthly, overhead = api_monthly_cost(inputs, baseline, estimate.requests_month)
        # Cache groups make the bill piecewise linear; find the first whole request.
        low, high = 0, 1
        while api_monthly_cost(inputs, baseline, high)[0] < estimate.total_monthly_usd:
            high *= 2
        while low + 1 < high:
            middle = low + (high - low) // 2
            if api_monthly_cost(inputs, baseline, middle)[0] >= estimate.total_monthly_usd:
                high = middle
            else:
                low = middle
        rows.append(
            APIComparison(
                baseline=baseline,
                monthly_usd=monthly,
                cache_overhead_usd=overhead,
                per_thousand_requests_usd=monthly / estimate.requests_month * 1000,
                break_even_requests=float(high),
                break_even_fits=(high * inputs.output_tokens_request <= estimate.capacity_tokens_month),
                mode_note=_api_mode_note(inputs, baseline),
                request_issue=api_request_issue(inputs, baseline),
            ),
        )
    return tuple(rows)


def _hosting_tasks(
    inputs: HostingInputs,
    estimate: HostingEstimate,
    baselines: tuple[APIBaseline, ...],
) -> tuple[TaskComparison, ...]:
    rows: list[TaskComparison] = []
    for index, quality in enumerate(inputs.quality):
        requests = inputs.tasks_per_month * quality.calls_per_task
        accepted = inputs.tasks_per_month * quality.acceptance_percent / 100
        model_usd = estimate.total_monthly_usd
        request_issue = estimate.context_issue
        if not estimate.topology_confirmed:
            request_issue = "Multi-host serving needs pilot measurements from this configuration"
        fits = not request_issue and requests * inputs.output_tokens_request <= estimate.capacity_tokens_month
        name = "Your GKE fleet"
        if index > 0:
            name = baselines[index - 1].name
            model_usd = api_monthly_cost(inputs, baselines[index - 1], requests)[0]
            request_issue = api_request_issue(inputs, baselines[index - 1])
            fits = not request_issue
        review_usd = inputs.tasks_per_month * quality.review_minutes / 60 * inputs.review_hourly_usd
        rows.append(
            TaskComparison(
                id=f"quality-{index}",
                name=name,
                quality=quality,
                requests=requests,
                accepted=accepted,
                model_usd=model_usd,
                review_usd=review_usd,
                per_accepted_usd=(model_usd + review_usd) / accepted if accepted else 0,
                fits=fits,
                request_issue=request_issue,
            ),
        )
    return tuple(rows)


def _hosting_decision(
    model: FrontierModel,
    node: GKENodePool,
    estimate: HostingEstimate,
) -> str:
    if model.license_class != "Permissive":
        return "Review commercial terms"
    if estimate.nodes_per_replica > 1:
        return "Validate multi-node serving"
    if estimate.required_memory_gb < node.vram_gb * 0.25:
        return "Right-size the node pool"
    return "Pilot on this topology"


def _demand_label(inputs: HostingInputs) -> str:
    for preset in DEMAND_PRESETS:
        if (
            inputs.requests_per_day == preset.requests_per_day
            and inputs.active_days == preset.active_days
            and inputs.input_tokens_request == preset.input_tokens
            and inputs.output_tokens_request == preset.output_tokens
        ):
            return preset.name
    return "Custom demand"


def _hosting_latency(inputs: HostingInputs) -> tuple[str, str]:
    measurements_complete = pilot_measurements_complete(inputs)
    if measurements_complete and not inputs.pilot_config:
        return (
            "Confirm which configuration produced this pilot",
            "Re-submit the latency measurements to bind them to the current model, hardware, precision, and workload.",
        )
    if (
        inputs.measured_concurrency < inputs.concurrency
        or inputs.measured_first_token == 0
        or inputs.measured_completion == 0
    ):
        return (
            "Responsiveness is still unproved",
            "Record p95 first-token and completion times at your target concurrency using this configuration.",
        )
    if inputs.measured_first_token > inputs.target_first_token or inputs.measured_completion > inputs.target_completion:
        return (
            "The recorded pilot misses a latency target",
            "Revisit batching, replicas, or model size, then measure again.",
        )
    return (
        "The recorded pilot meets your latency targets",
        "Both p95 measurements meet your targets at the recorded concurrency; production performance remains unproved.",
    )


def _hosting_sensitivity(
    inputs: HostingInputs,
    baselines: tuple[APIBaseline, ...],
) -> tuple[SensitivityRow, ...]:
    labels = ("Lower demand · ½×", "Your demand · 1×", "Higher demand · 2×")
    rows: list[SensitivityRow] = []
    for row_index, demand in enumerate((0.5, 1, 2)):
        cells: list[SensitivityCell] = []
        for speed in (0.5, 1, 2):
            scenario = replace(
                inputs,
                requests_per_day=min(10_000_000, max(1, inputs.requests_per_day * demand)),
                tokens_per_second=min(1_000_000, max(0.1, inputs.tokens_per_second * speed)),
            )
            if inputs.pilot_config and pilot_configuration_id(scenario) != inputs.pilot_config:
                scenario = replace(
                    scenario,
                    measured_concurrency=0,
                    measured_first_token=0,
                    measured_completion=0,
                    pilot_config="",
                )
            estimate = estimate_hosting(
                find_model(inputs.model_id),
                find_node_pool(inputs.node_pool_id),
                find_quantization(inputs.quantization_id),
                scenario,
            )
            cheapest = min(api_monthly_cost(scenario, baseline, estimate.requests_month)[0] for baseline in baselines)
            verdict = "API costs less"
            if estimate.total_monthly_usd <= cheapest:
                verdict = "Fleet has a cost case"
            if not estimate.demand_fits:
                verdict = "Fleet too small"
            cells.append(
                SensitivityCell(
                    url=hosting_url(scenario),
                    verdict=verdict,
                    inputs=scenario,
                    capacity_pct=estimate.demand_capacity_pct,
                    cheapest_api_usd=cheapest,
                    fits=estimate.qualified,
                ),
            )
        rows.append(SensitivityRow(labels[row_index], tuple(cells)))
    return tuple(rows)


def build_llm_self_hosting_view(
    query: Query | None = None,
    *,
    now: datetime | None = None,
) -> LLMSelfHostingView:
    query = query or {}
    now = now or datetime.now(UTC)
    inputs, parsed_validation = parse_inputs(query)
    validation = list(parsed_validation)
    model = find_model(inputs.model_id)
    node = find_node_pool(inputs.node_pool_id)
    quantization = find_quantization(inputs.quantization_id)
    estimate = estimate_hosting(model, node, quantization, inputs)
    if estimate.context_issue and estimate.context_issue not in validation:
        validation.append(estimate.context_issue)
    baselines = current_api_baselines(now, inputs)
    review_date = utc_date(now)
    apis = tuple(
        replace(
            comparison,
            needs_review=review_date >= comparison.baseline.review_on,
            freshness=(
                f"Verified {comparison.baseline.verified_on} · review by "
                f"{comparison.baseline.review_on}"
                + (
                    " · review overdue: check the linked price before deciding"
                    if review_date >= comparison.baseline.review_on
                    else ""
                )
            ),
        )
        for comparison in _compare_apis(inputs, estimate, baselines)
    )
    latency_title, latency_detail = _hosting_latency(inputs)
    current_pilot_config = pilot_configuration_id(inputs)
    precisions = tuple(PrecisionComparison(item, estimate_hosting(model, node, item, inputs)) for item in QUANTIZATIONS)
    comparisons: list[ModelComparison] = []
    for candidate in FRONTIER_MODELS:
        candidate_estimate = estimate_hosting(candidate, node, quantization, inputs)
        comparisons.append(
            ModelComparison(
                candidate,
                candidate_estimate,
                _hosting_decision(candidate, node, candidate_estimate),
            ),
        )
    return LLMSelfHostingView(
        inputs=inputs,
        models=FRONTIER_MODELS,
        node_pools=GKE_NODE_POOLS,
        quantizations=QUANTIZATIONS,
        selected_model=model,
        selected_node=node,
        selected_price=node.price(inputs.billing_plan),
        hardware_guidance=HardwareGuidance(find_node_pool(model.minimum_node_id), model.minimum_nodes),
        selected_quant=quantization,
        estimate=estimate,
        comparison=tuple(comparisons),
        validation=tuple(validation),
        snapshot_date=MODEL_SNAPSHOT,
        index_version=INDEX_VERSION,
        presets=DEMAND_PRESETS,
        apis=apis,
        precisions=precisions,
        demand_label=_demand_label(inputs),
        cost_plot=hosting_cost_plot(inputs, estimate, apis),
        sensitivity=_hosting_sensitivity(inputs, baselines),
        tasks=_hosting_tasks(inputs, estimate, baselines),
        latency_title=latency_title,
        latency_detail=latency_detail,
        model_source_url=MODEL_SOURCE_URL,
        gke_source_url=GKE_SOURCE_URL,
        price_source_url=PRICE_SOURCE_URL,
        current_pilot_config=current_pilot_config,
        comparison_ready=estimate.qualified and any(not row.request_issue for row in apis),
    )
