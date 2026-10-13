"""Server-owned MCP context arithmetic. See sources.md for equations and boundaries.

All-tools tokens B = sum(full catalog tokens for servers with enabled > 0).
Filtered tokens F = ceil(sum(catalog tokens * enabled / catalog tool count)).
Search tokens = ceil(discovery scaffold + F * loaded_percent / 100).
CLI tokens = skill scaffold + average loaded help. These are user assumptions.
For each strategy T, context share = 100*T/context; uncached session = T*R*P/1e6.
Eligible hits H = (R-1)*hit_percent/100; cached session =
T*((R-H)*P*write_multiplier + H*cache_read_price)/1e6.
If T + other stable prefix is below the cache minimum, use uncached cost.
Daily and monthly costs multiply session cost by sessions/day and workdays/month.
Caching changes billing, never the occupied context. Outputs exclude tool results,
other prompt/history tokens, output, search fees, extra calls and cache storage.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from math import ceil, isfinite
from re import fullmatch
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict

from www.data import METADATA

from .data import MODELS, SERVERS, SNAPSHOT_DATE, ModelSnapshot, ServerSnapshot

PATH = "/sites/mcp-context-cost/"
MITIGATIONS = (
    ("all", "All tools"),
    ("filter", "Tool filtering"),
    ("search", "Dynamic discovery / tool search"),
    ("cli", "CLI-first skills"),
)


@dataclass(frozen=True, slots=True)
class NumberField:
    key: str
    label: str
    default: float
    minimum: float
    maximum: float
    help: str
    whole: bool = False


FIELDS = (
    NumberField(
        "context",
        "Context window (tokens)",
        400000,
        1,
        10000000,
        "Total model window; reserve room for instructions, history, tool results and output.",
        True,
    ),
    NumberField(
        "input-price",
        "Input price (USD / million tokens)",
        0.75,
        0,
        1000,
        "Standard input rate. Preset rates are dated; edit to match your provider and tier.",
    ),
    NumberField(
        "cache-price",
        "Cache-read price (USD / million tokens)",
        0.075,
        0,
        1000,
        "Rate for eligible cached input; caching still occupies the same context.",
    ),
    NumberField(
        "write-multiplier",
        "Cache write / input price",
        1,
        1,
        10,
        "1 means ordinary input price on misses; 1.25 models a 25% cache-write premium.",
    ),
    NumberField(
        "requests",
        "Requests per session",
        20,
        1,
        10000,
        "Count every model request in an agent loop, not just user messages.",
        True,
    ),
    NumberField(
        "sessions",
        "Sessions per workday",
        10,
        1,
        100000,
        "A new session starts cold; no cache reuse across sessions is assumed.",
        True,
    ),
    NumberField("days", "Workdays per month", 22, 1, 31, "Costs apply only to these active days.", True),
    NumberField(
        "cache-hits",
        "Follow-up cache hits (%)",
        80,
        0,
        100,
        "Assumed share after the first request, for the entire modeled block. Use observed hits; changed schemas or prefixes can invalidate them.",
    ),
    NumberField(
        "cache-minimum",
        "Assumed minimum cache prefix (tokens)",
        1024,
        0,
        10000000,
        "1,024 is a planning assumption; preset model minima depend on request settings. Include other stable tokens; check provider rules.",
        True,
    ),
    NumberField(
        "other-prefix",
        "Other stable prefix (tokens)",
        0,
        0,
        10000000,
        "Used only for cache eligibility. Its cost and context usage are outside these tool-definition totals.",
        True,
    ),
    NumberField(
        "loaded",
        "Filtered definitions loaded on average (%)",
        20,
        0,
        100,
        "Discovery assumption per model request, including definitions retained in history. Measure this in your client.",
    ),
    NumberField(
        "discovery-tokens",
        "Discovery scaffold (tokens/request)",
        500,
        0,
        1000000,
        "Assumed search tool, index and discovery instructions. Search calls/results may cost extra.",
        True,
    ),
    NumberField(
        "skill-tokens",
        "CLI skill scaffold (tokens/request)",
        300,
        0,
        1000000,
        "Assumed always-visible skill metadata and shell tool definition.",
        True,
    ),
    NumberField(
        "help-tokens",
        "Loaded CLI help (average tokens/request)",
        700,
        0,
        1000000,
        "Assumed loaded instructions/help retained in context. Command output and extra calls are excluded.",
        True,
    ),
)


@dataclass(frozen=True, slots=True)
class ContextInputs:
    model: str
    mitigation: str
    enabled: tuple[int, ...]
    values: dict[str, float]


@dataclass(frozen=True, slots=True)
class Strategy:
    id: str
    label: str
    tokens_request: int
    context_percent: float
    fits: bool
    cache_eligible: bool
    request_usd: float
    cached_average_request_usd: float
    session_usd: float
    day_usd: float
    month_usd: float
    cached_session_usd: float
    cached_day_usd: float
    cached_month_usd: float
    saved_month_usd: float
    cached_saved_month_usd: float


@dataclass(frozen=True, slots=True)
class ContextView:
    inputs: ContextInputs
    parameters: dict[str, str]
    validation: tuple[str, ...]
    strategies: tuple[Strategy, ...]
    selected: Strategy
    fields: tuple[NumberField, ...]
    servers: tuple[ServerSnapshot, ...]
    models: tuple[ModelSnapshot, ...]
    model_urls: tuple[tuple[str, str], ...]
    mitigations: tuple[tuple[str, str], ...]
    snapshot_date: str
    scenario_url: str


type Query = Mapping[str, str | Sequence[str]]


def _number(raw: str, field: NumberField) -> float:
    pattern = r"[0-9]+" if field.whole else r"[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
    if len(raw) > 128 or fullmatch(pattern, raw) is None:
        raise ValueError("Invalid numeric syntax")
    value = float(raw)
    if not isfinite(value) or not field.minimum <= value <= field.maximum:
        raise ValueError("Outside the permitted range")
    return value


def parse_inputs(query: Query) -> tuple[ContextInputs, tuple[str, ...]]:
    """Validate all supplied keys; page fallbacks are visible and MCP rejects them."""
    errors: list[str] = []
    allowed = {field.key for field in FIELDS} | {server.id for server in SERVERS} | {"model", "mitigation"}
    raw: dict[str, str] = {}
    for key, value in query.items():
        if not isinstance(value, str) and len(value) == 1:
            value = value[0]
        if key not in allowed:
            errors.append("Unknown calculator parameter; it was ignored")
        elif not isinstance(value, str):
            errors.append(f"{key} must occur once; the default was used")
        elif not value or value.strip() != value:
            errors.append(f"{key} must be nonempty without surrounding whitespace; the default was used")
        else:
            raw[key] = value

    def choice(key: str, choices: tuple[str, ...]) -> str:
        value = raw.get(key, choices[0])
        if value in choices:
            return value
        errors.append(f"{key} was not recognized; the default was used")
        return choices[0]

    model_id = choice("model", tuple(model.id for model in MODELS))
    model = next(model for model in MODELS if model.id == model_id)
    defaults = {
        "context": model.context_tokens,
        "input-price": model.input_price,
        "cache-price": model.cache_price,
        "write-multiplier": model.write_multiplier,
        "cache-minimum": model.cache_minimum,
    }

    def number(field: NumberField) -> float:
        default = defaults.get(field.key, field.default)
        if field.key not in raw:
            return default
        try:
            return _number(raw[field.key], field)
        except ValueError:
            qualifier = "a whole number " if field.whole else ""
            errors.append(
                f"{field.label} must be {qualifier}between {field.minimum:g} and {field.maximum:g}; the default was used"
            )
            return default

    inputs = ContextInputs(
        model=model_id,
        mitigation=choice("mitigation", tuple(key for key, _ in MITIGATIONS)),
        enabled=tuple(
            int(number(NumberField(server.id, server.name + " enabled tools", server.tools, 0, server.tools, "", True)))
            for server in SERVERS
        ),
        values={field.key: number(field) for field in FIELDS},
    )
    return inputs, tuple(dict.fromkeys(errors))


def parameters(inputs: ContextInputs) -> dict[str, str]:
    return {
        "model": inputs.model,
        "mitigation": inputs.mitigation,
        **{server.id: str(count) for server, count in zip(SERVERS, inputs.enabled, strict=True)},
        **{
            key: str(int(value)) if field.whole else str(value)
            for field in FIELDS
            for key, value in ((field.key, inputs.values[field.key]),)
        },
    }


def scenario_url(inputs: ContextInputs) -> str:
    return PATH + "?" + urlencode(parameters(inputs))


def estimate(inputs: ContextInputs) -> tuple[Strategy, ...]:
    values = inputs.values
    baseline = sum(server.tokens for server, count in zip(SERVERS, inputs.enabled, strict=True) if count)
    filtered = ceil(
        sum(server.tokens * count / server.tools for server, count in zip(SERVERS, inputs.enabled, strict=True))
    )
    tokens = (
        baseline,
        filtered,
        ceil(values["discovery-tokens"] + filtered * values["loaded"] / 100),
        int(values["skill-tokens"] + values["help-tokens"]),
    )
    rows: list[Strategy] = []
    for (key, label), token_count in zip(MITIGATIONS, tokens, strict=True):
        session = token_count * values["requests"] * values["input-price"] / 1e6
        eligible = token_count + values["other-prefix"] >= values["cache-minimum"]
        hits = (values["requests"] - 1) * values["cache-hits"] / 100
        cached_session = (
            token_count
            * (
                (values["requests"] - hits) * values["input-price"] * values["write-multiplier"]
                + hits * values["cache-price"]
            )
            / 1e6
            if eligible
            else session
        )
        day = session * values["sessions"]
        cached_day = cached_session * values["sessions"]
        rows.append(
            Strategy(
                id=key,
                label=label,
                tokens_request=token_count,
                context_percent=100 * token_count / values["context"],
                fits=token_count <= values["context"],
                cache_eligible=eligible,
                request_usd=token_count * values["input-price"] / 1e6,
                cached_average_request_usd=cached_session / values["requests"],
                session_usd=session,
                day_usd=day,
                month_usd=day * values["days"],
                cached_session_usd=cached_session,
                cached_day_usd=cached_day,
                cached_month_usd=cached_day * values["days"],
                saved_month_usd=0,
                cached_saved_month_usd=0,
            )
        )
    return tuple(
        replace(
            row,
            saved_month_usd=rows[0].month_usd - row.month_usd,
            cached_saved_month_usd=rows[0].cached_month_usd - row.cached_month_usd,
        )
        for row in rows
    )


def build_context_view(query: Query) -> ContextView:
    inputs, validation = parse_inputs(query)
    rows = estimate(inputs)
    urls = []
    for model in MODELS:
        # Preset links replace only provider assumptions; workload and tools survive.
        values = {
            **inputs.values,
            "context": model.context_tokens,
            "input-price": model.input_price,
            "cache-price": model.cache_price,
            "write-multiplier": model.write_multiplier,
            "cache-minimum": model.cache_minimum,
        }
        urls.append((model.name, scenario_url(replace(inputs, model=model.id, values=values))))
    return ContextView(
        inputs,
        parameters(inputs),
        validation,
        rows,
        next(row for row in rows if row.id == inputs.mitigation),
        FIELDS,
        SERVERS,
        MODELS,
        tuple(urls),
        MITIGATIONS,
        SNAPSHOT_DATE,
        METADATA.site_url + scenario_url(inputs),
    )


class ContextResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenario_url: str
    parameters: dict[str, str]
    strategies: tuple[Strategy, ...]
    servers: tuple[ServerSnapshot, ...]
    models: tuple[ModelSnapshot, ...]
    fields: tuple[NumberField, ...]
    snapshot_date: str
    limitations: tuple[str, ...]


def compare_context(parameters: dict[str, str]) -> ContextResult:
    view = build_context_view(parameters)
    if view.validation:
        raise ValueError(
            "Invalid calculator parameters: " + "; ".join(error.partition("; ")[0] for error in view.validation)
        )
    return ContextResult(
        scenario_url=view.scenario_url,
        parameters=view.parameters,
        strategies=view.strategies,
        servers=view.servers,
        models=view.models,
        fields=view.fields,
        snapshot_date=view.snapshot_date,
        limitations=(
            "USD planning estimates, not measured production usage or live pricing.",
            "Snapshot tokens use tiktoken o200k_base over normalized input declarations; provider tokenizers and client wrappers differ.",
            "Partial tool counts are proportional estimates. Tool schemas vary in size; measure the actual enabled set.",
            "Discovery and CLI token budgets are assumptions per request, including retained definitions/help. Extra calls, search fees and tool output are excluded.",
            "Cache hits assume the entire modeled block is stable and eligible within retention limits; each session starts cold. Context usage is unchanged.",
            "Minimum cache prefix includes other-prefix, whose cost/context is excluded. Alignment, cache storage and provider-specific billing rounding are not modeled.",
            "A fitting tool block does not prove the entire request fits. Other instructions, history, results and output need context and budget.",
            "Savings compare each strategy with all tools under the same cache policy; negative savings mean a cost increase.",
        ),
    )
