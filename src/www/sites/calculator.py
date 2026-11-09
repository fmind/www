"""Self-hosting calculator."""

from dataclasses import replace
from datetime import UTC, datetime

from .capacity import MONTHLY_HOURS, replicas_for_demand
from .charts import hosting_cost_plot
from .data import (
    DEMAND_PRESETS,
    FLEX_START_SOURCE_URL,
    FRONTIER_MODELS,
    GKE_NODE_POOLS,
    GKE_SOURCE_URL,
    MODEL_SNAPSHOT,
    PRICE_SOURCE_URL,
    QUANTIZATIONS,
)
from .economics import (
    CLUSTER_HOURLY_USD,
    api_monthly_cost,
    api_request_issue,
    current_api_baselines,
    estimate_hosting,
    hosting_verdict,
    pilot_measurements_complete,
    utc_date,
)
from .formatting import format_decimal, format_usd2
from .inputs import (
    Query,
    automatic_node,
    automatic_setup,
    configuration_issue,
    demand_preset,
    find_model,
    find_node_pool,
    find_quantization,
    first_value,
    hosting_url,
    parse_inputs,
    pilot_configuration_id,
    scenario_parameters,
    without_pilot_evidence,
)
from .models import (
    AcceleratorComparison,
    APIBaseline,
    APIComparison,
    APIMode,
    BillingPlan,
    FrontierModel,
    GKENodePool,
    HostingEstimate,
    HostingInputs,
    LLMSelfHostingView,
    ModelComparison,
    PlanAlternative,
    PrecisionComparison,
    SensitivityCell,
    SensitivityRow,
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
                f"Explicit cache: {format_usd2(baseline.cache_read_per_million)}/M "
                f"cached input + {format_usd2(baseline.cache_storage_per_million_hour)}/M "
                f"token-hours stored; {baseline.cache_retention} is charged for every group. "
                "Implicit cache hits are not assumed."
            )
        return (
            f"Cache: {format_usd2(baseline.cache_write_per_million)}/M prefix tokens "
            f"on the first call, {format_usd2(baseline.cache_read_per_million)}/M on "
            f"reuse. Calls must share an exact prefix while it stays cached ({baseline.cache_retention})."
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
                break_even_fits=(
                    not estimate.compatibility_issue
                    and not estimate.context_issue
                    and estimate.topology_confirmed
                    and high * inputs.output_tokens_request <= estimate.capacity_tokens_month
                    and high <= estimate.capacity_requests_day * inputs.active_days
                ),
                mode_note=_api_mode_note(inputs, baseline),
                request_issue=api_request_issue(inputs, baseline),
            ),
        )
    return tuple(rows)


def _hosting_decision(
    model: FrontierModel,
    node: GKENodePool,
    estimate: HostingEstimate,
) -> str:
    if estimate.compatibility_issue:
        return "Unsupported configuration"
    if model.license_class != "Permissive":
        return "Review commercial terms"
    if estimate.nodes_per_replica > 1:
        return "Validate multi-node serving"
    if estimate.required_memory_gb < node.vram_gb * 0.25:
        return "Right-size the node pool"
    return "Pilot on this topology"


def _catalog_comparison(inputs: HostingInputs, model: FrontierModel) -> ModelComparison:
    """Size a catalog model on its own lowest-cost machine, keeping the visitor's plan and workload."""
    scenario = replace(inputs, model_id=model.id, quantization_id=model.default_quantization)
    issue = ""
    try:
        scenario, node = automatic_setup(scenario, inputs.billing_plan)
    except ValueError as exc:
        # No machine offers this plan for any checkpoint; the visitor's node offers it,
        # so the row can still be estimated and is reported as unsupported.
        node = find_node_pool(inputs.node_pool_id)
        issue = str(exc)
    scenario = replace(scenario, node_pool_id=node.id)
    quantization = find_quantization(scenario.quantization_id)
    estimate = estimate_hosting(model, node, quantization, scenario)
    if issue:
        estimate = replace(estimate, compatibility_issue=issue, qualified=False)
    return ModelComparison(
        model=model,
        quantization=quantization,
        node=node,
        estimate=estimate,
        decision=_hosting_decision(model, node, estimate),
    )


def _demand_label(inputs: HostingInputs) -> str:
    if inputs.mode == "simple":
        preset = demand_preset(inputs)
        return preset.name + (" · custom volume" if inputs.requests_per_day != preset.requests_per_day else "")
    # Unlike demand_preset, advanced mode also matches volume and names a custom mix.
    demand = (inputs.requests_per_day, inputs.active_days, inputs.input_tokens_request, inputs.output_tokens_request)
    return next(
        (
            preset.name
            for preset in DEMAND_PRESETS
            if demand == (preset.requests_per_day, preset.active_days, preset.input_tokens, preset.output_tokens)
        ),
        "Custom demand",
    )


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


# hosting_verdict names the first blocker, so a cell's verdict agrees with its qualified styling.
_SENSITIVITY_VERDICTS = {
    "unsupported": "Unsupported configuration",
    "context": "Exceeds model context",
    "topology": "Needs a multi-host pilot",
    "capacity": "Fleet too small",
    "no-api": "No API accepts this request",
    "api-cheaper": "API costs less",
    "fleet-case": "Fleet has a cost case",
}


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
                mode="advanced",
                requests_per_day=min(10_000_000, max(1, inputs.requests_per_day * demand)),
                tokens_per_second=min(1_000_000, max(0.1, inputs.tokens_per_second * speed)),
            )
            # Unbound measurements stay, as on the page itself; bound ones must match the cell.
            if inputs.pilot_config and pilot_configuration_id(scenario) != inputs.pilot_config:
                scenario = without_pilot_evidence(scenario)
            estimate = estimate_hosting(
                find_model(inputs.model_id),
                find_node_pool(inputs.node_pool_id),
                find_quantization(inputs.quantization_id),
                scenario,
            )
            # Only APIs that accept this request can be the lowest-cost alternative.
            cheapest = min(
                (
                    api_monthly_cost(scenario, baseline, estimate.requests_month)[0]
                    for baseline in baselines
                    if not api_request_issue(scenario, baseline)
                ),
                default=None,
            )
            cells.append(
                SensitivityCell(
                    url=hosting_url(scenario),
                    verdict=_SENSITIVITY_VERDICTS[hosting_verdict(estimate, cheapest)],
                    inputs=scenario,
                    capacity_pct=estimate.demand_capacity_pct,
                    cheapest_api_usd=cheapest,
                    fits=estimate.qualified,
                ),
            )
        rows.append(SensitivityRow(labels[row_index], tuple(cells)))
    return tuple(rows)


def _hosting_accelerators(
    inputs: HostingInputs,
    model: FrontierModel,
) -> tuple[AcceleratorComparison, ...]:
    """Compare the lowest-cost compatible GPU and Cloud TPU fleets for this demand."""
    families = (
        ("GPU", tuple(pool for pool in GKE_NODE_POOLS if pool.chip == "GPU")),
        ("Cloud TPU", tuple(pool for pool in GKE_NODE_POOLS if pool.chip == "TPU")),
    )
    # An unsupported precision cannot be sized; start from the model's default checkpoint.
    start = (
        inputs
        if inputs.quantization_id in model.supported_quantizations
        else replace(inputs, quantization_id=model.default_quantization)
    )
    rows: list[AcceleratorComparison] = []
    for family, pools in families:
        chosen_plan = target_plan = inputs.billing_plan
        try:
            candidate, chosen_node = automatic_setup(start, target_plan, pools=pools)
            matched_hardware = True
        except ValueError:
            # Placeholder row: the family's first machine, on a plan it publishes.
            candidate, chosen_node, matched_hardware = start, pools[0], False
            if all(price.plan is not target_plan for price in chosen_node.prices):
                chosen_plan = chosen_node.prices[0].plan
        chosen_quant = find_quantization(candidate.quantization_id)
        scenario = replace(
            inputs,
            mode="advanced",
            node_pool_id=chosen_node.id,
            quantization_id=chosen_quant.id,
            billing_plan=chosen_plan,
        )
        if pilot_configuration_id(scenario) != pilot_configuration_id(inputs):
            scenario = without_pilot_evidence(scenario)
        estimate = estimate_hosting(model, chosen_node, chosen_quant, scenario)
        if not matched_hardware:
            # pools[0] is only a placeholder: report a reason shared by every machine that offers the plan.
            reasons = {
                configuration_issue(
                    replace(start, node_pool_id=pool.id, billing_plan=target_plan),
                    check_workload=False,
                )
                for pool in pools
                if any(price.plan is target_plan for price in pool.prices)
            }
            estimate = replace(
                estimate,
                compatibility_issue=reasons.pop()
                if len(reasons) == 1
                else f"No {family} machine in this catalog has a verified {model.name} configuration for these settings",
                qualified=False,
            )
        rows.append(
            AcceleratorComparison(
                family=family,
                quantization=chosen_quant,
                node=chosen_node,
                estimate=estimate,
                url=hosting_url(scenario),
            )
        )
    return tuple(rows)


def _plan_alternatives(inputs: HostingInputs, model: FrontierModel) -> tuple[PlanAlternative, ...]:
    """Price the simple scenario on every other plan it may use, as selecting that plan would."""
    preset = demand_preset(inputs)
    rows: list[PlanAlternative] = []
    for plan in BillingPlan:
        if plan is inputs.billing_plan or (plan is BillingPlan.FLEX and preset.api_mode is not APIMode.BATCH):
            continue
        try:
            scenario, node = automatic_setup(replace(inputs, quantization_id=model.default_quantization), plan)
        except ValueError:
            continue
        scenario = replace(scenario, node_pool_id=node.id, billing_plan=plan)
        if configuration_issue(scenario):
            continue
        estimate = estimate_hosting(model, node, find_quantization(scenario.quantization_id), scenario)
        rows.append(PlanAlternative(node.price(plan).label, estimate.total_monthly_usd, hosting_url(scenario)))
    return tuple(sorted(rows, key=lambda row: row.monthly_usd))


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
    preset = demand_preset(inputs)
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
    precisions = []
    for item in QUANTIZATIONS:
        if item.id not in model.supported_quantizations:
            continue
        scenario = replace(
            inputs,
            mode="advanced",
            quantization_id=item.id,
        )
        try:
            precision_node = automatic_node(scenario, inputs.billing_plan)
        except ValueError:
            precision_node = node
        scenario = replace(scenario, node_pool_id=precision_node.id)
        if pilot_configuration_id(scenario) != current_pilot_config:
            scenario = without_pilot_evidence(scenario)
        precisions.append(
            PrecisionComparison(
                item, estimate_hosting(model, precision_node, item, scenario), precision_node, hosting_url(scenario)
            )
        )
    budgets = []
    for speed in (0.5, 2):
        scenario = replace(inputs, tokens_per_second=inputs.tokens_per_second * speed)
        scenario = replace(scenario, replicas=replicas_for_demand(scenario))
        budgets.append(estimate_hosting(model, node, quantization, scenario).total_monthly_usd)
    return LLMSelfHostingView(
        inputs=inputs,
        models=FRONTIER_MODELS,
        node_pools=GKE_NODE_POOLS,
        quantizations=QUANTIZATIONS,
        selected_model=model,
        selected_node=node,
        selected_price=node.price(inputs.billing_plan),
        selected_quant=quantization,
        estimate=estimate,
        comparison=tuple(_catalog_comparison(inputs, candidate) for candidate in FRONTIER_MODELS),
        validation=tuple(validation),
        snapshot_date=MODEL_SNAPSHOT,
        presets=DEMAND_PRESETS,
        apis=apis,
        precisions=tuple(precisions),
        accelerators=_hosting_accelerators(inputs, model),
        demand_label=_demand_label(inputs),
        selected_preset=preset,
        window_is_auto=first_value(query, "window") in (None, "auto"),
        billing_is_auto=first_value(query, "billing") in (None, "", "auto"),
        plan_alternatives=_plan_alternatives(inputs, model) if inputs.mode == "simple" else (),
        flex_start_source_url=FLEX_START_SOURCE_URL,
        custom_requests=inputs.requests_per_day != preset.requests_per_day,
        budget_low_usd=min(budgets),
        budget_high_usd=max(budgets),
        cost_plot=hosting_cost_plot(inputs, estimate, apis),
        sensitivity=_hosting_sensitivity(inputs, baselines),
        latency_title=latency_title,
        latency_detail=latency_detail,
        model_source_url=next(
            (url for precision, url in model.checkpoint_urls if precision == quantization.id), model.weights_url
        ),
        gke_source_url=GKE_SOURCE_URL,
        cluster_hourly_usd=CLUSTER_HOURLY_USD,
        monthly_hours=MONTHLY_HOURS,
        price_source_url=PRICE_SOURCE_URL,
        current_pilot_config=current_pilot_config,
        comparison_ready=estimate.qualified and any(not row.request_issue for row in apis),
        form_values=scenario_parameters(replace(inputs, mode="advanced")),
        advanced_url=hosting_url(replace(inputs, mode="advanced")),
        simple_url=hosting_url(
            replace(
                inputs,
                mode="simple",
                # Simple mode offers Flex-start to batch workloads only.
                billing_plan=BillingPlan.ON_DEMAND
                if inputs.billing_plan is BillingPlan.FLEX and preset.api_mode is not APIMode.BATCH
                else inputs.billing_plan,
            )
        ),
    )
