"""Self-hosting calculator inputs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
from math import isfinite
from re import fullmatch
from urllib.parse import urlencode

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
    FrontierModel,
    GKENodePool,
    HostingInputs,
    Quantization,
    TaskQuality,
)

# Source-faithful UI copy intentionally uses multiplication signs.

type QueryValue = str | Sequence[str]
type Query = Mapping[str, QueryValue]


def _first(query: Query, key: str) -> str | None:
    raw = query.get(key)
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    return raw[0] if raw else None


def _go_general(value: float) -> str:
    return format(value, ".6g")


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
) -> float:
    raw = _first(query, key)
    if raw is None or raw == "":
        return fallback
    try:
        if raw.strip() != raw:
            raise ValueError
        value = float(raw)
    except ValueError:
        value = float("nan")
    if not isfinite(value) or value < minimum or value > maximum:
        validation.append(
            f"{key} must be between {_go_general(minimum)} and {_go_general(maximum)}; the default was used",
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
            f"{key} must be between {minimum} and {maximum}; the default was used",
        )
        return fallback
    return value


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
    defaults = DEFAULT_HOSTING_INPUTS
    # Previously shared URLs encoded the A4 billing plan in the hardware ID.
    legacy_plan = {"a4-cud-3y": "cud-3y", "a4-flex": "flex"}.get(_first(query, "node") or "")
    if legacy_plan:
        query = dict(query)
        query["node"] = "a4"
        if not _first(query, "billing"):
            query["billing"] = legacy_plan
    inputs = replace(
        defaults,
        model_id=_parse_choice(
            query,
            "model",
            defaults.model_id,
            frozenset(model.id for model in FRONTIER_MODELS),
            validation,
        ),
        node_pool_id=_parse_choice(
            query,
            "node",
            defaults.node_pool_id,
            frozenset(node.id for node in GKE_NODE_POOLS),
            validation,
        ),
        quantization_id=_parse_choice(
            query,
            "quant",
            defaults.quantization_id,
            frozenset(quant.id for quant in QUANTIZATIONS),
            validation,
        ),
        replicas=_parse_bounded_int(query, "replicas", defaults.replicas, 1, 8, validation),
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
        output_tokens_request=_parse_bounded_float(
            query,
            "tokens",
            defaults.output_tokens_request,
            1,
            1_000_000,
            validation,
        ),
        input_tokens_request=_parse_bounded_float(
            query,
            "input-tokens",
            defaults.input_tokens_request,
            1,
            1_000_000,
            validation,
        ),
        requests_per_day=_parse_bounded_float(
            query,
            "requests",
            defaults.requests_per_day,
            1,
            10_000_000,
            validation,
        ),
        active_days=_parse_bounded_float(
            query,
            "days",
            defaults.active_days,
            1,
            31,
            validation,
        ),
        platform_monthly_usd=_parse_bounded_float(
            query,
            "platform",
            defaults.platform_monthly_usd,
            0,
            10_000_000,
            validation,
        ),
    )
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
    inputs = _apply_demand_preset(_first(query, "preset"), inputs, validation)
    inputs = _parse_hosting_options(query, inputs, validation)
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
    float_fields = (
        ("cache_prefix_tokens", "cache-prefix", 0, 1_000_000),
        ("target_first_token", "target-first", 0.1, 3600),
        ("target_completion", "target-complete", 0.1, 86_400),
        ("measured_first_token", "measured-first", 0, 3600),
        ("measured_completion", "measured-complete", 0, 86_400),
        ("tasks_per_month", "tasks", 1, 10_000_000),
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
    quality_0, quality_1, quality_2, quality_3 = qualities
    inputs = replace(inputs, quality=(quality_0, quality_1, quality_2, quality_3))
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
        validation.append("The pilot measurements were cleared because the serving configuration changed")
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


def hosting_url(inputs: HostingInputs) -> str:
    values = {
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
        "platform": _float_for_url(inputs.platform_monthly_usd),
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
    return "/sites/llm-self-hosting/?" + urlencode(sorted(values.items()))
