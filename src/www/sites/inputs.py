"""Self-hosting calculator inputs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
from math import ceil, isfinite
from re import fullmatch
from urllib.parse import urlencode

from .capacity import MONTHLY_HOURS, replicas_for_demand
from .data import (
    DEFAULT_HOSTING_INPUTS,
    DEMAND_PRESETS,
    FRONTIER_MODELS,
    GKE_NODE_POOLS,
    QUANTIZATIONS,
)
from .models import (
    APIMode,
    BillingPlan,
    DemandPreset,
    FrontierModel,
    GKENodePool,
    HostingInputs,
    Quantization,
    TaskQuality,
)

type QueryValue = str | Sequence[str]
type Query = Mapping[str, QueryValue]


def _first(query: Query, key: str) -> str | None:
    raw = query.get(key)
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    return raw[0] if raw else None


def _format_bound(value: float) -> str:
    # Plain digits, never exponent notation, so bounds read like the whole-number messages.
    return format(Decimal(repr(value)).normalize(), "f")


def _parse_choice(
    query: Query,
    key: str,
    fallback: str,
    allowed: frozenset[str],
    validation: list[str],
) -> str:
    raw = _first(query, key)
    if raw is None or raw == "":
        return fallback
    if raw in allowed:
        return raw
    validation.append(f"{key} was not recognized; the default was used")
    return fallback


def _parse_bounded_float(
    query: Query,
    key: str,
    fallback: float,
    minimum: float,
    maximum: float,
    validation: list[str],
    *,
    minimum_positive: float = 0,
) -> float:
    raw = _first(query, key)
    if raw is None or raw == "":
        return fallback
    try:
        # float() also accepts underscores, non-ASCII digits, and inf/nan spellings.
        if fullmatch(r"[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", raw) is None:
            raise ValueError
        value = float(raw)
    except ValueError:
        value = float("nan")
    if not isfinite(value) or value < minimum or value > maximum:
        validation.append(
            f"{key} must be between {_format_bound(minimum)} and {_format_bound(maximum)}; the default was used",
        )
        return fallback
    # Reject tiny nonzero ratios before division, including values that float()
    # underflows to zero. Literal zero remains valid for no accepted tasks.
    if value < minimum_positive and any(digit in "123456789" for digit in raw.lower().partition("e")[0]):
        validation.append(
            f"{key} must be zero or at least {minimum_positive:.7f}; the default was used",
        )
        return fallback
    return value


def _parse_bounded_int(
    query: Query,
    key: str,
    fallback: int,
    minimum: int,
    maximum: int,
    validation: list[str],
) -> int:
    raw = _first(query, key)
    if raw is None or raw == "":
        return fallback
    try:
        # strconv.Atoi accepts only integer syntax, never decimal-valued floats.
        if fullmatch(r"[+-]?[0-9]+", raw) is None:
            raise ValueError
        value = int(raw, 10)
    except ValueError:
        value = minimum - 1
    if value < minimum or value > maximum:
        validation.append(
            f"{key} must be a whole number between {minimum} and {maximum}; the default was used",
        )
        return fallback
    return value


def _parse_bounded_count(
    query: Query,
    key: str,
    fallback: float,
    minimum: int,
    maximum: int,
    validation: list[str],
) -> float:
    """Parse a whole quantity stored as a float, matching the form's integer step."""
    # The out-of-range marker distinguishes a missing or rejected value from a parsed one.
    marker = minimum - 1
    value = _parse_bounded_int(query, key, marker, minimum, maximum, validation)
    return fallback if value == marker else float(value)


def _apply_demand_preset(
    preset_id: str | None,
    inputs: HostingInputs,
    validation: list[str],
) -> HostingInputs:
    if not preset_id:
        return inputs
    for preset in DEMAND_PRESETS:
        if preset.id == preset_id:
            return replace(
                inputs,
                requests_per_day=preset.requests_per_day,
                active_days=preset.active_days,
                input_tokens_request=preset.input_tokens,
                output_tokens_request=preset.output_tokens,
            )
    validation.append("preset was not recognized; the validated demand inputs were kept")
    return inputs


def parse_inputs(query: Query) -> tuple[HostingInputs, tuple[str, ...]]:
    validation: list[str] = []
    if "platform" in query:
        validation.append("Operations budget is no longer included; totals cover GPU compute and the GKE fee")
    defaults = DEFAULT_HOSTING_INPUTS
    preset = next(
        (item for item in DEMAND_PRESETS if item.id == (_first(query, "preset") or "small-team")), DEMAND_PRESETS[1]
    )
    advanced_keys = (scenario_parameters(defaults).keys() | {"quality", "pilot", "confirm-pilot"}) - {
        "model",
        "billing",
        "mode",
        "preset",
        "window",
    }
    mode = _parse_choice(
        query,
        "mode",
        "advanced" if query.keys() & advanced_keys else "simple",
        frozenset(("simple", "advanced")),
        validation,
    )
    if mode == "simple" and query.keys() & (advanced_keys - {"requests"}):
        validation.append("Advanced parameters require advanced mode; simple defaults were used")
    # Previously shared URLs encoded the A4 billing plan in the hardware ID.
    legacy_plan = {"a4-cud-3y": "cud-3y", "a4-flex": "flex"}.get(_first(query, "node") or "")
    if legacy_plan:
        query = dict(query)
        query["node"] = "a4"
        if not _first(query, "billing"):
            query["billing"] = legacy_plan
    model_id = _parse_choice(
        query, "model", defaults.model_id, frozenset(model.id for model in FRONTIER_MODELS), validation
    )
    demand_window_hours = (
        float(_parse_choice(query, "window", str(int(preset.window_hours)), frozenset(("24", "8", "1")), validation))
        if mode == "simple" and _first(query, "window") != "auto"
        else preset.window_hours
        if mode == "simple"
        else _parse_bounded_float(query, "window", defaults.demand_window_hours, 0.1, 24, validation)
    )
    quantization_id = _parse_choice(
        query,
        "quant",
        find_model(model_id).default_quantization,
        frozenset(quant.id for quant in QUANTIZATIONS) | {"auto"},
        validation,
    )
    if quantization_id == "auto":
        quantization_id = find_model(model_id).default_quantization
    inputs = replace(
        defaults,
        mode=mode,
        model_id=model_id,
        node_pool_id=_parse_choice(
            query, "node", defaults.node_pool_id, frozenset(node.id for node in GKE_NODE_POOLS) | {"auto"}, validation
        ),
        quantization_id=quantization_id,
        demand_window_hours=demand_window_hours,
        replicas=_parse_bounded_int(query, "replicas", defaults.replicas, 1, 100_000, validation),
        duty_cycle_percent=_parse_bounded_float(
            query,
            "duty",
            defaults.duty_cycle_percent,
            0.1,
            100,
            validation,
        ),
        memory_overhead_pct=_parse_bounded_float(
            query,
            "overhead",
            defaults.memory_overhead_pct,
            0,
            50,
            validation,
        ),
        tokens_per_second=_parse_bounded_float(
            query,
            "throughput",
            defaults.tokens_per_second,
            0.1,
            1_000_000,
            validation,
        ),
        target_utilization=_parse_bounded_float(
            query,
            "utilization",
            defaults.target_utilization,
            1,
            95,
            validation,
        ),
        output_tokens_request=_parse_bounded_count(
            query,
            "tokens",
            defaults.output_tokens_request,
            1,
            1_000_000,
            validation,
        ),
        input_tokens_request=_parse_bounded_count(
            query,
            "input-tokens",
            defaults.input_tokens_request,
            1,
            1_000_000,
            validation,
        ),
        requests_per_day=(
            _parse_bounded_float(query, "requests", defaults.requests_per_day, 1, 10_000_000, validation)
            if mode == "advanced"
            else defaults.requests_per_day
        ),
        active_days=_parse_bounded_count(
            query,
            "days",
            defaults.active_days,
            1,
            31,
            validation,
        ),
    )
    if mode == "simple":
        inputs = replace(
            defaults,
            mode=mode,
            model_id=inputs.model_id,
            demand_window_hours=inputs.demand_window_hours,
            quantization_id=find_model(inputs.model_id).default_quantization,
        )
    inputs = _apply_demand_preset(_first(query, "preset"), inputs, validation)
    if mode == "simple":
        inputs = replace(
            inputs,
            requests_per_day=_parse_bounded_float(
                query, "requests", inputs.requests_per_day, 1, 10_000_000, validation
            ),
            duty_cycle_percent=min(100, inputs.active_days * inputs.demand_window_hours / MONTHLY_HOURS * 100)
            if preset.scheduled
            else 100,
        )
        inputs = replace(inputs, replicas=replicas_for_demand(inputs))
    if mode == "advanced":
        inputs = _parse_hosting_options(query, inputs, validation)
    if mode == "simple" or _first(query, "node") in (None, "auto"):
        allowed_plans = frozenset(("on-demand", "cud-1y", "cud-3y"))
        if mode == "advanced":
            allowed_plans |= {"flex"}
        raw_billing = _parse_choice(query, "billing", "on-demand", allowed_plans, validation)
        try:
            node = automatic_node(inputs, BillingPlan(raw_billing))
        except ValueError as exc:
            if mode == "simple":
                validation.append(f"{exc}; the default model was used")
                inputs = replace(inputs, model_id=defaults.model_id, quantization_id=defaults.quantization_id)
                node = automatic_node(inputs, BillingPlan(raw_billing))
            else:
                validation.append(f"{exc}; select a compatible checkpoint, GPU and billing plan")
                node = find_node_pool(defaults.node_pool_id)
        inputs = replace(inputs, node_pool_id=node.id)
    node = find_node_pool(inputs.node_pool_id)
    raw_plan = _first(query, "billing")
    available_plans = frozenset(price.plan.value for price in node.prices)
    plan = node.prices[0].plan.value
    if raw_plan and raw_plan not in available_plans:
        validation.append(
            f"{node.name} does not offer the {raw_plan} billing plan; {node.prices[0].label} was used",
        )
    elif raw_plan:
        plan = raw_plan
    inputs = replace(inputs, billing_plan=BillingPlan(plan))
    issue = configuration_issue(inputs)
    if issue:
        validation.append(issue)
    return _bind_pilot_measurements(query, inputs, validation), tuple(validation)


def _parse_hosting_options(
    query: Query,
    inputs: HostingInputs,
    validation: list[str],
) -> HostingInputs:
    api_mode = _parse_choice(
        query,
        "api-mode",
        inputs.api_mode.value,
        frozenset(mode.value for mode in APIMode),
        validation,
    )
    inputs = replace(
        inputs,
        api_mode=APIMode(api_mode),
        cache_requests=_parse_bounded_int(
            query,
            "cache-requests",
            inputs.cache_requests,
            1,
            1_000_000,
            validation,
        ),
        concurrency=_parse_bounded_int(
            query,
            "concurrency",
            inputs.concurrency,
            1,
            100_000,
            validation,
        ),
        measured_concurrency=_parse_bounded_int(
            query,
            "measured-concurrency",
            inputs.measured_concurrency,
            0,
            100_000,
            validation,
        ),
    )
    inputs = replace(
        inputs,
        quality_enabled=(
            _parse_choice(
                query,
                "quality",
                "off",
                frozenset(("on", "off")),
                validation,
            )
            == "on"
        ),
    )
    count_fields = (
        ("cache_prefix_tokens", "cache-prefix", 0, 1_000_000),
        ("tasks_per_month", "tasks", 1, 10_000_000),
    )
    for attribute, key, minimum, maximum in count_fields:
        inputs = replace(
            inputs,
            **{
                attribute: _parse_bounded_count(
                    query,
                    key,
                    getattr(inputs, attribute),
                    minimum,
                    maximum,
                    validation,
                ),
            },
        )
    float_fields = (
        ("target_first_token", "target-first", 0.1, 3600),
        ("target_completion", "target-complete", 0.1, 86_400),
        ("measured_first_token", "measured-first", 0, 3600),
        ("measured_completion", "measured-complete", 0, 86_400),
        ("review_hourly_usd", "review-rate", 0, 10_000),
    )
    for attribute, key, minimum, maximum in float_fields:
        inputs = replace(
            inputs,
            **{
                attribute: _parse_bounded_float(
                    query,
                    key,
                    getattr(inputs, attribute),
                    minimum,
                    maximum,
                    validation,
                ),
            },
        )
    qualities: list[TaskQuality] = []
    for index, quality in enumerate(inputs.quality):
        prefix = f"quality-{index}-"
        qualities.append(
            TaskQuality(
                acceptance_percent=_parse_bounded_float(
                    query,
                    prefix + "acceptance",
                    quality.acceptance_percent,
                    0,
                    100,
                    validation,
                    minimum_positive=0.0000001,
                ),
                calls_per_task=_parse_bounded_float(
                    query,
                    prefix + "calls",
                    quality.calls_per_task,
                    1,
                    100,
                    validation,
                ),
                review_minutes=_parse_bounded_float(
                    query,
                    prefix + "review",
                    quality.review_minutes,
                    0,
                    480,
                    validation,
                ),
            ),
        )
    inputs = replace(inputs, quality=tuple(qualities))
    if (
        inputs.measured_first_token > 0
        and inputs.measured_completion > 0
        and inputs.measured_first_token > inputs.measured_completion
    ):
        validation.append(
            "Recorded first-token time cannot exceed completion time; both measurements were cleared",
        )
        inputs = replace(inputs, measured_first_token=0, measured_completion=0)
    return inputs


def find_model(model_id: str) -> FrontierModel:
    return next((model for model in FRONTIER_MODELS if model.id == model_id), FRONTIER_MODELS[0])


def find_node_pool(node_id: str) -> GKENodePool:
    return next((node for node in GKE_NODE_POOLS if node.id == node_id), GKE_NODE_POOLS[0])


def find_quantization(quantization_id: str) -> Quantization:
    return next(
        (item for item in QUANTIZATIONS if item.id == quantization_id),
        QUANTIZATIONS[0],
    )


def configuration_issue(inputs: HostingInputs, *, check_workload: bool = True) -> str:
    """Fail closed on known checkpoint, kernel, topology and delivery constraints."""
    model = find_model(inputs.model_id)
    node = find_node_pool(inputs.node_pool_id)
    quantization = find_quantization(inputs.quantization_id)
    if model.deployment_issue:
        return model.deployment_issue
    if quantization.id not in model.supported_quantizations:
        return f"{model.name} has no verified {quantization.name} checkpoint in this catalog"
    if model.required_node_ids and node.id not in model.required_node_ids:
        return f"{model.name} requires one of the verified node families: {', '.join(model.required_node_ids)}"
    if quantization.id == "fp8" and node.id == "a2-ultra-1g":
        return (
            "A100 does not support the selected native FP8 W8A8 kernels; choose 16-bit or an Ada/Hopper/Blackwell GPU"
        )
    if (
        quantization.id == "nvfp4"
        and node.id not in ("g4-standard-48", "a4")
        and not (model.id == "inkling" and node.id == "a3-ultra")
    ):
        return f"{quantization.name} requires Blackwell hardware in this conservative compatibility snapshot"
    for node_id, context_limit in model.node_context_limits:
        if (
            check_workload
            and node.id == node_id
            and inputs.input_tokens_request + inputs.output_tokens_request > context_limit
        ):
            return f"The verified {model.name} recipe on {node.name} is limited to {context_limit:,} context tokens"
    required = weight_memory_gb(model, quantization) * (1 + inputs.memory_overhead_pct / 100)
    if ceil(required / node.vram_gb) > 1 and not node.multi_host:
        return (
            f"{model.name} does not fit on one {node.name}; this catalog does not support sharding across those nodes"
        )
    if inputs.billing_plan is BillingPlan.FLEX and inputs.api_mode is not APIMode.BATCH:
        return "Flex-start queues bounded jobs and does not support this interactive serving comparison; select batch or reserved capacity"
    return ""


def automatic_node(inputs: HostingInputs, plan: BillingPlan) -> GKENodePool:
    """Minimize published compute cost under the shared throughput assumption."""
    quant = find_quantization(inputs.quantization_id)
    model = find_model(inputs.model_id)
    required = weight_memory_gb(model, quant) * (1 + inputs.memory_overhead_pct / 100)
    candidates = [
        node
        for node in GKE_NODE_POOLS
        if any(price.plan is plan for price in node.prices)
        and not configuration_issue(replace(inputs, node_pool_id=node.id, billing_plan=plan), check_workload=False)
    ]
    if not candidates:
        raise ValueError(f"No compatible hardware for {model.name} under {plan}")
    workload_candidates = [
        node for node in candidates if not configuration_issue(replace(inputs, node_pool_id=node.id, billing_plan=plan))
    ]
    # If every recipe rejects the request, preserve a compatible checkpoint/GPU
    # so parse_inputs can report the actual context limit and reject the scenario.
    return min(
        workload_candidates or candidates,
        key=lambda node: (
            nodes_for_model(model, node, required) * node.price(plan).hourly_usd,
            nodes_for_model(model, node, required),
        ),
    )


def weight_memory_gb(model: FrontierModel, quantization: Quantization) -> float:
    """Published tensor bytes include mixed precision and quantization scales."""
    return next(
        (size for precision, size in model.checkpoint_memory if precision == quantization.id),
        model.parameters_b * quantization.bytes_per_param,
    )


def nodes_for_model(model: FrontierModel, node: GKENodePool, required_memory: float) -> int:
    minimum = next((count for node_id, count in model.node_minimums if node_id == node.id), 1)
    return max(minimum, ceil(required_memory / node.vram_gb))


def pilot_configuration_id(inputs: HostingInputs) -> str:
    """Return a stable identifier for the configuration behind pilot evidence."""
    values = (
        inputs.model_id,
        inputs.node_pool_id,
        inputs.quantization_id,
        str(inputs.replicas),
        _float_for_url(inputs.memory_overhead_pct),
        _float_for_url(inputs.tokens_per_second),
        _float_for_url(inputs.input_tokens_request),
        _float_for_url(inputs.output_tokens_request),
        str(inputs.concurrency),
    )
    return "v1-" + sha256("\0".join(values).encode()).hexdigest()[:24]


def _bind_pilot_measurements(
    query: Query,
    inputs: HostingInputs,
    validation: list[str],
) -> HostingInputs:
    current = pilot_configuration_id(inputs)
    saved = _first(query, "pilot") or ""
    confirmation = _first(query, "confirm-pilot") or ""
    measurements_present = any(
        (inputs.measured_concurrency, inputs.measured_first_token, inputs.measured_completion),
    )
    if not measurements_present:
        return replace(inputs, pilot_config="")
    if saved == current or confirmation == current:
        return replace(inputs, pilot_config=current)
    if saved or confirmation:
        validation.append("The pilot measurements belong to a different serving configuration; they were cleared")
        return replace(
            inputs,
            measured_concurrency=0,
            measured_first_token=0,
            measured_completion=0,
            pilot_config="",
        )
    return inputs


def _float_for_url(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    # repr is the shortest round-tripping form; Decimal expands its exponent
    # because Go's strconv.FormatFloat with the `f` verb never emits one.
    return format(Decimal(repr(value)), "f")


def demand_preset(inputs: HostingInputs) -> DemandPreset:
    """Match a workload's token mix and calendar while allowing custom volume."""
    return next(
        (
            preset
            for preset in DEMAND_PRESETS
            if (inputs.active_days, inputs.input_tokens_request, inputs.output_tokens_request)
            == (preset.active_days, preset.input_tokens, preset.output_tokens)
        ),
        DEMAND_PRESETS[1],
    )


def scenario_parameters(inputs: HostingInputs) -> dict[str, str]:
    """Serialize inputs exactly; URLs, agent parameters, and form values share this."""
    values = {
        "mode": inputs.mode,
        "model": inputs.model_id,
        "node": inputs.node_pool_id,
        "billing": inputs.billing_plan.value,
        "quant": inputs.quantization_id,
        "api-mode": inputs.api_mode.value,
        "replicas": str(inputs.replicas),
        "cache-requests": str(inputs.cache_requests),
        "concurrency": str(inputs.concurrency),
        "measured-concurrency": str(inputs.measured_concurrency),
        "duty": _float_for_url(inputs.duty_cycle_percent),
        "overhead": _float_for_url(inputs.memory_overhead_pct),
        "throughput": _float_for_url(inputs.tokens_per_second),
        "utilization": _float_for_url(inputs.target_utilization),
        "tokens": _float_for_url(inputs.output_tokens_request),
        "input-tokens": _float_for_url(inputs.input_tokens_request),
        "requests": _float_for_url(inputs.requests_per_day),
        "days": _float_for_url(inputs.active_days),
        "window": _float_for_url(inputs.demand_window_hours),
        "cache-prefix": _float_for_url(inputs.cache_prefix_tokens),
        "target-first": _float_for_url(inputs.target_first_token),
        "target-complete": _float_for_url(inputs.target_completion),
        "measured-first": _float_for_url(inputs.measured_first_token),
        "measured-complete": _float_for_url(inputs.measured_completion),
        "tasks": _float_for_url(inputs.tasks_per_month),
        "review-rate": _float_for_url(inputs.review_hourly_usd),
    }
    if inputs.quality_enabled:
        values["quality"] = "on"
    if inputs.pilot_config:
        values["pilot"] = inputs.pilot_config
    for index, quality in enumerate(inputs.quality):
        values[f"quality-{index}-acceptance"] = _float_for_url(
            quality.acceptance_percent,
        )
        values[f"quality-{index}-calls"] = _float_for_url(quality.calls_per_task)
        values[f"quality-{index}-review"] = _float_for_url(quality.review_minutes)
    if inputs.mode == "simple":
        values = {key: value for key, value in values.items() if key in {"mode", "model", "billing", "window"}}
        if inputs.demand_window_hours not in (24, 8, 1):
            values["window"] = "24"
        preset = demand_preset(inputs)
        values["preset"] = preset.id
        if inputs.requests_per_day != preset.requests_per_day:
            values["requests"] = _float_for_url(inputs.requests_per_day)
    return dict(sorted(values.items()))


def hosting_url(inputs: HostingInputs) -> str:
    return "/sites/llm-self-hosting/?" + urlencode(scenario_parameters(inputs))
