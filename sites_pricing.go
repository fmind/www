package site

import (
	"fmt"
	"math"
	"time"

	"github.com/fmind/www/templates"
)

// Each rate carries its own review date. Announced changes apply even to old shared URLs.
var apiBaselines = []templates.APIBaseline{
	{
		Name: "Gemini 3.8 Flash", InputPerMillion: .75, OutputPerMillion: 3.75, CacheReadPerMillion: .075, CacheStoragePerMillionHour: .5, CacheMinimum: 4096,
		SourceURL: "https://ai.google.dev/gemini-api/docs/pricing#gemini-3.8-flash", CacheURL: "https://ai.google.dev/gemini-api/docs/generate-content/caching",
		VerifiedOn: modelSnapshot, ReviewOn: "2026-10-05", ValidThrough: "2026-12-31", Note: "Introductory rates through Dec 31, 2026; input, output, cache reads, and storage double on Jan 1, 2027.",
	},
	{
		Name: "Claude Sonnet 5", InputPerMillion: 2, OutputPerMillion: 10, CacheReadPerMillion: .2, CacheWritePerMillion: 2.5, CacheMinimum: 1024,
		SourceURL: "https://platform.claude.com/docs/en/about-claude/pricing", CacheURL: "https://platform.claude.com/docs/en/build-with-claude/prompt-caching",
		VerifiedOn: modelSnapshot, ReviewOn: "2026-10-05", Note: "$2 / $10 is standard pricing; the previously announced September increase was canceled. No announced end date.",
	},
	{
		Name: "GPT-6 Astra", InputPerMillion: 10, OutputPerMillion: 50, CacheReadPerMillion: 1, CacheWritePerMillion: 12.5, CacheMinimum: 1024,
		SourceURL: "https://developers.openai.com/api/docs/models/gpt-6-astra", CacheURL: "https://developers.openai.com/api/docs/guides/prompt-caching",
		VerifiedOn: modelSnapshot, ReviewOn: "2026-10-05", Note: "OpenAI's published Astra name. Above 272,000 input tokens, full-request rates rise to $20 input / $75 output per million. No announced end date.",
	},
}

func currentAPIBaselines(now time.Time, inputs templates.HostingInputs) []templates.APIBaseline {
	rows := make([]templates.APIBaseline, len(apiBaselines))
	copy(rows, apiBaselines)
	for i := range rows {
		row := &rows[i]
		if row.ValidThrough != "" && now.UTC().Format(time.DateOnly) > row.ValidThrough {
			row.InputPerMillion *= 2
			row.OutputPerMillion *= 2
			row.CacheReadPerMillion *= 2
			row.CacheStoragePerMillionHour *= 2
			row.Note = "The announced January 2027 rates are applied. This snapshot needs a fresh source check."
		}
		if row.Name == "GPT-6 Astra" && inputs.InputTokensRequest > 272000 {
			row.InputPerMillion, row.OutputPerMillion = 20, 75
			row.CacheReadPerMillion, row.CacheWritePerMillion = 2, 25
		}
	}
	return rows
}

func apiMonthlyCost(inputs templates.HostingInputs, baseline templates.APIBaseline, requests float64) (total, overhead float64) {
	input := inputs.InputTokensRequest * requests * baseline.InputPerMillion
	output := inputs.OutputTokensRequest * requests * baseline.OutputPerMillion
	switch inputs.APIMode {
	case "batch":
		return (input + output) / 2e6, 0
	case "cached":
		prefix := inputs.CachePrefixTokens
		if prefix < baseline.CacheMinimum || prefix > inputs.InputTokensRequest {
			break
		}
		// Charge a whole warm-up for each group, including a partially filled last group.
		writes := math.Min(requests, math.Ceil(requests/float64(inputs.CacheRequests)))
		reads := requests - writes
		input = (inputs.InputTokensRequest - prefix) * requests * baseline.InputPerMillion
		if baseline.CacheStoragePerMillionHour > 0 {
			// Explicit Gemini caches serve every call and store each prefix for five minutes.
			reads = requests
			overhead = writes * prefix * baseline.CacheStoragePerMillionHour / 12
		} else {
			overhead = writes * prefix * baseline.CacheWritePerMillion
		}
		input += reads*prefix*baseline.CacheReadPerMillion + overhead
	}
	return (input + output) / 1e6, overhead / 1e6
}

func apiModeNote(inputs templates.HostingInputs, baseline templates.APIBaseline) string {
	switch inputs.APIMode {
	case "batch":
		return "Batch: 50% off input and output. Asynchronous jobs, up to 24 hours; unsuitable for live chat. No cache discount combined here."
	case "cached":
		if inputs.CachePrefixTokens < baseline.CacheMinimum || inputs.CachePrefixTokens > inputs.InputTokensRequest {
			return fmt.Sprintf("Standard rates applied: caching needs at least %s shared prefix tokens, within the request's input budget.", templates.FormatDecimal(baseline.CacheMinimum, 0))
		}
		if baseline.CacheStoragePerMillionHour > 0 {
			return fmt.Sprintf("Explicit Gemini cache: %s/M cached input + %s/M token-hours stored; five-minute storage charged for every group. Use GenerateContent, not the Interactions-only implicit cache.", templates.FormatUSD2(baseline.CacheReadPerMillion), templates.FormatUSD2(baseline.CacheStoragePerMillionHour))
		}
		return fmt.Sprintf("Cache: %s/M prefix tokens on the first call, %s/M on reuse. Calls must share an exact prefix within five minutes; Astra retains it for at least 30 minutes.", templates.FormatUSD2(baseline.CacheWritePerMillion), templates.FormatUSD2(baseline.CacheReadPerMillion))
	default:
		return "Standard uncached text rates. Immediate requests; no batch or cache discount assumed."
	}
}

func compareAPIs(inputs templates.HostingInputs, estimate templates.HostingEstimate, baselines []templates.APIBaseline) []templates.APIComparison {
	rows := make([]templates.APIComparison, 0, len(baselines))
	for _, baseline := range baselines {
		monthly, overhead := apiMonthlyCost(inputs, baseline, estimate.RequestsMonth)
		// Cache groups make the bill piecewise linear; find the first whole request that pays for the fleet.
		low, high := int64(0), int64(1)
		for total, _ := apiMonthlyCost(inputs, baseline, float64(high)); total < estimate.TotalMonthlyUSD; total, _ = apiMonthlyCost(inputs, baseline, float64(high)) {
			high *= 2
		}
		for low+1 < high {
			middle := low + (high-low)/2
			cost, _ := apiMonthlyCost(inputs, baseline, float64(middle))
			if cost >= estimate.TotalMonthlyUSD {
				high = middle
			} else {
				low = middle
			}
		}
		rows = append(rows, templates.APIComparison{
			Baseline: baseline, MonthlyUSD: monthly, CacheOverheadUSD: overhead,
			PerThousandRequestsUSD: monthly / estimate.RequestsMonth * 1000, BreakEvenRequests: float64(high),
			BreakEvenFits: float64(high)*inputs.OutputTokensRequest <= estimate.CapacityTokensMonth, ModeNote: apiModeNote(inputs, baseline),
		})
	}
	return rows
}

func hostingTasks(inputs templates.HostingInputs, estimate templates.HostingEstimate, baselines []templates.APIBaseline) []templates.TaskComparison {
	rows := make([]templates.TaskComparison, 4)
	for i, quality := range inputs.Quality {
		requests := inputs.TasksPerMonth * quality.CallsPerTask
		row := templates.TaskComparison{
			ID: fmt.Sprintf("quality-%d", i), Name: "Your GKE fleet", Quality: quality, Requests: requests,
			Accepted: inputs.TasksPerMonth * quality.AcceptancePercent / 100, ModelUSD: estimate.TotalMonthlyUSD,
			ReviewUSD: inputs.TasksPerMonth * quality.ReviewMinutes / 60 * inputs.ReviewHourlyUSD,
			Fits:      requests*inputs.OutputTokensRequest <= estimate.CapacityTokensMonth,
		}
		if i > 0 {
			row.Name = baselines[i-1].Name
			row.ModelUSD, _ = apiMonthlyCost(inputs, baselines[i-1], requests)
			row.Fits = true
		}
		if row.Accepted > 0 {
			row.PerAcceptedUSD = (row.ModelUSD + row.ReviewUSD) / row.Accepted
		}
		rows[i] = row
	}
	return rows
}
