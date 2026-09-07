from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class APIMode(StrEnum):
    STANDARD = "standard"
    BATCH = "batch"
    CACHED = "cached"


class BillingPlan(StrEnum):
    ON_DEMAND = "on-demand"
    CUD_1Y = "cud-1y"
    CUD_3Y = "cud-3y"
    FLEX = "flex"


@dataclass(frozen=True, slots=True)
class NodePrice:
    plan: BillingPlan
    label: str
    hourly_usd: float

    @property
    def committed(self) -> bool:
        return self.plan in (BillingPlan.CUD_1Y, BillingPlan.CUD_3Y)


@dataclass(frozen=True, slots=True)
class FrontierModel:
    id: str
    rank: int
    name: str
    creator: str
    intelligence: float
    parameters_b: float
    active_parameters: float
    context_tokens: int
    license: str
    license_class: str
    analysis_url: str
    weights_url: str
    minimum_node_id: str
    minimum_nodes: int


@dataclass(frozen=True, slots=True)
class GKENodePool:
    id: str
    name: str
    gpu: str
    gpu_count: int
    vram_gb: float
    prices: tuple[NodePrice, ...]
    operational: str
    multi_host: bool = False

    def price(self, plan: BillingPlan) -> NodePrice:
        for price in self.prices:
            if price.plan is plan:
                return price
        msg = f"{self.name} does not offer {plan} in this price snapshot"
        raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class Quantization:
    id: str
    name: str
    bytes_per_param: float
    guidance: str


@dataclass(frozen=True, slots=True)
class DemandPreset:
    id: str
    name: str
    description: str
    requests_per_day: float
    active_days: float
    input_tokens: float
    output_tokens: float


@dataclass(frozen=True, slots=True)
class APIBaseline:
    name: str
    input_per_million: float
    output_per_million: float
    cache_read_per_million: float
    cache_write_per_million: float
    cache_storage_per_million_hour: float
    cache_minimum: float
    source_url: str
    cache_url: str
    verified_on: str
    review_on: str
    valid_through: str
    note: str
    input_token_limit: int
    output_token_limit: int
    context_token_limit: int = 0


@dataclass(frozen=True, slots=True)
class TaskQuality:
    acceptance_percent: float
    calls_per_task: float
    review_minutes: float


@dataclass(frozen=True, slots=True)
class HostingInputs:
    model_id: str
    node_pool_id: str
    quantization_id: str
    replicas: int
    duty_cycle_percent: float
    memory_overhead_pct: float
    tokens_per_second: float
    target_utilization: float
    output_tokens_request: float
    input_tokens_request: float
    requests_per_day: float
    active_days: float
    platform_monthly_usd: float
    api_mode: APIMode
    cache_prefix_tokens: float
    cache_requests: int
    concurrency: int
    target_first_token: float
    target_completion: float
    measured_concurrency: int
    measured_first_token: float
    measured_completion: float
    tasks_per_month: float
    review_hourly_usd: float
    quality: tuple[TaskQuality, TaskQuality, TaskQuality, TaskQuality]
    quality_enabled: bool
    billing_plan: BillingPlan = BillingPlan.ON_DEMAND
    pilot_config: str = ""


@dataclass(frozen=True, slots=True)
class HostingEstimate:
    weight_memory_gb: float
    required_memory_gb: float
    nodes_per_replica: int
    total_nodes: int
    total_gpus: int
    compute_monthly_usd: float
    control_monthly_usd: float
    platform_monthly_usd: float
    total_monthly_usd: float
    capacity_tokens_month: float
    capacity_requests_day: float
    requests_month: float
    input_tokens_month: float
    output_tokens_month: float
    demand_capacity_pct: float
    per_thousand_requests_usd: float
    demand_fits: bool
    context_issue: str
    topology_confirmed: bool
    qualified: bool


@dataclass(frozen=True, slots=True)
class APIComparison:
    baseline: APIBaseline
    monthly_usd: float
    cache_overhead_usd: float
    per_thousand_requests_usd: float
    break_even_requests: float
    break_even_fits: bool
    mode_note: str
    request_issue: str
    freshness: str = ""
    needs_review: bool = False


@dataclass(frozen=True, slots=True)
class PrecisionComparison:
    quantization: Quantization
    estimate: HostingEstimate


@dataclass(frozen=True, slots=True)
class ModelComparison:
    model: FrontierModel
    estimate: HostingEstimate
    decision: str


@dataclass(frozen=True, slots=True)
class HardwareGuidance:
    node: GKENodePool
    nodes_per_replica: int


@dataclass(frozen=True, slots=True)
class TaskComparison:
    id: str
    name: str
    quality: TaskQuality
    requests: float
    accepted: float
    model_usd: float
    review_usd: float
    per_accepted_usd: float
    fits: bool
    request_issue: str


@dataclass(frozen=True, slots=True)
class PlotLine:
    name: str
    points: str


@dataclass(frozen=True, slots=True)
class PlotTick:
    position: str
    label: str


@dataclass(frozen=True, slots=True)
class CostFrame:
    x: str
    label: str
    summary: str
    url: str
    requests: float


@dataclass(frozen=True, slots=True)
class CostPlot:
    capacity_x: str
    capacity_width: str
    capacity_label: str
    fleet_y: str
    lines: tuple[PlotLine, ...]
    frames: tuple[CostFrame, ...]
    x_ticks: tuple[PlotTick, ...]
    y_ticks: tuple[PlotTick, ...]
    break_evens: tuple[PlotTick, ...]
    selected: int


@dataclass(frozen=True, slots=True)
class SensitivityCell:
    url: str
    verdict: str
    inputs: HostingInputs
    capacity_pct: float
    cheapest_api_usd: float
    fits: bool


@dataclass(frozen=True, slots=True)
class SensitivityRow:
    label: str
    cells: tuple[SensitivityCell, ...]


@dataclass(frozen=True, slots=True)
class LLMSelfHostingView:
    inputs: HostingInputs
    models: tuple[FrontierModel, ...]
    node_pools: tuple[GKENodePool, ...]
    quantizations: tuple[Quantization, ...]
    selected_model: FrontierModel
    selected_node: GKENodePool
    selected_price: NodePrice
    hardware_guidance: HardwareGuidance
    selected_quant: Quantization
    estimate: HostingEstimate
    comparison: tuple[ModelComparison, ...]
    validation: tuple[str, ...]
    snapshot_date: str
    index_version: str
    presets: tuple[DemandPreset, ...]
    apis: tuple[APIComparison, ...]
    precisions: tuple[PrecisionComparison, ...]
    demand_label: str
    cost_plot: CostPlot
    sensitivity: tuple[SensitivityRow, ...]
    tasks: tuple[TaskComparison, ...]
    latency_title: str
    latency_detail: str
    model_source_url: str
    gke_source_url: str
    price_source_url: str
    current_pilot_config: str
    comparison_ready: bool
