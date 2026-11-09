from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal


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
    name: str
    creator: str
    parameters_b: float
    active_parameters: float
    context_tokens: int
    license: str
    license_class: str
    weights_url: str
    default_quantization: str = "fp16"
    # Required: a default list would claim checkpoints that a model never released.
    supported_quantizations: tuple[str, ...] = field(kw_only=True)
    required_node_ids: tuple[str, ...] = ()
    node_context_limits: tuple[tuple[str, int], ...] = ()
    checkpoint_memory: tuple[tuple[str, float], ...] = ()
    node_minimums: tuple[tuple[str, int], ...] = ()
    checkpoint_urls: tuple[tuple[str, str], ...] = ()
    recipe_url: str = ""
    # Per-precision hardware when a recipe validates each checkpoint on different nodes.
    quantization_node_ids: tuple[tuple[str, tuple[str, ...]], ...] = ()


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

    @property
    def chip(self) -> Literal["GPU", "TPU"]:
        """Accelerator unit; Cloud TPU machines name their TPU chips in `gpu`."""
        return "TPU" if "TPU" in self.gpu else "GPU"

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
    active_days: int
    input_tokens: int
    output_tokens: int
    window_hours: float = 24
    scheduled: bool = False


@dataclass(frozen=True, slots=True)
class APIRates:
    """USD token rates that replace a baseline's standard rates for a whole request."""

    input_per_million: float
    output_per_million: float
    cache_read_per_million: float
    cache_write_per_million: float
    cache_storage_per_million_hour: float = 0


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
    # How long a cached prefix lives, as the cache notes name it.
    cache_retention: str = field(default="", kw_only=True)
    # Requests with more input tokens than the threshold pay long_prompt_rates in full.
    long_prompt_threshold: int = field(default=0, kw_only=True)
    long_prompt_rates: APIRates | None = field(default=None, kw_only=True)
    # Announced rates and note that apply after valid_through.
    post_validity_rates: APIRates | None = field(default=None, kw_only=True)
    post_validity_note: str = field(default="", kw_only=True)

    def __post_init__(self) -> None:
        """Fail at import when a pricing rule is only half described."""
        if not self.cache_retention:
            msg = f"{self.name}: cache_retention is required"
            raise ValueError(msg)
        if (self.long_prompt_threshold > 0) != (self.long_prompt_rates is not None):
            msg = f"{self.name}: long_prompt_threshold and long_prompt_rates must be set together"
            raise ValueError(msg)
        if bool(self.valid_through) != (self.post_validity_rates is not None) or bool(self.valid_through) != bool(
            self.post_validity_note
        ):
            msg = f"{self.name}: valid_through, post_validity_rates, and post_validity_note must be set together"
            raise ValueError(msg)
        if self.long_prompt_rates is not None and self.post_validity_rates is not None:
            # A single rate table cannot say which tier survives the date change.
            msg = f"{self.name}: long-prompt tiers after valid_through are not modeled; add a fresh snapshot"
            raise ValueError(msg)


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
    output_tokens_request: int
    input_tokens_request: int
    requests_per_day: float
    active_days: int
    demand_window_hours: float
    api_mode: APIMode
    cache_prefix_tokens: int
    cache_requests: int
    concurrency: int
    target_first_token: float
    target_completion: float
    measured_concurrency: int
    measured_first_token: float
    measured_completion: float
    billing_plan: BillingPlan = BillingPlan.ON_DEMAND
    pilot_config: str = ""
    mode: str = "advanced"


@dataclass(frozen=True, slots=True)
class HostingEstimate:
    weight_memory_gb: float
    required_memory_gb: float
    nodes_per_replica: int
    total_nodes: int
    total_gpus: int
    compute_monthly_usd: float
    control_monthly_usd: float
    total_monthly_usd: float
    capacity_tokens_month: float
    capacity_requests_day: float
    requests_month: float
    input_tokens_month: float
    output_tokens_month: float
    demand_capacity_pct: float
    window_capacity_pct: float
    required_output_tokens_per_second: float
    usable_output_tokens_per_second: float
    capacity_requests_month: int
    per_thousand_requests_usd: float
    demand_fits: bool
    context_issue: str
    topology_confirmed: bool
    qualified: bool
    compatibility_issue: str
    daily_demand_fits: bool


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
    node: GKENodePool
    url: str


@dataclass(frozen=True, slots=True)
class AcceleratorComparison:
    family: str
    quantization: Quantization
    node: GKENodePool
    estimate: HostingEstimate
    url: str


@dataclass(frozen=True, slots=True)
class ModelComparison:
    model: FrontierModel
    # Each catalog model is sized on its own automatic checkpoint and machine.
    quantization: Quantization
    node: GKENodePool
    estimate: HostingEstimate
    decision: str


@dataclass(frozen=True, slots=True)
class PlotLine:
    name: str
    points: str
    # 0 is the fleet; API series keep their baseline position so styles stay stable.
    series: int


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
    unavailable: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SensitivityCell:
    url: str
    verdict: str
    inputs: HostingInputs
    capacity_pct: float
    cheapest_api_usd: float | None
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
    selected_quant: Quantization
    estimate: HostingEstimate
    comparison: tuple[ModelComparison, ...]
    validation: tuple[str, ...]
    snapshot_date: str
    presets: tuple[DemandPreset, ...]
    apis: tuple[APIComparison, ...]
    precisions: tuple[PrecisionComparison, ...]
    accelerators: tuple[AcceleratorComparison, ...]
    demand_label: str
    selected_preset: DemandPreset
    window_is_auto: bool
    custom_requests: bool
    budget_low_usd: float
    budget_high_usd: float
    cost_plot: CostPlot
    sensitivity: tuple[SensitivityRow, ...]
    latency_title: str
    latency_detail: str
    model_source_url: str
    gke_source_url: str
    cluster_hourly_usd: float
    price_source_url: str
    current_pilot_config: str
    comparison_ready: bool
    # Exact serialized values keep resubmitted forms identical to shareable URLs.
    form_values: dict[str, str]
    advanced_url: str
    simple_url: str
