package site

import (
	"math"
	"net/url"
	"testing"
)

func TestEstimateHostingUsesWholeNodesAndCompleteMonthlyCost(t *testing.T) {
	model := findModel("qwen3-8-27b")
	node := findNodePool("a2-ultra-1g")
	quant := findQuantization("fp16")
	inputs := defaultHostingInputs
	inputs.Replicas = 2
	inputs.DutyCyclePercent = 50
	inputs.MemoryOverheadPct = 25
	inputs.TokensPerSecond = 10
	inputs.TargetUtilization = 50
	inputs.OutputTokensRequest = 1000
	inputs.PlatformMonthlyUSD = 1000

	estimate := estimateHosting(model, node, quant, inputs)

	if estimate.RequiredMemoryGB != 67.5 || estimate.NodesPerReplica != 1 || estimate.TotalNodes != 2 || estimate.TotalGPUs != 2 {
		t.Fatalf("unexpected footprint: %+v", estimate)
	}
	wantTotal := 2*node.HourlyUSD*monthlyHours*0.5 + clusterHourlyUSD*monthlyHours + 1000
	if math.Abs(estimate.TotalMonthlyUSD-wantTotal) > 1e-9 {
		t.Errorf("monthly cost = %f, want %f", estimate.TotalMonthlyUSD, wantTotal)
	}
	wantTokens := 10.0 * 2 * 0.5 * secondsPerMonth * 0.5
	if estimate.CapacityTokensMonth != wantTokens {
		t.Errorf("monthly token capacity = %f, want %f", estimate.CapacityTokensMonth, wantTokens)
	}
}

func TestLLMSelfHostingViewRejectsInvalidQueryValues(t *testing.T) {
	view := hostingTestView(url.Values{
		"model":      {"unknown"},
		"replicas":   {"0"},
		"throughput": {"NaN"},
	})

	if view.Inputs.ModelID != defaultHostingInputs.ModelID || view.Inputs.Replicas != defaultHostingInputs.Replicas || view.Inputs.TokensPerSecond != defaultHostingInputs.TokensPerSecond {
		t.Fatalf("invalid inputs did not fall back to defaults: %+v", view.Inputs)
	}
	if len(view.Validation) != 3 {
		t.Fatalf("validation messages = %d, want 3: %v", len(view.Validation), view.Validation)
	}
}

func TestDemandPresetsPreserveFleetAndAllowManualEdits(t *testing.T) {
	for _, preset := range demandPresets {
		t.Run(preset.ID, func(t *testing.T) {
			view := hostingTestView(url.Values{"preset": {preset.ID}, "replicas": {"3"}, "quant": {"fp16"}, "requests": {"999"}})
			if view.Inputs.Replicas != 3 || view.Inputs.QuantizationID != "fp16" {
				t.Fatalf("preset changed fleet: %+v", view.Inputs)
			}
			if view.Estimate.RequestsMonth != preset.RequestsPerDay*preset.ActiveDays || view.Inputs.InputTokensRequest != preset.InputTokens || view.Inputs.OutputTokensRequest != preset.OutputTokens || view.DemandLabel != preset.Name {
				t.Fatalf("preset demand mismatch: %+v", view)
			}
		})
	}
	view := hostingTestView(url.Values{"requests": {"7"}, "days": {"2"}})
	if view.DemandLabel != "Custom demand" || view.Estimate.RequestsMonth != 14 {
		t.Fatalf("manual demand overridden: %+v", view)
	}
}

func TestAPIBaselinesChargeBothTokenDirectionsAtActualDemand(t *testing.T) {
	view := hostingTestView(url.Values{"preset": {"small-team"}})
	// 8 people * 20 requests * 22 days = 3,520 calls, each 2k in / 600 out.
	for i, want := range []float64{13.20, 35.20, 176} {
		if got := view.APIs[i].MonthlyUSD; math.Abs(got-want) > 1e-9 {
			t.Errorf("%s monthly = %g, want %g", view.APIs[i].Baseline.Name, got, want)
		}
	}
	if !view.Estimate.DemandFits || view.Estimate.OutputTokensMonth != 2112000 || view.Estimate.InputTokensMonth != 7040000 {
		t.Fatalf("unexpected small-team estimate: %+v", view.Estimate)
	}
	job := hostingTestView(url.Values{"preset": {"single-job"}})
	if math.Abs(job.APIs[0].MonthlyUSD-0.675) > 1e-9 || job.Estimate.TotalMonthlyUSD != view.Estimate.TotalMonthlyUSD {
		t.Fatal("single job must reduce API usage without silently shutting down the fleet")
	}
}

func TestCommitmentChargesIdleTimeWhileOnDemandCanStop(t *testing.T) {
	for _, node := range []string{"a4-cud-3y", "a2-ultra-1g"} {
		full := hostingTestView(url.Values{"node": {node}})
		part := hostingTestView(url.Values{"node": {node}, "duty": {"25"}})
		wantCompute := full.Estimate.ComputeMonthlyUSD / 4
		if full.SelectedNode.Committed {
			wantCompute = full.Estimate.ComputeMonthlyUSD
		}
		if part.Estimate.ComputeMonthlyUSD != wantCompute || part.Estimate.CapacityTokensMonth != full.Estimate.CapacityTokensMonth/4 {
			t.Errorf("%s runtime and bill diverged incorrectly: full=%+v part=%+v", node, full.Estimate, part.Estimate)
		}
		if part.Estimate.PlatformMonthlyUSD != full.Estimate.PlatformMonthlyUSD || part.Estimate.ControlMonthlyUSD != full.Estimate.ControlMonthlyUSD {
			t.Error("stopping nodes must not prorate monthly labor or the cluster fee")
		}
	}
}

func TestCapacityShortfallAndUnreachableBreakEven(t *testing.T) {
	view := hostingTestView(url.Values{"preset": {"service"}, "throughput": {"0.1"}})
	if view.Estimate.DemandFits || view.Estimate.DemandCapacityPct <= 100 {
		t.Fatal("overloaded fleet must flag a shortfall")
	}
	for _, row := range view.APIs {
		if row.BreakEvenFits {
			t.Errorf("%s break-even should exceed capacity", row.Baseline.Name)
		}
	}
	fast := hostingTestView(url.Values{"preset": {"service"}, "throughput": {"10000"}})
	if !fast.Estimate.DemandFits || !fast.APIs[0].BreakEvenFits {
		t.Fatal("higher measured throughput should permit demand and break-even")
	}
	if fast.Estimate.TotalMonthlyUSD != view.Estimate.TotalMonthlyUSD || fast.APIs[0].MonthlyUSD != view.APIs[0].MonthlyUSD {
		t.Fatal("capacity assumption must not change demand or fixed cost")
	}
	row := fast.APIs[0]
	price := row.PerThousandRequestsUSD / 1000
	if row.BreakEvenRequests*price < fast.Estimate.TotalMonthlyUSD || (row.BreakEvenRequests-1)*price >= fast.Estimate.TotalMonthlyUSD {
		t.Fatal("break-even must be the first whole request covering the fleet bill")
	}
}

func TestAstraLongContextPricingBoundary(t *testing.T) {
	short := hostingTestView(url.Values{"input-tokens": {"272000"}})
	long := hostingTestView(url.Values{"input-tokens": {"272001"}})
	if short.APIs[2].Baseline.InputPerMillion != 10 || short.APIs[2].Baseline.OutputPerMillion != 50 || long.APIs[2].Baseline.InputPerMillion != 20 || long.APIs[2].Baseline.OutputPerMillion != 75 {
		t.Fatal("Astra must apply full-request long-context rates only above 272K input tokens")
	}
	if long.APIs[0].Baseline.InputPerMillion != short.APIs[0].Baseline.InputPerMillion {
		t.Fatal("Astra price tier must not affect another baseline")
	}
}

func TestDemandInputValidation(t *testing.T) {
	for _, key := range []string{"requests", "days", "input-tokens", "tokens", "duty"} {
		for _, invalid := range []string{"0", "-1", "NaN", "+Inf", "1e99", "oops"} {
			view := hostingTestView(url.Values{key: {invalid}})
			if len(view.Validation) != 1 || view.Inputs != defaultHostingInputs {
				t.Errorf("%s=%s did not fall back: %+v", key, invalid, view)
			}
		}
	}
	unknown := hostingTestView(url.Values{"preset": {"missing"}, "requests": {"7"}})
	if len(unknown.Validation) != 1 || unknown.Inputs.RequestsPerDay != 7 {
		t.Fatal("unknown preset must report an error and preserve validated demand")
	}
}

func TestPrecisionChangesMemoryButOnlyWholeNodesChangeBill(t *testing.T) {
	small := hostingTestView(nil)
	if small.Precisions[0].Estimate.WeightMemoryGB*4 != small.Precisions[2].Estimate.WeightMemoryGB || small.Precisions[0].Estimate.TotalMonthlyUSD != small.Precisions[2].Estimate.TotalMonthlyUSD {
		t.Fatal("all three precisions fit a 27B model in one A100 node")
	}
	large := hostingTestView(url.Values{"model": {"kimi-k3"}, "node": {"a4-cud-3y"}})
	if large.Precisions[0].Estimate.TotalNodes >= large.Precisions[2].Estimate.TotalNodes || large.Precisions[0].Estimate.TotalMonthlyUSD >= large.Precisions[2].Estimate.TotalMonthlyUSD {
		t.Fatal("lower weight precision must reduce billed nodes when crossing node boundaries")
	}
}

func TestLLMSelfHostingViewComparesAllRankedModels(t *testing.T) {
	view := hostingTestView(url.Values{"model": {"qwen3-8-27b"}, "node": {"a2-ultra-1g"}})

	if len(view.Models) != 10 || len(view.Comparison) != 10 {
		t.Fatalf("models=%d comparison=%d, want ten each", len(view.Models), len(view.Comparison))
	}
	for index, row := range view.Comparison {
		if row.Model.Rank != index+1 {
			t.Errorf("comparison[%d] rank = %d, want %d", index, row.Model.Rank, index+1)
		}
	}
	if view.Estimate.NodesPerReplica != 1 {
		t.Errorf("27B FP4 model needs %d A100 nodes per replica, want 1", view.Estimate.NodesPerReplica)
	}
}
