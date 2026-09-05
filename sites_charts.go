package site

import (
	"fmt"
	"math"
	"slices"
	"strings"

	"github.com/fmind/www/templates"
)

func plotCoordinate(value float64) string { return fmt.Sprintf("%.2f", value) }

func hostingCostPlot(inputs templates.HostingInputs, estimate templates.HostingEstimate, apis []templates.APIComparison) templates.CostPlot {
	capacity := estimate.CapacityTokensMonth / inputs.OutputTokensRequest
	maxBreakEven := 0.0
	for _, api := range apis {
		maxBreakEven = max(maxBreakEven, api.BreakEvenRequests)
	}
	maxDaily := min(1e7, max(inputs.RequestsPerDay*4, maxBreakEven/inputs.ActiveDays*1.2, capacity/inputs.ActiveDays*1.2))
	// Log axes preserve both a small team's demand and million-request break-even points.
	maxDaily = max(10, maxDaily)
	x := func(requests float64) string {
		return plotCoordinate(130 + math.Log10(max(1, requests/inputs.ActiveDays))/math.Log10(maxDaily)*590)
	}
	maxCost := estimate.TotalMonthlyUSD
	for _, api := range apis {
		total, _ := apiMonthlyCost(inputs, api.Baseline, maxDaily*inputs.ActiveDays)
		maxCost = max(maxCost, total)
	}
	y := func(cost float64) string { return plotCoordinate(300 - math.Log10(1+cost)/math.Log10(1+maxCost)*260) }
	plot := templates.CostPlot{CapacityLabel: templates.FormatDecimal(capacity, 0) + " requests/month", FleetY: y(estimate.TotalMonthlyUSD)}
	if capacity >= inputs.ActiveDays && capacity <= maxDaily*inputs.ActiveDays {
		plot.CapacityX = x(capacity)
		plot.CapacityWidth = plotCoordinate(590 - math.Log10(max(1, capacity/inputs.ActiveDays))/math.Log10(maxDaily)*590)
	}
	days := []float64{inputs.RequestsPerDay}
	for i := 0; i <= 60; i++ {
		days = append(days, math.Pow(maxDaily, float64(i)/60))
	}
	for _, api := range apis {
		if api.BreakEvenRequests >= inputs.ActiveDays && api.BreakEvenRequests <= maxDaily*inputs.ActiveDays {
			days = append(days, api.BreakEvenRequests/inputs.ActiveDays)
			plot.BreakEvens = append(plot.BreakEvens, templates.PlotTick{Position: x(api.BreakEvenRequests), Label: api.Baseline.Name + ": " + templates.FormatDecimal(api.BreakEvenRequests, 0) + " requests/month"})
		}
	}
	slices.Sort(days)
	days = slices.Compact(days)
	paths := make([][]string, 4)
	for index, daily := range days {
		scenario := inputs
		scenario.RequestsPerDay = daily
		requests := daily * inputs.ActiveDays
		label := templates.FormatDecimal(requests, 0) + " requests/month"
		fit := "within modeled capacity"
		if requests > capacity {
			fit = "beyond this fleet's capacity"
		}
		var summary strings.Builder
		summary.WriteString(label + " · " + fit + ". GKE fleet " + templates.FormatUSD2(estimate.TotalMonthlyUSD))
		paths[0] = append(paths[0], x(requests)+","+y(estimate.TotalMonthlyUSD))
		for j, api := range apis {
			total, _ := apiMonthlyCost(inputs, api.Baseline, requests)
			summary.WriteString(" · " + api.Baseline.Name + " " + templates.FormatUSD2(total))
			paths[j+1] = append(paths[j+1], x(requests)+","+y(total))
		}
		plot.Frames = append(plot.Frames, templates.CostFrame{X: x(requests), Label: label, Summary: summary.String() + " per month.", URL: hostingURL(scenario), Requests: requests})
		if daily == inputs.RequestsPerDay {
			plot.Selected = index
		}
	}
	names := []string{"GKE fleet", apis[0].Baseline.Name, apis[1].Baseline.Name, apis[2].Baseline.Name}
	for i, name := range names {
		plot.Lines = append(plot.Lines, templates.PlotLine{Name: name, Points: strings.Join(paths[i], " ")})
	}
	for i := 0; i <= 4; i++ {
		requests := math.Pow(maxDaily, float64(i)/4) * inputs.ActiveDays
		plot.XTicks = append(plot.XTicks, templates.PlotTick{Position: x(requests), Label: templates.FormatNumber(requests)})
		cost := math.Pow(1+maxCost, float64(i)/4) - 1
		plot.YTicks = append(plot.YTicks, templates.PlotTick{Position: y(cost), Label: chartUSD(cost)})
	}
	return plot
}

func hostingSensitivity(inputs templates.HostingInputs, baselines []templates.APIBaseline) []templates.SensitivityRow {
	rows := make([]templates.SensitivityRow, 0, 3)
	labels := []string{"Lower demand · ½×", "Your demand · 1×", "Higher demand · 2×"}
	for i, demand := range []float64{.5, 1, 2} {
		row := templates.SensitivityRow{Label: labels[i]}
		for _, speed := range []float64{.5, 1, 2} {
			scenario := inputs
			scenario.RequestsPerDay = min(1e7, max(1, inputs.RequestsPerDay*demand))
			scenario.TokensPerSecond = min(1e6, max(.1, inputs.TokensPerSecond*speed))
			estimate := estimateHosting(findModel(inputs.ModelID), findNodePool(inputs.NodePoolID), findQuantization(inputs.QuantizationID), scenario)
			cheapest := math.Inf(1)
			for _, baseline := range baselines {
				cost, _ := apiMonthlyCost(scenario, baseline, estimate.RequestsMonth)
				cheapest = min(cheapest, cost)
			}
			verdict := "API costs less"
			if estimate.TotalMonthlyUSD <= cheapest {
				verdict = "Fleet has a cost case"
			}
			if !estimate.DemandFits {
				verdict = "Fleet too small"
			}
			row.Cells = append(row.Cells, templates.SensitivityCell{URL: hostingURL(scenario), Inputs: scenario, CapacityPct: estimate.DemandCapacityPct, CheapestAPIUSD: cheapest, Verdict: verdict, Fits: estimate.DemandFits})
		}
		rows = append(rows, row)
	}
	return rows
}

func chartUSD(value float64) string {
	for _, unit := range []struct {
		suffix string
		scale  float64
	}{{"T", 1e12}, {"B", 1e9}, {"M", 1e6}, {"k", 1e3}} {
		if value >= unit.scale {
			if value/unit.scale < 10 {
				return fmt.Sprintf("$%.1f%s", value/unit.scale, unit.suffix)
			}
			return fmt.Sprintf("$%.0f%s", value/unit.scale, unit.suffix)
		}
	}
	return templates.FormatUSD(value)
}
