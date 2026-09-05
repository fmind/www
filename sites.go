package site

import (
	"fmt"
	"math"
	"net/url"
	"strconv"
	"time"

	"github.com/fmind/www/templates"
)

const (
	monthlyHours     = 730.0
	secondsPerMonth  = monthlyHours * 60 * 60
	secondsPerDay    = 24 * 60 * 60
	clusterHourlyUSD = 0.10
	modelSnapshot    = "2026-09-05"
	indexVersion     = "4.2"
)

var frontierModels = []templates.FrontierModel{
	{ID: "kimi-k3", Rank: 1, Name: "Kimi K3 (max)", Creator: "Moonshot AI", Intelligence: 50.2337, ParametersB: 2800, ActiveParameters: 104, ContextTokens: 1048576, License: "Kimi K3 License", LicenseClass: "Commercial license", AnalysisURL: "https://artificialanalysis.ai/models/kimi-k3", WeightsURL: "https://huggingface.co/moonshotai/Kimi-K3"},
	{ID: "glm-5-3", Rank: 2, Name: "GLM-5.3 (max)", Creator: "Z AI", Intelligence: 48.5840, ParametersB: 753, ActiveParameters: 40, ContextTokens: 1000000, License: "GLM-5.3 License", LicenseClass: "Commercial license", AnalysisURL: "https://artificialanalysis.ai/models/glm-5-3", WeightsURL: "https://huggingface.co/zai-org/GLM-5.3"},
	{ID: "qwen3-8-2-4t-a95b", Rank: 3, Name: "Qwen3.8 2.4T A95B", Creator: "Alibaba", Intelligence: 46.7403, ParametersB: 2400, ActiveParameters: 95, ContextTokens: 983616, License: "Qwen3.8-Max License", LicenseClass: "Commercial license", AnalysisURL: "https://artificialanalysis.ai/models/qwen3-8-2-4t-a95b", WeightsURL: "https://huggingface.co/Qwen/Qwen3.8-2.4T-A95B"},
	{ID: "glm-5-3-flash", Rank: 4, Name: "GLM-5.3-Flash", Creator: "Z AI", Intelligence: 46.2237, ParametersB: 320, ActiveParameters: 18, ContextTokens: 1000000, License: "MIT", LicenseClass: "Permissive", AnalysisURL: "https://artificialanalysis.ai/models/glm-5-3-flash", WeightsURL: "https://huggingface.co/zai-org/GLM-5.3-Flash"},
	{ID: "deepseek-v4-pro", Rank: 5, Name: "DeepSeek V4 Pro 0813 (max)", Creator: "DeepSeek", Intelligence: 42.1133, ParametersB: 1600, ActiveParameters: 49, ContextTokens: 1000000, License: "MIT", LicenseClass: "Permissive", AnalysisURL: "https://artificialanalysis.ai/models/deepseek-v4-pro", WeightsURL: "https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro-0813"},
	{ID: "qwen3-8-27b", Rank: 6, Name: "Qwen3.8 27B (xhigh)", Creator: "Alibaba", Intelligence: 41.6459, ParametersB: 27, ActiveParameters: 27, ContextTokens: 256000, License: "Apache 2.0", LicenseClass: "Permissive", AnalysisURL: "https://artificialanalysis.ai/models/qwen3-8-27b", WeightsURL: "https://huggingface.co/Qwen/Qwen3.8-27B"},
	{ID: "k2-horizon-375b-a23b", Rank: 7, Name: "K2 Horizon 375B A23B", Creator: "MBZUAI", Intelligence: 37.7507, ParametersB: 375, ActiveParameters: 23, ContextTokens: 524288, License: "Apache 2.0", LicenseClass: "Permissive", AnalysisURL: "https://artificialanalysis.ai/models/k2-horizon-375b-a23b", WeightsURL: "https://huggingface.co/IFM/K2-Horizon-375B-A23B"},
	{ID: "minimax-m3", Rank: 8, Name: "MiniMax-M3", Creator: "MiniMax", Intelligence: 35.7477, ParametersB: 428, ActiveParameters: 23, ContextTokens: 1000000, License: "MiniMax Community License", LicenseClass: "Commercial license", AnalysisURL: "https://artificialanalysis.ai/models/minimax-m3", WeightsURL: "https://huggingface.co/MiniMaxAI/MiniMax-M3"},
	{ID: "inkling", Rank: 9, Name: "Inkling (xhigh)", Creator: "Thinking Machines", Intelligence: 32.1865, ParametersB: 975, ActiveParameters: 41, ContextTokens: 1000000, License: "Apache 2.0", LicenseClass: "Permissive", AnalysisURL: "https://artificialanalysis.ai/models/inkling", WeightsURL: "https://huggingface.co/thinkingmachines/Inkling"},
	{ID: "muse-glimmer", Rank: 10, Name: "Muse Glimmer (high)", Creator: "Meta", Intelligence: 24.3773, ParametersB: 30, ActiveParameters: 30, ContextTokens: 131072, License: "Apache 2.0", LicenseClass: "Permissive", AnalysisURL: "https://artificialanalysis.ai/models/muse-glimmer", WeightsURL: "https://huggingface.co/meta-models/Muse-Glimmer-30B"},
}

var gkeNodePools = []templates.GKENodePool{
	{ID: "a4-cud-3y", Name: "A4 · 3-year resource CUD", GPU: "8× NVIDIA B200", GPUCount: 8, HBMGB: 1440, HourlyUSD: 56.7072, PriceModel: "3-year committed use", Committed: true, Operational: "Billed for the full term, even while idle. Capacity reservation and commitment required."},
	{ID: "a4-flex", Name: "A4 · DWS Flex-start", GPU: "8× NVIDIA B200", GPUCount: 8, HBMGB: 1440, HourlyUSD: 64.44, PriceModel: "Flex-start", Operational: "Batch-like provisioning; do not assume continuous online availability."},
	{ID: "a3-ultra", Name: "A3 Ultra · on-demand", GPU: "8× NVIDIA H200", GPUCount: 8, HBMGB: 1128, HourlyUSD: 84.806908493, PriceModel: "On-demand", Operational: "Validate regional stock, quota, and RDMA topology."},
	{ID: "a3-high", Name: "A3 High · on-demand", GPU: "8× NVIDIA H100", GPUCount: 8, HBMGB: 640, HourlyUSD: 88.490000119, PriceModel: "On-demand", Operational: "Validate regional stock, quota, and multi-host networking."},
	{ID: "a2-ultra-1g", Name: "A2 Ultra · on-demand", GPU: "1× NVIDIA A100 80GB", GPUCount: 1, HBMGB: 80, HourlyUSD: 5.06879789, PriceModel: "On-demand", Operational: "Best used for models that fit on one node; inter-node serving needs separate validation."},
}

var quantizations = []templates.Quantization{
	{ID: "fp4", Name: "4-bit · prioritize memory savings", BytesPerParam: 0.5, Guidance: "¼ of 16-bit weight memory. Validate reasoning, tool use, and accuracy before accepting the quality trade-off."},
	{ID: "fp8", Name: "8-bit · balanced starting experiment", BytesPerParam: 1, Guidance: "½ of 16-bit weight memory. A practical first compression test with a supported checkpoint and runtime."},
	{ID: "fp16", Name: "16-bit · precision reference", BytesPerParam: 2, Guidance: "Full weight memory as a precision reference. Expanding quantized weights cannot recover lost quality."},
}

// Presets describe demand only; choosing one preserves the user's fleet experiment.
var demandPresets = []templates.DemandPreset{
	{ID: "single-job", Name: "Single job", Description: "Process 100 documents once: 100 requests on one day, 4,000 input / 1,000 output tokens each.", RequestsPerDay: 100, ActiveDays: 1, InputTokens: 4000, OutputTokens: 1000},
	{ID: "small-team", Name: "Small team · 5–10 people", Description: "Example: 8 people × 20 requests × 22 workdays, 2,000 input / 600 output tokens each.", RequestsPerDay: 160, ActiveDays: 22, InputTokens: 2000, OutputTokens: 600},
	{ID: "department", Name: "Department · 50 people", Description: "50 people × 40 requests × 22 workdays, 4,000 input / 1,000 output tokens each.", RequestsPerDay: 2000, ActiveDays: 22, InputTokens: 4000, OutputTokens: 1000},
	{ID: "service", Name: "Busy customer service", Description: "100,000 requests per day × 30 days, 1,000 input / 300 output tokens each. Test peak traffic too.", RequestsPerDay: 100000, ActiveDays: 30, InputTokens: 1000, OutputTokens: 300},
}

var defaultHostingInputs = templates.HostingInputs{
	ModelID:             "qwen3-8-27b",
	NodePoolID:          "a2-ultra-1g",
	QuantizationID:      "fp8",
	Replicas:            1,
	DutyCyclePercent:    100,
	MemoryOverheadPct:   15,
	TokensPerSecond:     100,
	TargetUtilization:   65,
	OutputTokensRequest: 600,
	InputTokensRequest:  2000,
	RequestsPerDay:      160,
	ActiveDays:          22,
	PlatformMonthlyUSD:  1000,
	APIMode:             "standard", CachePrefixTokens: 1024, CacheRequests: 20,
	Concurrency: 8, TargetFirstToken: 2, TargetCompletion: 30,
	TasksPerMonth: 1000, ReviewHourlyUSD: 40,
	Quality: [4]templates.TaskQuality{{AcceptancePercent: 90, CallsPerTask: 1, ReviewMinutes: 1}, {AcceptancePercent: 90, CallsPerTask: 1, ReviewMinutes: 1}, {AcceptancePercent: 90, CallsPerTask: 1, ReviewMinutes: 1}, {AcceptancePercent: 90, CallsPerTask: 1, ReviewMinutes: 1}},
}

func llmSelfHostingView(query url.Values) templates.LLMSelfHostingView {
	return llmSelfHostingViewAt(query, time.Now())
}

func llmSelfHostingViewAt(query url.Values, now time.Time) templates.LLMSelfHostingView {
	inputs := defaultHostingInputs
	validation := make([]string, 0)

	inputs.ModelID = parseChoice(query, "model", inputs.ModelID, modelIDs(), &validation)
	inputs.NodePoolID = parseChoice(query, "node", inputs.NodePoolID, nodePoolIDs(), &validation)
	inputs.QuantizationID = parseChoice(query, "quant", inputs.QuantizationID, quantizationIDs(), &validation)
	inputs.Replicas = parseBoundedInt(query, "replicas", inputs.Replicas, 1, 8, &validation)
	inputs.DutyCyclePercent = parseBoundedFloat(query, "duty", inputs.DutyCyclePercent, 0.1, 100, &validation)
	inputs.MemoryOverheadPct = parseBoundedFloat(query, "overhead", inputs.MemoryOverheadPct, 0, 50, &validation)
	inputs.TokensPerSecond = parseBoundedFloat(query, "throughput", inputs.TokensPerSecond, 0.1, 1000000, &validation)
	inputs.TargetUtilization = parseBoundedFloat(query, "utilization", inputs.TargetUtilization, 1, 95, &validation)
	inputs.OutputTokensRequest = parseBoundedFloat(query, "tokens", inputs.OutputTokensRequest, 1, 1000000, &validation)
	inputs.InputTokensRequest = parseBoundedFloat(query, "input-tokens", inputs.InputTokensRequest, 1, 1000000, &validation)
	inputs.RequestsPerDay = parseBoundedFloat(query, "requests", inputs.RequestsPerDay, 1, 10000000, &validation)
	inputs.ActiveDays = parseBoundedFloat(query, "days", inputs.ActiveDays, 1, 31, &validation)
	inputs.PlatformMonthlyUSD = parseBoundedFloat(query, "platform", inputs.PlatformMonthlyUSD, 0, 10000000, &validation)
	applyDemandPreset(query.Get("preset"), &inputs, &validation)

	parseHostingOptions(query, &inputs, &validation)

	model := findModel(inputs.ModelID)
	node := findNodePool(inputs.NodePoolID)
	quant := findQuantization(inputs.QuantizationID)
	estimate := estimateHosting(model, node, quant, inputs)
	baselines := currentAPIBaselines(now, inputs)
	apis := compareAPIs(inputs, estimate, baselines)
	for i := range apis {
		apis[i].NeedsReview = now.UTC().Format(time.DateOnly) >= apis[i].Baseline.ReviewOn
		apis[i].Freshness = "Verified " + apis[i].Baseline.VerifiedOn + " · review by " + apis[i].Baseline.ReviewOn
		if apis[i].NeedsReview {
			apis[i].Freshness += " · review overdue: check the linked price before deciding"
		}
	}
	latencyTitle, latencyDetail := hostingLatency(inputs)
	precisions := make([]templates.PrecisionComparison, 0, len(quantizations))
	for _, precision := range quantizations {
		precisions = append(precisions, templates.PrecisionComparison{Quantization: precision, Estimate: estimateHosting(model, node, precision, inputs)})
	}
	comparison := make([]templates.ModelComparison, 0, len(frontierModels))
	for _, candidate := range frontierModels {
		candidateEstimate := estimateHosting(candidate, node, quant, inputs)
		comparison = append(comparison, templates.ModelComparison{
			Model:    candidate,
			Estimate: candidateEstimate,
			Decision: hostingDecision(candidate, node, candidateEstimate),
		})
	}

	return templates.LLMSelfHostingView{
		Inputs: inputs, Models: frontierModels, NodePools: gkeNodePools, Quantizations: quantizations,
		SelectedModel: model, SelectedNode: node, SelectedQuant: quant, Estimate: estimate,
		Comparison: comparison, Validation: validation, SnapshotDate: modelSnapshot, IndexVersion: indexVersion,
		Presets: demandPresets, APIs: apis, Precisions: precisions, DemandLabel: demandLabel(inputs),
		CostPlot: hostingCostPlot(inputs, estimate, apis), Sensitivity: hostingSensitivity(inputs, baselines),
		Tasks: hostingTasks(inputs, estimate, baselines), LatencyTitle: latencyTitle, LatencyDetail: latencyDetail,
		ModelSourceURL: "https://artificialanalysis.ai/models",
		GKESourceURL:   "https://cloud.google.com/kubernetes-engine/pricing",
		PriceSourceURL: "https://cloud.google.com/products/compute/pricing/accelerator-optimized",
	}
}

func estimateHosting(model templates.FrontierModel, node templates.GKENodePool, quant templates.Quantization, inputs templates.HostingInputs) templates.HostingEstimate {
	weightMemory := model.ParametersB * quant.BytesPerParam
	requiredMemory := weightMemory * (1 + inputs.MemoryOverheadPct/100)
	nodesPerReplica := max(1, int(math.Ceil(requiredMemory/node.HBMGB)))
	totalNodes := nodesPerReplica * inputs.Replicas
	duty := inputs.DutyCyclePercent / 100
	paidDuty := duty
	// Stopping a committed VM reduces serving time, never the contractual bill.
	if node.Committed {
		paidDuty = 1
	}
	computeMonthly := float64(totalNodes) * node.HourlyUSD * monthlyHours * paidDuty
	controlMonthly := clusterHourlyUSD * monthlyHours
	totalMonthly := computeMonthly + controlMonthly + inputs.PlatformMonthlyUSD
	capacity := inputs.TokensPerSecond * float64(inputs.Replicas) * (inputs.TargetUtilization / 100) * secondsPerMonth * duty
	requestsDay := inputs.TokensPerSecond * float64(inputs.Replicas) * (inputs.TargetUtilization / 100) * secondsPerDay * duty / inputs.OutputTokensRequest
	requests := inputs.RequestsPerDay * inputs.ActiveDays
	outputTokens := requests * inputs.OutputTokensRequest

	return templates.HostingEstimate{
		WeightMemoryGB: weightMemory, RequiredMemoryGB: requiredMemory, NodesPerReplica: nodesPerReplica,
		TotalNodes: totalNodes, TotalGPUs: totalNodes * node.GPUCount,
		ComputeMonthlyUSD: computeMonthly, ControlMonthlyUSD: controlMonthly,
		PlatformMonthlyUSD: inputs.PlatformMonthlyUSD, TotalMonthlyUSD: totalMonthly,
		CapacityTokensMonth: capacity, CapacityRequestsDay: requestsDay,
		RequestsMonth: requests, InputTokensMonth: requests * inputs.InputTokensRequest, OutputTokensMonth: outputTokens,
		DemandCapacityPct: outputTokens / capacity * 100, DemandFits: outputTokens <= capacity,
		PerThousandRequestsUSD: totalMonthly / requests * 1000,
	}
}

func applyDemandPreset(id string, inputs *templates.HostingInputs, validation *[]string) {
	if id == "" {
		return
	}
	for _, preset := range demandPresets {
		if preset.ID == id {
			inputs.RequestsPerDay, inputs.ActiveDays = preset.RequestsPerDay, preset.ActiveDays
			inputs.InputTokensRequest, inputs.OutputTokensRequest = preset.InputTokens, preset.OutputTokens
			return
		}
	}
	*validation = append(*validation, "preset was not recognized; the validated demand inputs were kept")
}

func demandLabel(inputs templates.HostingInputs) string {
	for _, preset := range demandPresets {
		if inputs.RequestsPerDay == preset.RequestsPerDay && inputs.ActiveDays == preset.ActiveDays && inputs.InputTokensRequest == preset.InputTokens && inputs.OutputTokensRequest == preset.OutputTokens {
			return preset.Name
		}
	}
	return "Custom demand"
}

func hostingDecision(model templates.FrontierModel, node templates.GKENodePool, estimate templates.HostingEstimate) string {
	if model.LicenseClass != "Permissive" {
		return "Review commercial terms"
	}
	if estimate.NodesPerReplica > 1 {
		return "Validate multi-node serving"
	}
	if estimate.RequiredMemoryGB < node.HBMGB*0.25 {
		return "Right-size the node pool"
	}
	return "Pilot on this topology"
}

func parseChoice(query url.Values, key, fallback string, allowed map[string]bool, validation *[]string) string {
	raw, present := query[key]
	if !present || len(raw) == 0 || raw[0] == "" {
		return fallback
	}
	if allowed[raw[0]] {
		return raw[0]
	}
	*validation = append(*validation, key+" was not recognized; the default was used")
	return fallback
}

func parseBoundedFloat(query url.Values, key string, fallback, minimum, maximum float64, validation *[]string) float64 {
	raw, present := query[key]
	if !present || len(raw) == 0 || raw[0] == "" {
		return fallback
	}
	value, err := strconv.ParseFloat(raw[0], 64)
	if err != nil || math.IsNaN(value) || math.IsInf(value, 0) || value < minimum || value > maximum {
		*validation = append(*validation, fmt.Sprintf("%s must be between %g and %g; the default was used", key, minimum, maximum))
		return fallback
	}
	return value
}

func parseBoundedInt(query url.Values, key string, fallback, minimum, maximum int, validation *[]string) int {
	raw, present := query[key]
	if !present || len(raw) == 0 || raw[0] == "" {
		return fallback
	}
	value, err := strconv.Atoi(raw[0])
	if err != nil || value < minimum || value > maximum {
		*validation = append(*validation, fmt.Sprintf("%s must be between %d and %d; the default was used", key, minimum, maximum))
		return fallback
	}
	return value
}

func modelIDs() map[string]bool {
	ids := make(map[string]bool, len(frontierModels))
	for _, model := range frontierModels {
		ids[model.ID] = true
	}
	return ids
}

func nodePoolIDs() map[string]bool {
	ids := make(map[string]bool, len(gkeNodePools))
	for _, node := range gkeNodePools {
		ids[node.ID] = true
	}
	return ids
}

func quantizationIDs() map[string]bool {
	ids := make(map[string]bool, len(quantizations))
	for _, quant := range quantizations {
		ids[quant.ID] = true
	}
	return ids
}

func findModel(id string) templates.FrontierModel {
	for _, model := range frontierModels {
		if model.ID == id {
			return model
		}
	}
	return frontierModels[0]
}

func findNodePool(id string) templates.GKENodePool {
	for _, node := range gkeNodePools {
		if node.ID == id {
			return node
		}
	}
	return gkeNodePools[0]
}

func findQuantization(id string) templates.Quantization {
	for _, quant := range quantizations {
		if quant.ID == id {
			return quant
		}
	}
	return quantizations[0]
}
