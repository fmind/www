"""Shared serving assumptions, hardware compatibility, and sizing physics."""

from collections.abc import Sequence
from dataclasses import replace
from math import ceil

from .data import FRONTIER_MODELS, GKE_NODE_POOLS, QUANTIZATIONS
from .models import APIMode, BillingPlan, DemandPreset, FrontierModel, GKENodePool, HostingInputs, Quantization

MONTHLY_HOURS = 730.0


def serving_capacity(inputs: HostingInputs) -> tuple[float, float]:
    """Return monthly output tokens and requests per active-day window."""
    usable_rate = inputs.tokens_per_second * inputs.replicas * inputs.target_utilization / 100
    # Paid hours can be scheduled inside active windows. Applying the monthly
    # running fraction to each window would count downtime a second time.
    running_hours = MONTHLY_HOURS * (inputs.duty_cycle_percent / 100)
    return (
        usable_rate * running_hours * 3600,
        usable_rate * inputs.demand_window_hours * 60 * 60 / inputs.output_tokens_request,
    )


def replicas_for_demand(inputs: HostingInputs) -> int:
    """Round up complete model copies to cover both monthly and window demand."""
    monthly_tokens, daily_requests = serving_capacity(replace(inputs, replicas=1))
    return max(
        1,
        ceil(inputs.requests_per_day * inputs.active_days * inputs.output_tokens_request / monthly_tokens),
        ceil(inputs.requests_per_day / daily_requests),
    )


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
    nodes = max(minimum, ceil(required_memory / node.vram_gb))
    if nodes > 1 and node.id == "ct6e-standard-8t":
        # Trillium 2D torus slices scale in powers of two: 8, 16, 32, 64, 128, or 256 chips (1..32 8-chip units).
        return 1 << (nodes - 1).bit_length()
    if nodes > 1 and node.id == "tpu7x-standard-4t":
        # Ironwood 3D torus slices are 1, 2, 4, 8, or 16 4-chip hosts up to one 64-chip cube, then multiples of 16.
        return 1 << (nodes - 1).bit_length() if nodes <= 16 else ceil(nodes / 16) * 16
    return nodes


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
    nodes = nodes_for_model(model, node, required)
    if nodes > 1 and not node.multi_host:
        return (
            f"{model.name} does not fit on one {node.name}; this catalog does not support sharding across those nodes"
        )
    if node.id == "ct6e-standard-8t" and nodes > 32:
        return f"{model.name} exceeds the 256-chip Cloud TPU v6e Trillium pod limit"
    if inputs.billing_plan is BillingPlan.FLEX and inputs.api_mode is not APIMode.BATCH:
        return "Flex-start queues bounded jobs and does not support this interactive serving comparison; select batch or reserved capacity"
    return ""


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


def automatic_setup(
    inputs: HostingInputs,
    plan: BillingPlan,
    *,
    keep_checkpoint: bool = False,
    pools: Sequence[GKENodePool] = GKE_NODE_POOLS,
) -> tuple[HostingInputs, GKENodePool]:
    """Pick the lowest-cost machine for the checkpoint, else for the model's next supported one.

    A checkpoint can lack hardware with this plan (Mistral Large 4 NVFP4 runs only on A4, which
    has no on-demand rate) or reject the workload (Nemotron NVFP4 on G4 stops at 16,384 context
    tokens). Unless the caller chose the precision, prefer the first checkpoint whose machine
    accepts the workload (the current one, the model default, then the other supported ones);
    otherwise keep the first compatible one, so the caller reports its limit.
    """
    model = find_model(inputs.model_id)
    others = () if keep_checkpoint else (model.default_quantization, *model.supported_quantizations)
    candidates = [replace(inputs, quantization_id=q) for q in dict.fromkeys((inputs.quantization_id, *others))]
    compatible: tuple[HostingInputs, GKENodePool] | None = None
    first_error: ValueError | None = None
    for candidate in candidates:
        try:
            node = automatic_node(candidate, plan, pools)
        except ValueError as exc:
            first_error = first_error or exc
            continue
        if not configuration_issue(replace(candidate, node_pool_id=node.id, billing_plan=plan)):
            return candidate, node
        compatible = compatible or (candidate, node)
    if compatible:
        return compatible
    raise first_error or ValueError(f"No compatible hardware for {model.name} under {plan}")


def workload_plans(preset: DemandPreset) -> tuple[BillingPlan, ...]:
    """Plans a workload takes without a commitment: batch jobs can queue on Flex-start, services cannot."""
    if preset.api_mode is APIMode.BATCH:
        return (BillingPlan.FLEX, BillingPlan.ON_DEMAND)
    return (BillingPlan.ON_DEMAND,)


def workload_setup(inputs: HostingInputs, preset: DemandPreset) -> tuple[str, HostingInputs, GKENodePool]:
    """Size the workload's default plan: the lowest-cost setup among its no-commitment plans."""
    model = find_model(inputs.model_id)
    best: tuple[tuple[bool, bool, float], BillingPlan, HostingInputs, GKENodePool] | None = None
    first_error: ValueError | None = None
    for plan in workload_plans(preset):
        try:
            candidate, node = automatic_setup(inputs, plan)
        except ValueError as exc:
            first_error = first_error or exc
            continue
        required = required_memory_gb(
            model, find_quantization(candidate.quantization_id), candidate.memory_overhead_pct
        )
        nodes = nodes_for_model(model, node, required)
        # Same order as automatic_node: a setup the workload fits, then one host, then price.
        rank = (
            bool(configuration_issue(replace(candidate, node_pool_id=node.id, billing_plan=plan))),
            nodes > 1,
            nodes * node.price(plan).hourly_usd,
        )
        if best is None or rank < best[0]:
            best = (rank, plan, candidate, node)
    if best is None:
        raise first_error or ValueError(f"No compatible hardware for {model.name}")
    return best[1].value, best[2], best[3]
