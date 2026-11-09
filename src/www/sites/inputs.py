"""Self-hosting calculator inputs."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
from math import ceil, isfinite
from re import fullmatch
from typing import Any
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
)

type QueryValue = str | Sequence[str]
type Query = Mapping[str, QueryValue]

# DEFAULT_HOSTING_INPUTS describes this workload; unmatched presets and token mixes fall back to it.
_DEFAULT_PRESET = next(preset for preset in DEMAND_PRESETS if preset.id == "small-team")


def _first(query: Query, key: str) -> str | None:
    raw = query.get(key)
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    return raw[0] if raw else None


def _format_bound(value: float) -> str:
    # Grouped plain digits, never exponent notation, so bounds read like the form's numbers.
    return format(Decimal(repr(value)).normalize(), ",f")


# Validation messages name the visible form label first and the query key second,
# so both website readers and MCP callers can find the field.
_FIELD_LABELS: dict[str, str] = {
    "api-mode": "API pricing mode",
    "billing": "Pricing plan",
    "cache-prefix": "Shared prefix tokens",
    "cache-requests": "Calls per cache group",
    "concurrency": "Target simultaneous requests",
    "days": "Active days per month",
    "duty": "Fleet running time (%)",
    "input-tokens": "Input tokens per request",
    "measured-complete": "Measured p95 completion",
    "measured-concurrency": "Pilot simultaneous requests",
    "measured-first": "Measured p95 first token",
    "model": "Model",
    "node": "GPU / TPU node",
    "overhead": "Runtime memory reserve (%)",
    "preset": "Workload",
    "quant": "Checkpoint precision",
    "replicas": "Serving replicas",
    "requests": "Calls per active day",
    "target-complete": "Target p95 completion",
    "target-first": "Target p95 first token",
    "throughput": "Assumed output tokens/s per replica",
    "tokens": "Output tokens per request",
    "utilization": "Usable share of throughput (%)",
    "window": "Usage window (hours/active day)",
}


def _field(key: str) -> str:
    label = _FIELD_LABELS.get(key)
    return f"{label} ({key})" if label else key


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
    validation.append(f"{_field(key)} was not recognized; the default was used")
    return fallback


def _parse_bounded_float(
    query: Query,
    key: str,
    fallback: float,
    minimum: float,
    maximum: float,
    validation: list[str],
) -> float:
    raw = _first(query, key)
    if raw is None or raw == "":
        return fallback
    try:
        # float() also accepts underscores, non-ASCII digits, and inf/nan spellings.
        if len(raw) > 128 or fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", raw) is None:
            raise ValueError
        value = float(raw)
    except ValueError:
        value = float("nan")
    if not isfinite(value) or value < minimum or value > maximum:
        validation.append(
            f"{_field(key)} must be between {_format_bound(minimum)} and {_format_bound(maximum)}; the default was used",
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
        # Accept only integer syntax, never decimal-valued floats such as 2.0.
        if len(raw) > 128 or fullmatch(r"[+-]?[0-9]+", raw) is None:
            raise ValueError
        value = int(raw, 10)
    except ValueError:
        value = minimum - 1
    if value < minimum or value > maximum:
        validation.append(
            f"{_field(key)} must be a whole number between {minimum:,} and {maximum:,}; the default was used",
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


# (attribute, query key, parser, minimum, maximum); each parser takes the current value as its fallback.
type _BoundedField = tuple[str, str, Callable[[Query, str, Any, Any, Any, list[str]], float], float, float]

# Fleet and demand fields in form order, so validation messages follow the form.
_FLEET_FIELDS: tuple[_BoundedField, ...] = (
    ("replicas", "replicas", _parse_bounded_int, 1, 100_000),
    ("duty_cycle_percent", "duty", _parse_bounded_float, 0.1, 100),
    ("memory_overhead_pct", "overhead", _parse_bounded_float, 0, 50),
    ("tokens_per_second", "throughput", _parse_bounded_float, 0.1, 1_000_000),
    ("target_utilization", "utilization", _parse_bounded_float, 1, 95),
    ("output_tokens_request", "tokens", _parse_bounded_count, 1, 1_000_000),
    ("input_tokens_request", "input-tokens", _parse_bounded_count, 1, 1_000_000),
    ("requests_per_day", "requests", _parse_bounded_float, 1, 10_000_000),
    ("active_days", "days", _parse_bounded_count, 1, 31),
)
_OPTION_FIELDS: tuple[_BoundedField, ...] = (
    ("cache_requests", "cache-requests", _parse_bounded_int, 1, 1_000_000),
    ("concurrency", "concurrency", _parse_bounded_int, 1, 100_000),
    ("measured_concurrency", "measured-concurrency", _parse_bounded_int, 0, 100_000),
    ("cache_prefix_tokens", "cache-prefix", _parse_bounded_count, 0, 1_000_000),
    ("target_first_token", "target-first", _parse_bounded_float, 0.1, 3600),
    ("target_completion", "target-complete", _parse_bounded_float, 0.1, 86_400),
    ("measured_first_token", "measured-first", _parse_bounded_float, 0, 3600),
    ("measured_completion", "measured-complete", _parse_bounded_float, 0, 86_400),
)


def _parse_fields(
    query: Query,
    inputs: HostingInputs,
    fields: Sequence[_BoundedField],
    validation: list[str],
) -> HostingInputs:
    """Parse bounded fields in order; each falls back to its current value."""
    return replace(
        inputs,
        **{
            attribute: parse(query, key, getattr(inputs, attribute), minimum, maximum, validation)
            for attribute, key, parse, minimum, maximum in fields
        },
    )


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
    validation.append(f"{_field('preset')} was not recognized; the validated demand inputs were kept")
    return inputs


def parse_inputs(query: Query) -> tuple[HostingInputs, tuple[str, ...]]:
    validation: list[str] = []
    if "platform" in query:
        validation.append("Operations budget is no longer included; totals cover GPU compute and the GKE fee")
    defaults = DEFAULT_HOSTING_INPUTS
    preset = next((item for item in DEMAND_PRESETS if item.id == _first(query, "preset")), _DEFAULT_PRESET)
    # The removed quality lab's keys (`quality*`, `tasks`, `review-rate`) are read nowhere,
    # so previously shared URLs keep working without a message.
    advanced_keys = (scenario_parameters(defaults).keys() | {"pilot", "confirm-pilot"}) - {
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
    model = find_model(
        _parse_choice(query, "model", defaults.model_id, frozenset(item.id for item in FRONTIER_MODELS), validation)
    )
    if mode == "simple":
        # Simple mode ignores advanced fields: the message above covers them, so their values are not parsed.
        inputs = replace(
            defaults,
            mode=mode,
            model_id=model.id,
            demand_window_hours=preset.window_hours
            if _first(query, "window") == "auto"
            else float(
                _parse_choice(query, "window", str(int(preset.window_hours)), frozenset(("24", "8", "1")), validation)
            ),
            quantization_id=model.default_quantization,
        )
    else:
        demand_window_hours = _parse_bounded_float(query, "window", defaults.demand_window_hours, 0.1, 24, validation)
        quantization_id = _parse_choice(
            query,
            "quant",
            model.default_quantization,
            frozenset(quant.id for quant in QUANTIZATIONS) | {"auto"},
            validation,
        )
        inputs = replace(
            defaults,
            mode=mode,
            model_id=model.id,
            demand_window_hours=demand_window_hours,
            quantization_id=model.default_quantization if quantization_id == "auto" else quantization_id,
            node_pool_id=_parse_choice(
                query,
                "node",
                defaults.node_pool_id,
                frozenset(node.id for node in GKE_NODE_POOLS) | {"auto"},
                validation,
            ),
        )
        inputs = _parse_fields(query, inputs, _FLEET_FIELDS, validation)
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
    else:
        inputs = _parse_hosting_options(query, inputs, validation)
    raw_plan = _first(query, "billing")
    if mode == "simple" or _first(query, "node") in (None, "auto"):
        allowed_plans = frozenset(("on-demand", "cud-1y", "cud-3y"))
        if mode == "advanced":
            allowed_plans |= {"flex"}
        raw_plan = _parse_choice(query, "billing", "on-demand", allowed_plans, validation)
        try:
            inputs, node = automatic_setup(
                inputs, BillingPlan(raw_plan), keep_checkpoint=_first(query, "quant") not in (None, "", "auto")
            )
        except ValueError as exc:
            validation.append(f"{exc}; select a compatible checkpoint, GPU and billing plan")
            node = find_node_pool(defaults.node_pool_id)
        inputs = replace(inputs, node_pool_id=node.id)
    node = find_node_pool(inputs.node_pool_id)
    available_plans = frozenset(price.plan.value for price in node.prices)
    # Fall back to the first plan this scenario can use; A4 lists Flex-start first,
    # which interactive serving rejects.
    fallback = next(
        (price for price in node.prices if not configuration_issue(replace(inputs, billing_plan=price.plan))),
        node.prices[0],
    )
    plan = fallback.plan.value
    if raw_plan and raw_plan not in available_plans:
        validation.append(
            f"{node.name} does not offer the {raw_plan} billing plan; {fallback.label} was used",
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
    inputs = _parse_fields(query, replace(inputs, api_mode=APIMode(api_mode)), _OPTION_FIELDS, validation)
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
    """Return a catalog precision; parsing validates ids, so an unknown one is a bug."""
    for item in QUANTIZATIONS:
        if item.id == quantization_id:
            return item
    # LookupError, not ValueError: automatic selection treats ValueError as "no machine fits".
    msg = f"Unknown checkpoint precision {quantization_id!r}; parse it with parse_inputs first"
    raise LookupError(msg)


def configuration_issue(inputs: HostingInputs, *, check_workload: bool = True) -> str:
    """Fail closed on known checkpoint, kernel, topology and delivery constraints."""
    model = find_model(inputs.model_id)
    node = find_node_pool(inputs.node_pool_id)
    quantization = find_quantization(inputs.quantization_id)
    if quantization.id not in model.supported_quantizations:
        return f"{model.name} has no verified {quantization.name} checkpoint in this catalog"
    if model.required_node_ids and node.id not in model.required_node_ids:
        names = "; ".join(find_node_pool(node_id).name for node_id in model.required_node_ids)
        return f"{model.name} requires one of the verified machines: {names}"
    precision_nodes = dict(model.quantization_node_ids).get(quantization.id)
    if precision_nodes and node.id not in precision_nodes:
        precision = quantization.name.partition(" · ")[0]
        names = "; ".join(find_node_pool(node_id).name for node_id in precision_nodes)
        return f"The {model.name} {precision} checkpoint is verified only on: {names}"
    if node.id == "ct6e-standard-8t" and quantization.id != "fp16":
        return (
            "Cloud TPU v6e Trillium requires a 16-bit BF16 checkpoint in this catalog; "
            "CUDA quantized formats are not supported on Trillium"
        )
    if node.id == "tpu7x-standard-4t" and quantization.id not in ("fp8", "fp16"):
        return (
            "Cloud TPU7x Ironwood requires an FP8 or 16-bit BF16 checkpoint in this catalog; "
            "CUDA 4-bit formats are not supported on TPU"
        )
    if quantization.id == "fp8" and node.id == "a2-ultra-1g":
        return (
            "A100 does not support the selected native FP8 W8A8 kernels; choose 16-bit or an Ada/Hopper/Blackwell GPU"
        )
    if quantization.id == "nvfp4" and node.id not in ("g4-standard-48", "a4"):
        return f"{quantization.name} requires Blackwell hardware in this conservative compatibility snapshot"
    for node_id, context_limit in model.node_context_limits:
        if (
            check_workload
            and node.id == node_id
            and inputs.input_tokens_request + inputs.output_tokens_request > context_limit
        ):
            return f"The verified {model.name} recipe on {node.name} is limited to {context_limit:,} context tokens"
    required = required_memory_gb(model, quantization, inputs.memory_overhead_pct)
    if ceil(required / node.vram_gb) > 1 and not node.multi_host:
        return (
            f"{model.name} does not fit on one {node.name}; this catalog does not support sharding across those nodes"
        )
    if inputs.billing_plan is BillingPlan.FLEX and inputs.api_mode is not APIMode.BATCH:
        return "Flex-start queues bounded jobs and does not support this interactive serving comparison; select batch or reserved capacity"
    return ""


def automatic_setup(
    inputs: HostingInputs,
    plan: BillingPlan,
    *,
    keep_checkpoint: bool = False,
) -> tuple[HostingInputs, GKENodePool]:
    """Pick the lowest-cost machine for the checkpoint, else for the model's next supported one.

    A checkpoint can lack hardware with this plan (Mistral Large 4 NVFP4 runs only on A4, which
    has no on-demand rate) or reject the workload (Nemotron NVFP4 on G4 stops at 16,384 context
    tokens). Unless the caller chose the precision, prefer the first supported checkpoint whose
    machine accepts the workload; otherwise keep the first compatible one, so the caller reports
    its limit.
    """
    model = find_model(inputs.model_id)
    others = () if keep_checkpoint else model.supported_quantizations
    candidates = [inputs, *(replace(inputs, quantization_id=q) for q in others if q != inputs.quantization_id)]
    compatible: tuple[HostingInputs, GKENodePool] | None = None
    first_error: ValueError | None = None
    for candidate in candidates:
        try:
            node = automatic_node(candidate, plan)
        except ValueError as exc:
            first_error = first_error or exc
            continue
        if not configuration_issue(replace(candidate, node_pool_id=node.id, billing_plan=plan)):
            return candidate, node
        compatible = compatible or (candidate, node)
    if compatible:
        return compatible
    raise first_error or ValueError(f"No compatible hardware for {model.name} under {plan}")


def automatic_node(
    inputs: HostingInputs,
    plan: BillingPlan,
    pools: Sequence[GKENodePool] = GKE_NODE_POOLS,
) -> GKENodePool:
    """Minimize published compute cost under the shared throughput assumption."""
    quant = find_quantization(inputs.quantization_id)
    model = find_model(inputs.model_id)
    required = required_memory_gb(model, quant, inputs.memory_overhead_pct)
    candidates = [
        node
        for node in pools
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
            nodes_for_model(model, node, required) > 1,
            nodes_for_model(model, node, required) * node.price(plan).hourly_usd,
            nodes_for_model(model, node, required),
        ),
    )


def weight_memory_gb(model: FrontierModel, quantization: Quantization) -> float:
    """Published tensor bytes include mixed precision and quantization scales.

    Every supported checkpoint lists its size (tests enforce it); the nominal fallback only
    sizes a precision the model lacks, which configuration_issue reports as unsupported.
    """
    return next(
        (size for precision, size in model.checkpoint_memory if precision == quantization.id),
        model.parameters_b * quantization.bytes_per_param,
    )


def required_memory_gb(model: FrontierModel, quantization: Quantization, overhead_pct: float) -> float:
    """Checkpoint weights plus the runtime memory reserve."""
    return weight_memory_gb(model, quantization) * (1 + overhead_pct / 100)


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
    if confirmation and not saved:
        # The button carries the configuration rendered before this submit, so a runtime
        # setting changed alongside newly typed measurements. Keep them unbound (they
        # still prove nothing) so the visitor can confirm them without retyping.
        validation.append(
            "The serving configuration changed in the same update as the pilot measurements; "
            "check recorded latency again to confirm them"
        )
        return replace(inputs, pilot_config="")
    if saved:
        validation.append("The pilot measurements belong to a different serving configuration; they were cleared")
        return without_pilot_evidence(inputs)
    return inputs


def without_pilot_evidence(inputs: HostingInputs) -> HostingInputs:
    """Drop pilot measurements that do not belong to this configuration."""
    return replace(inputs, measured_concurrency=0, measured_first_token=0, measured_completion=0, pilot_config="")


def _float_for_url(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    # repr is the shortest round-tripping form; Decimal expands its exponent so
    # shared URLs never carry scientific notation such as 1e-05.
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
        _DEFAULT_PRESET,
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
    }
    if inputs.pilot_config:
        values["pilot"] = inputs.pilot_config
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
