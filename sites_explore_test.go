package site

import (
	"math"
	"net/url"
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/fmind/www/templates"
)

func hostingTestView(query url.Values) templates.LLMSelfHostingView {
	return llmSelfHostingViewAt(query, time.Date(2026, time.September, 5, 12, 0, 0, 0, time.UTC))
}

func TestAPIModesIncludeWarmupAndStorage(t *testing.T) {
	batch := hostingTestView(url.Values{"api-mode": {"batch"}})
	for i, want := range []float64{6.60, 17.60, 88} {
		if math.Abs(batch.APIs[i].MonthlyUSD-want) > 1e-9 {
			t.Errorf("batch %d=%g, want %g", i, batch.APIs[i].MonthlyUSD, want)
		}
	}
	cached := hostingTestView(url.Values{"api-mode": {"cached"}, "cache-prefix": {"4096"}, "input-tokens": {"6000"}, "tokens": {"500"}, "requests": {"20"}, "days": {"1"}})
	// One 20-call group: 4,096 shared tokens, 1,904 fresh tokens, 500 output tokens.
	for i, want := range []float64{.07237466666666667, .2019648, 1.009824} {
		if math.Abs(cached.APIs[i].MonthlyUSD-want) > 1e-9 {
			t.Errorf("cached %d=%g, want %g", i, cached.APIs[i].MonthlyUSD, want)
		}
	}
	inputs := cached.Inputs
	for _, baseline := range currentAPIBaselines(time.Date(2026, 9, 5, 0, 0, 0, 0, time.UTC), inputs) {
		_, one := apiMonthlyCost(inputs, baseline, 20)
		_, partial := apiMonthlyCost(inputs, baseline, 21)
		if partial != one*2 {
			t.Errorf("%s partial group overhead=%g, want %g", baseline.Name, partial, one*2)
		}
	}
	fallback := hostingTestView(url.Values{"api-mode": {"cached"}})
	if fallback.APIs[0].MonthlyUSD != 13.2 || !strings.Contains(fallback.APIs[0].ModeNote, "Standard rates applied") || fallback.APIs[1].MonthlyUSD >= 35.2 {
		t.Fatal("cache minimum must apply per provider", fallback.APIs)
	}
	invalidPrefix := hostingTestView(url.Values{"api-mode": {"cached"}, "cache-prefix": {"9999"}})
	if invalidPrefix.APIs[1].MonthlyUSD != 35.2 {
		t.Fatal("a prefix cannot exceed the input budget")
	}
}

func TestCacheBreakEvenIsFirstWholeRequest(t *testing.T) {
	view := hostingTestView(url.Values{"api-mode": {"cached"}, "cache-prefix": {"4096"}, "input-tokens": {"6000"}})
	for _, row := range view.APIs {
		before, _ := apiMonthlyCost(view.Inputs, row.Baseline, row.BreakEvenRequests-1)
		at, _ := apiMonthlyCost(view.Inputs, row.Baseline, row.BreakEvenRequests)
		if before >= view.Estimate.TotalMonthlyUSD || at < view.Estimate.TotalMonthlyUSD {
			t.Errorf("%s break-even did not straddle fleet bill", row.Baseline.Name)
		}
	}
}

func TestPriceExpiryAndReviewAreVisible(t *testing.T) {
	before := llmSelfHostingViewAt(nil, time.Date(2026, 12, 31, 23, 59, 0, 0, time.UTC))
	after := llmSelfHostingViewAt(nil, time.Date(2027, 1, 1, 0, 0, 0, 0, time.UTC))
	if after.APIs[0].MonthlyUSD != before.APIs[0].MonthlyUSD*2 || after.APIs[1].MonthlyUSD != before.APIs[1].MonthlyUSD {
		t.Fatal("announced rate change must be date-specific and provider-specific")
	}
	if !after.APIs[0].NeedsReview || !strings.Contains(after.APIs[0].Freshness, "overdue") {
		t.Fatal("old snapshots must disclose overdue source review")
	}
	if hostingTestView(nil).APIs[0].NeedsReview {
		t.Fatal("current verified snapshot must not be overdue")
	}
}

func TestScenarioLinksPreserveAllAssumptions(t *testing.T) {
	view := hostingTestView(url.Values{"quality": {"on"}, "api-mode": {"cached"}, "quality-2-calls": {"2.5"}, "measured-first": {"1.3"}, "cache-requests": {"7"}})
	for _, raw := range []string{hostingURL(view.Inputs), view.CostPlot.Frames[view.CostPlot.Selected].URL} {
		parsed, err := url.Parse(raw)
		if err != nil {
			t.Fatal(err)
		}
		roundTrip := hostingTestView(parsed.Query())
		if !reflect.DeepEqual(roundTrip.Inputs, view.Inputs) || len(roundTrip.Validation) > 0 {
			t.Fatalf("scenario lost inputs: %+v", roundTrip.Inputs)
		}
	}
	for i, row := range view.Sensitivity {
		for j, cell := range row.Cells {
			parsed, err := url.Parse(cell.URL)
			if err != nil {
				t.Fatal(err)
			}
			candidate := hostingTestView(parsed.Query())
			if candidate.Inputs != cell.Inputs || len(candidate.Validation) > 0 {
				t.Fatalf("cell %d,%d lost state", i, j)
			}
			if i == 1 && j == 1 && candidate.Inputs != view.Inputs {
				t.Fatal("center must be the current scenario")
			}
		}
	}
}

func TestCostExplorerFramesUseBillingAndCapacity(t *testing.T) {
	view := hostingTestView(nil)
	current := view.CostPlot.Frames[view.CostPlot.Selected]
	if current.Requests != view.Estimate.RequestsMonth || !strings.Contains(current.Summary, "$13.20") || view.CostPlot.CapacityX == "" || len(view.CostPlot.BreakEvens) != 3 {
		t.Fatal("plot must include current demand, capacity and API crossings")
	}
	previous := 0.0
	for _, frame := range view.CostPlot.Frames {
		if frame.Requests <= previous || strings.Contains(frame.X, "NaN") {
			t.Fatal("chart samples must be ordered and finite")
		}
		previous = frame.Requests
	}
	extreme := hostingTestView(url.Values{"requests": {"10000000"}, "days": {"31"}, "throughput": {"0.1"}})
	if extreme.CostPlot.Frames[extreme.CostPlot.Selected].Requests != 310000000 || !strings.Contains(extreme.CostPlot.Frames[extreme.CostPlot.Selected].Summary, "beyond") {
		t.Fatal("upper-bound demand must remain representable")
	}
}

func TestAcceptedTaskCostIncludesRetriesReviewAndCapacity(t *testing.T) {
	view := hostingTestView(url.Values{"quality": {"on"}, "tasks": {"1000"}, "review-rate": {"60"}, "quality-1-acceptance": {"50"}, "quality-1-calls": {"2"}, "quality-1-review": {"3"}})
	row := view.Tasks[1]
	// 2,000 calls cost $7.50; 3,000 review minutes cost $3,000; 500 tasks pass.
	if row.Requests != 2000 || row.Accepted != 500 || row.ModelUSD != 7.5 || row.ReviewUSD != 3000 || row.PerAcceptedUSD != 6.015 {
		t.Fatalf("unexpected task cost: %+v", row)
	}
	overloaded := hostingTestView(url.Values{"tasks": {"10000000"}, "quality-0-calls": {"100"}})
	if overloaded.Tasks[0].Fits {
		t.Fatal("retry workload must respect fleet capacity")
	}
}

func TestLatencyDoesNotFollowMonthlyCapacity(t *testing.T) {
	view := hostingTestView(nil)
	if !view.Estimate.DemandFits || view.LatencyTitle != "Responsiveness is still unproved" {
		t.Fatal("monthly spare capacity is not latency evidence")
	}
	query := url.Values{"measured-concurrency": {"8"}, "measured-first": {"1.5"}, "measured-complete": {"25"}}
	pass := hostingTestView(query)
	if pass.LatencyTitle != "The recorded pilot meets your latency targets" {
		t.Fatal(pass.LatencyTitle)
	}
	query.Set("measured-first", "3")
	if hostingTestView(query).LatencyTitle != "The recorded pilot misses a latency target" {
		t.Fatal("slow first-token measurement must fail latency target")
	}
	query.Set("measured-concurrency", "7")
	if hostingTestView(query).LatencyTitle != "Responsiveness is still unproved" {
		t.Fatal("insufficient pilot concurrency cannot prove target")
	}
}

func TestOptionalInputValidation(t *testing.T) {
	view := hostingTestView(url.Values{"api-mode": {"free"}, "cache-requests": {"0"}, "measured-first": {"NaN"}, "quality-0-acceptance": {"-1"}, "quality-1-calls": {"0.5"}, "quality": {"yes"}})
	if len(view.Validation) != 6 || view.Inputs != defaultHostingInputs {
		t.Fatalf("invalid options must fail to explicit defaults: %+v", view.Validation)
	}
}

func TestZeroAcceptanceAndInconsistentLatency(t *testing.T) {
	view := hostingTestView(url.Values{"quality": {"on"}, "quality-0-acceptance": {"0"}, "measured-first": {"10"}, "measured-complete": {"5"}, "measured-concurrency": {"8"}})
	if view.Tasks[0].Accepted != 0 || math.IsNaN(view.Tasks[0].PerAcceptedUSD) || len(view.Validation) != 1 || view.Inputs.MeasuredFirstToken != 0 || view.LatencyTitle != "Responsiveness is still unproved" {
		t.Fatal("invalid pilot evidence must not imply usable quality or latency")
	}
}
