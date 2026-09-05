package templates

import "testing"

func TestHostingFormatsReadableNumbersAndPlurals(t *testing.T) {
	for _, tc := range []struct{ got, want string }{
		{FormatUSD2(6.015), "$6.02"},
		{FormatUSD2(2.675), "$2.68"},
		{FormatUSD2(4773.2224597), "$4,773.22"},
		{FormatUSD(10000000), "$10,000,000"},
		{FormatDecimal(3520, 0), "3,520"},
		{FormatDecimal(999.995, 2), "1,000.00"},
		{FormatCount(1, "node"), "1 node"},
		{FormatCount(2, "GPU"), "2 GPUs"},
	} {
		if tc.got != tc.want {
			t.Errorf("got %q, want %q", tc.got, tc.want)
		}
	}
}

func TestHostingRecommendationUsesCheapestEligibleAPI(t *testing.T) {
	view := LLMSelfHostingView{Estimate: HostingEstimate{DemandFits: true, TotalMonthlyUSD: 20}, APIs: []APIComparison{{Baseline: APIBaseline{Name: "Gemini"}, MonthlyUSD: 30}, {Baseline: APIBaseline{Name: "Claude"}, MonthlyUSD: 10}}}
	if hostingDecisionTitle(view) != "Start with an API on cost grounds" || cheapestHostingAPI(view).Baseline.Name != "Claude" {
		t.Fatal("cache eligibility can change which API is cheapest")
	}
}
