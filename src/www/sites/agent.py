"""Bounded agent access to the same calculator used by the website."""

from dataclasses import replace
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from www.data import METADATA
from www.sites.calculator import build_llm_self_hosting_view
from www.sites.capacity import MONTHLY_HOURS
from www.sites.data import DEFAULT_HOSTING_INPUTS
from www.sites.inputs import hosting_url, parse_inputs, scenario_parameters
from www.sites.models import (
    APIComparison,
    DemandPreset,
    FrontierModel,
    GKENodePool,
    HostingEstimate,
    HostingInputs,
    Quantization,
    TaskComparison,
)


# Comparison rows name catalog entries by id: repeating the full model, machine, and
# quantization objects in every row made one default call about 158 KB of agent context.
class ModelRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_id: str
    quantization_id: str
    node_id: str
    estimate: HostingEstimate
    decision: str


class PrecisionRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    quantization_id: str
    node_id: str
    estimate: HostingEstimate
    url: str


class AcceleratorRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    family: str
    quantization_id: str
    node_id: str
    estimate: HostingEstimate
    url: str


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
    model_comparisons: tuple[ModelRow, ...]
    precision_comparisons: tuple[PrecisionRow, ...]
    accelerator_comparisons: tuple[AcceleratorRow, ...]
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
    allowed = scenario_parameters(replace(DEFAULT_HOSTING_INPUTS, mode="advanced")).keys() | {
        "quality",
        "pilot",
        "confirm-pilot",
        "preset",
    }
    if parameters.keys() - allowed:
        raise ValueError("Unknown calculator parameter; use the parameters returned by an empty call or /agents.")
    if any(not value or value.strip() != value for value in parameters.values()):
        raise ValueError("Calculator parameter values must be nonempty and have no surrounding whitespace.")
    # The web form resubmits every field with a preset button, so outside simple mode a
    # preset replaces explicit demand. MCP callers must choose one instead of losing values.
    demand = parameters.keys() & {"requests", "days", "input-tokens", "tokens"}
    if "preset" in parameters and parameters.get("mode") != "simple" and demand:
        raise ValueError(
            "preset replaces " + ", ".join(sorted(demand)) + " in advanced mode; send the preset or explicit demand.",
        )
    _, errors = parse_inputs(parameters)
    if errors:
        # Validation messages read "<reason>; <fallback applied by the web form>". MCP
        # rejects instead of falling back, so it reports only the reason.
        reasons = (error.partition("; ")[0] for error in errors)
        raise ValueError("Invalid calculator parameters: " + "; ".join(reasons))
    now = datetime.now(UTC)
    view = build_llm_self_hosting_view(parameters, now=now)
    return HostingResult(
        scenario_url=METADATA.site_url + hosting_url(view.inputs),
        parameters=scenario_parameters(view.inputs),
        inputs=view.inputs,
        estimate=view.estimate,
        apis=view.apis,
        models=view.models,
        node_pools=view.node_pools,
        quantizations=view.quantizations,
        presets=view.presets,
        model_comparisons=tuple(
            ModelRow(
                model_id=row.model.id,
                quantization_id=row.quantization.id,
                node_id=row.node.id,
                estimate=row.estimate,
                decision=row.decision,
            )
            for row in view.comparison
        ),
        precision_comparisons=tuple(
            PrecisionRow(quantization_id=row.quantization.id, node_id=row.node.id, estimate=row.estimate, url=row.url)
            for row in view.precisions
        ),
        accelerator_comparisons=tuple(
            AcceleratorRow(
                family=row.family,
                quantization_id=row.quantization.id,
                node_id=row.node.id,
                estimate=row.estimate,
                url=row.url,
            )
            for row in view.accelerators
        ),
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
            "capacity_load": "percent of assumed usable output capacity, not measured GPU utilization",
        },
        limitations=(
            "Planning estimates from a dated snapshot, not live prices or a capacity quote; check linked sources.",
            "Model quality is not equivalent across providers. Throughput is an assumption unless measured.",
            "Memory fit does not prove runtime support, topology, concurrency, or latency; validate with a pilot.",
            "Totals include GPU compute and the GKE fee; additional disks, network, load balancers, licenses, and operations are excluded.",
            "Committed machines are billed for the full term even when idle; regional availability needs a quote.",
            "Pilot and task-quality inputs are caller-supplied evidence, not measurements performed by this server.",
            # Kept numeric so the published output schema stays stable for existing callers.
            "A task row with accepted 0 reports per_accepted_usd 0: cost per accepted task is undefined there, not free.",
            "Usage windows constrain average output rate, not bursts or latency. Running hours are scheduled inside active windows; startup needs a pilot.",
            "Simple mode sizes replicas and schedules batch presets; interactive presets stay on 24/7. Advanced mode keeps the fleet fixed. Break-even holds it fixed.",
        ),
    )
