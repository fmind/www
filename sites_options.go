package site

import (
	"fmt"
	"net/url"
	"strconv"

	"github.com/fmind/www/templates"
)

// One field mapping serves validation and scenario URLs, including controls outside the main form.
type hostingOption struct {
	value            *float64
	key              string
	minimum, maximum float64
}

func hostingFloatOptions(inputs *templates.HostingInputs) []hostingOption {
	fields := make([]hostingOption, 0, 7+3*len(inputs.Quality))
	fields = append(fields, []hostingOption{
		{&inputs.CachePrefixTokens, "cache-prefix", 0, 1000000},
		{&inputs.TargetFirstToken, "target-first", .1, 3600},
		{&inputs.TargetCompletion, "target-complete", .1, 86400},
		{&inputs.MeasuredFirstToken, "measured-first", 0, 3600},
		{&inputs.MeasuredCompletion, "measured-complete", 0, 86400},
		{&inputs.TasksPerMonth, "tasks", 1, 10000000},
		{&inputs.ReviewHourlyUSD, "review-rate", 0, 10000},
	}...)
	for i := range inputs.Quality {
		prefix := fmt.Sprintf("quality-%d-", i)
		fields = append(fields, hostingOption{&inputs.Quality[i].AcceptancePercent, prefix + "acceptance", 0, 100},
			hostingOption{&inputs.Quality[i].CallsPerTask, prefix + "calls", 1, 100}, hostingOption{&inputs.Quality[i].ReviewMinutes, prefix + "review", 0, 480})
	}
	return fields
}

func parseHostingOptions(query url.Values, inputs *templates.HostingInputs, validation *[]string) {
	inputs.APIMode = parseChoice(query, "api-mode", inputs.APIMode, map[string]bool{"standard": true, "batch": true, "cached": true}, validation)
	inputs.CacheRequests = parseBoundedInt(query, "cache-requests", inputs.CacheRequests, 1, 1000000, validation)
	inputs.Concurrency = parseBoundedInt(query, "concurrency", inputs.Concurrency, 1, 100000, validation)
	inputs.MeasuredConcurrency = parseBoundedInt(query, "measured-concurrency", inputs.MeasuredConcurrency, 0, 100000, validation)
	inputs.QualityEnabled = parseChoice(query, "quality", "off", map[string]bool{"on": true, "off": true}, validation) == "on"
	for _, field := range hostingFloatOptions(inputs) {
		*field.value = parseBoundedFloat(query, field.key, *field.value, field.minimum, field.maximum, validation)
	}
	if inputs.MeasuredFirstToken > 0 && inputs.MeasuredCompletion > 0 && inputs.MeasuredFirstToken > inputs.MeasuredCompletion {
		*validation = append(*validation, "Recorded first-token time cannot exceed completion time; both measurements were cleared")
		inputs.MeasuredFirstToken, inputs.MeasuredCompletion = 0, 0
	}
}

func hostingURL(inputs templates.HostingInputs) string {
	query := url.Values{
		"model": {inputs.ModelID}, "node": {inputs.NodePoolID}, "quant": {inputs.QuantizationID}, "api-mode": {inputs.APIMode},
		"replicas": {strconv.Itoa(inputs.Replicas)}, "cache-requests": {strconv.Itoa(inputs.CacheRequests)},
		"concurrency": {strconv.Itoa(inputs.Concurrency)}, "measured-concurrency": {strconv.Itoa(inputs.MeasuredConcurrency)},
	}
	if inputs.QualityEnabled {
		query.Set("quality", "on")
	}
	fields := []hostingOption{
		{&inputs.DutyCyclePercent, "duty", 0, 0},
		{&inputs.MemoryOverheadPct, "overhead", 0, 0},
		{&inputs.TokensPerSecond, "throughput", 0, 0},
		{&inputs.TargetUtilization, "utilization", 0, 0},
		{&inputs.OutputTokensRequest, "tokens", 0, 0},
		{&inputs.InputTokensRequest, "input-tokens", 0, 0},
		{&inputs.RequestsPerDay, "requests", 0, 0},
		{&inputs.ActiveDays, "days", 0, 0},
		{&inputs.PlatformMonthlyUSD, "platform", 0, 0},
	}
	for _, field := range append(fields, hostingFloatOptions(&inputs)...) {
		query.Set(field.key, strconv.FormatFloat(*field.value, 'f', -1, 64))
	}
	return "/sites/llm-self-hosting/?" + query.Encode()
}

func hostingLatency(inputs templates.HostingInputs) (title, detail string) {
	if inputs.MeasuredConcurrency < inputs.Concurrency || inputs.MeasuredFirstToken == 0 || inputs.MeasuredCompletion == 0 {
		return "Responsiveness is still unproved", "Record p95 first-token and completion times at your target concurrency using this configuration."
	}
	if inputs.MeasuredFirstToken > inputs.TargetFirstToken || inputs.MeasuredCompletion > inputs.TargetCompletion {
		return "The recorded pilot misses a latency target", "Revisit batching, replicas, or model size, then measure again."
	}
	return "The recorded pilot meets your latency targets", "Both p95 measurements meet your targets at the recorded concurrency; production performance remains unproved."
}
