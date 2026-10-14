"""Server-owned MCP tool-definition arithmetic. See sources.md for provenance and limits.

Tokens per request T = sum of measured catalog tokens for the selected servers.
Tokens per month = T * requests/day * 30 days.
For each managed API: context share = 100 * T / input limit, and cost = tokens * standard
input price / 1e6. Caching, output, tool results and the rest of the prompt are excluded.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from re import fullmatch
from typing import Literal, get_args
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict

from www.data import METADATA
from www.sites.data import DEFAULT_HOSTING_INPUTS, MODEL_SNAPSHOT
from www.sites.economics import current_api_baselines, utc_date
from www.sites.formatting import format_decimal

from .data import SERVERS, SNAPSHOT_DATE, ServerSnapshot

PATH = "/sites/mcp-context-cost/"
DAYS_PER_MONTH = 30
DEFAULT_REQUESTS = 1000
MAX_REQUESTS = 10_000_000
# Typed MCP arguments advertise these choices; a test keeps them aligned with SERVERS.
ServerId = Literal["github", "filesystem", "memory", "playwright"]
SERVER_IDS: tuple[str, ...] = get_args(ServerId)
LIMITATIONS = (
    "Reference tokens: tiktoken o200k_base over each server's normalized input declarations. Provider tokenizers, tool wrappers and hidden system tokens differ.",
    "Costs use standard input prices from a dated snapshot. Prompt caching lowers the price of repeated definitions, not the context they occupy.",
    "Only tool definitions are counted: instructions, history, tool results, output and reasoning need their own budget.",
    "A month is 30 days of the given daily requests. Every model call in an agent loop counts as a request.",
)


@dataclass(frozen=True, slots=True)
class ServerShare:
    server: ServerSnapshot
    percent: float


@dataclass(frozen=True, slots=True)
class ModelCost:
    name: str
    input_per_million: float
    input_token_limit: int
    context_percent: float
    per_thousand_requests_usd: float
    month_usd: float
    source_url: str
    verified_on: str
    needs_review: bool


@dataclass(frozen=True, slots=True)
class ContextView:
    servers: tuple[ServerSnapshot, ...]
    selected: tuple[ServerShare, ...]
    requests_per_day: int
    tools: int
    tokens_request: int
    tokens_month: int
    models: tuple[ModelCost, ...]
    validation: tuple[str, ...]
    scenario_url: str
    snapshot_date: str
    price_date: str


type Query = Mapping[str, str | Sequence[str]]


def scenario_url(servers: Sequence[str], requests_per_day: int) -> str:
    return PATH + "?" + urlencode([*(("server", server) for server in servers), ("requests", requests_per_day)])


def parse_query(query: Query) -> tuple[tuple[str, ...], int, tuple[str, ...]]:
    """Read the native GET form; unrelated keys such as UTM tags are ignored."""
    errors: list[str] = []
    raw_servers = query.get("server", ())
    raw_servers = [raw_servers] if isinstance(raw_servers, str) else list(raw_servers)
    unknown = any(value not in SERVER_IDS for value in raw_servers)
    servers = tuple(server for server in SERVER_IDS if server in raw_servers)
    if not servers:
        if unknown:
            errors.append("Unknown MCP servers were ignored; all servers were used")
        elif "requests" in query:
            # The form always submits requests: a submitted form without servers had every box unchecked.
            errors.append("Select at least one MCP server; all servers were used")
        servers = SERVER_IDS
    elif unknown:
        errors.append("Unknown MCP servers were ignored")
    requests = DEFAULT_REQUESTS
    raw_requests = query.get("requests")
    if raw_requests is not None:
        values = [raw_requests] if isinstance(raw_requests, str) else list(raw_requests)
        value = values[0] if len(values) == 1 else ""
        if len(value) <= 12 and fullmatch(r"[0-9]+", value) and 1 <= int(value) <= MAX_REQUESTS:
            requests = int(value)
        else:
            errors.append(
                f"Requests per day must be a whole number between 1 and {format_decimal(MAX_REQUESTS, 0)}; "
                f"{format_decimal(DEFAULT_REQUESTS, 0)} was used"
            )
    return servers, requests, tuple(errors)


def build_context_view(
    servers: Sequence[str] = SERVER_IDS,
    requests_per_day: int = DEFAULT_REQUESTS,
    validation: Sequence[str] = (),
    now: datetime | None = None,
) -> ContextView:
    chosen = tuple(server for server in SERVERS if server.id in servers)
    tokens = sum(server.tokens for server in chosen)
    requests_month = requests_per_day * DAYS_PER_MONTH
    now = now or datetime.now(UTC)
    today = utc_date(now)
    # Definitions are a short prompt prefix, so the default scenario selects standard-tier rates.
    baselines = sorted(current_api_baselines(now, DEFAULT_HOSTING_INPUTS), key=lambda row: row.input_per_million)
    models = tuple(
        ModelCost(
            name=baseline.name,
            input_per_million=baseline.input_per_million,
            input_token_limit=baseline.input_token_limit,
            context_percent=100 * tokens / baseline.input_token_limit,
            per_thousand_requests_usd=tokens * 1000 * baseline.input_per_million / 1e6,
            month_usd=tokens * requests_month * baseline.input_per_million / 1e6,
            source_url=baseline.source_url,
            verified_on=baseline.verified_on,
            needs_review=today >= baseline.review_on,
        )
        for baseline in baselines
    )
    return ContextView(
        servers=SERVERS,
        selected=tuple(
            ServerShare(server, 100 * server.tokens / tokens) for server in sorted(chosen, key=lambda row: -row.tokens)
        ),
        requests_per_day=requests_per_day,
        tools=sum(server.tools for server in chosen),
        tokens_request=tokens,
        tokens_month=tokens * requests_month,
        models=models,
        validation=tuple(validation),
        scenario_url=METADATA.site_url + scenario_url(tuple(server.id for server in chosen), requests_per_day),
        snapshot_date=SNAPSHOT_DATE,
        price_date=MODEL_SNAPSHOT,
    )


def view_from_query(query: Query) -> ContextView:
    servers, requests, validation = parse_query(query)
    return build_context_view(servers, requests, validation)


class ContextResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    servers: tuple[ServerSnapshot, ...]
    requests_per_day: int
    days_per_month: int
    tools: int
    tokens_per_request: int
    tokens_per_month: int
    models: tuple[ModelCost, ...]
    scenario_url: str
    snapshot_verified_on: str
    prices_checked_on: str
    limitations: tuple[str, ...]


def compare_context(servers: Sequence[str] | None = None, requests_per_day: int = DEFAULT_REQUESTS) -> ContextResult:
    """Fail closed for MCP callers: duplicate, unknown or out-of-range inputs raise."""
    servers = SERVER_IDS if servers is None else tuple(servers)
    if not servers or len(set(servers)) != len(servers) or set(servers) - set(SERVER_IDS):
        raise ValueError(f"servers must list distinct ids from {', '.join(SERVER_IDS)}; omit it for all servers.")
    if not 1 <= requests_per_day <= MAX_REQUESTS:
        raise ValueError(f"requests_per_day must be between 1 and {MAX_REQUESTS}.")
    view = build_context_view(servers, requests_per_day)
    return ContextResult(
        servers=tuple(share.server for share in view.selected),
        requests_per_day=view.requests_per_day,
        days_per_month=DAYS_PER_MONTH,
        tools=view.tools,
        tokens_per_request=view.tokens_request,
        tokens_per_month=view.tokens_month,
        models=view.models,
        scenario_url=view.scenario_url,
        snapshot_verified_on=view.snapshot_date,
        prices_checked_on=view.price_date,
        limitations=LIMITATIONS,
    )
