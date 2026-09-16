"""Bounded agent access to the same calculator used by the website."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlsplit

from pydantic import BaseModel, ConfigDict

from www.data import METADATA
from www.sites.calculator import build_llm_self_hosting_view
from www.sites.data import DEFAULT_HOSTING_INPUTS
from www.sites.economics import MONTHLY_HOURS
from www.sites.inputs import hosting_url, parse_inputs
from www.sites.models import (
    APIComparison,
    DemandPreset,
    FrontierModel,
    GKENodePool,
    HostingEstimate,
    HostingInputs,
    ModelComparison,
    PrecisionComparison,
    Quantization,
    TaskComparison,
)


def hosting_parameters(inputs: HostingInputs = DEFAULT_HOSTING_INPUTS) -> dict[str, str]:
    """Use the URL serializer as the public parameter vocabulary."""
    return dict(parse_qsl(urlsplit(hosting_url(inputs)).query))


class HostingResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenario_url: str
    parameters: dict[str, str]
    inputs: HostingInputs
    estimate: HostingEstimate
    apis: tuple[APIComparison, ...]
    models: tuple[FrontierModel, ...]
    node_pools: tuple[GKENodePool, ...]
    quantizations: tuple[Quantization, ...]
    presets: tuple[DemandPreset, ...]
    model_comparisons: tuple[ModelComparison, ...]
    precision_comparisons: tuple[PrecisionComparison, ...]
    tasks: tuple[TaskComparison, ...]
    comparison_ready: bool
    validation: tuple[str, ...]
    latency: str
    pilot_configuration: str
    calculated_on: str
    snapshot_date: str
    sources: dict[str, str]
    units: dict[str, str]
    limitations: tuple[str, ...]


def compare_hosting(parameters: dict[str, str]) -> HostingResult:
    """Reject silent input fallback before running the shared web calculator."""
    allowed = hosting_parameters().keys() | {"quality", "pilot", "confirm-pilot", "preset"}
    if parameters.keys() - allowed:
        raise ValueError("Unknown calculator parameter; use the parameters returned by an empty call or /agents.")
    if any(not value or value.strip() != value for value in parameters.values()):
        raise ValueError("Calculator parameter values must be nonempty and have no surrounding whitespace.")
    _, errors = parse_inputs(parameters)
    if errors:
        raise ValueError("Invalid calculator parameters: " + "; ".join(errors))
    now = datetime.now(UTC)
    view = build_llm_self_hosting_view(parameters, now=now)
    return HostingResult(
        scenario_url=METADATA.site_url + hosting_url(view.inputs),
        parameters=hosting_parameters(view.inputs),
        inputs=view.inputs,
        estimate=view.estimate,
        apis=view.apis,
        models=view.models,
        node_pools=view.node_pools,
        quantizations=view.quantizations,
        presets=view.presets,
        model_comparisons=view.comparison,
        precision_comparisons=view.precisions,
        tasks=view.tasks if view.inputs.quality_enabled else (),
        comparison_ready=view.comparison_ready,
        validation=view.validation,
        latency=f"{view.latency_title}. {view.latency_detail}",
        pilot_configuration=view.current_pilot_config,
        calculated_on=now.date().isoformat(),
        snapshot_date=view.snapshot_date,
        sources={"models": view.model_source_url, "gke": view.gke_source_url, "compute": view.price_source_url},
        units={
            "currency": "USD",
            "month": f"{MONTHLY_HOURS:g} hours",
            "memory": "GB",
            "throughput": "output tokens per second per replica",
            "latency": "seconds (p95)",
            "api_prices": "USD per million tokens unless field states otherwise",
            "break_even_requests": "requests per month",
        },
        limitations=(
            "Planning estimates from a dated snapshot, not live prices or a capacity quote; check linked sources.",
            "Model quality is not equivalent across providers. Throughput is an assumption unless measured.",
            "Memory fit does not prove runtime support, topology, concurrency, or latency; validate with a pilot.",
            "Additional disks, network, load balancers, licenses, and operations belong in the platform budget.",
            "Committed machines are billed for the full term even when idle; regional availability needs a quote.",
            "Pilot and task-quality inputs are caller-supplied evidence, not measurements performed by this server.",
        ),
    )
