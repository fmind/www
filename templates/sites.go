package templates

import (
	"encoding/json"
	"fmt"
	"math"
	"strconv"
	"strings"
)

// SitePage is one focused decision surface published under /sites/.
type SitePage struct {
	Slug         string   `json:"slug"`
	Title        string   `json:"title"`
	Description  string   `json:"description"`
	Audience     string   `json:"audience"`
	URL          string   `json:"url"`
	ArticleSlugs []string `json:"-"`
}

// SITE_PAGES is the public registry shared by routing, navigation, sitemap,
// llms.txt, JSON, and MCP discovery.
var SITE_PAGES = []SitePage{
	{
		Slug:         "llm-self-hosting",
		ArticleSlugs: []string{"the-affordable-ai-agents", "cag-vs-rag-choosing-the-right-strategy-for-your-ai-application"},
		Title:        "LLM self-hosting on GKE",
		Description:  "Compare the leading open-weight models, GPU memory fit, GKE fleet cost, serving capacity, and managed-API break-even.",
		Audience:     "AI and technology leaders evaluating sovereign or controlled model serving",
		URL:          METADATA.SiteURL + "/sites/llm-self-hosting/",
	},
}

type FrontierModel struct {
	ID               string
	Name             string
	Creator          string
	License          string
	LicenseClass     string
	AnalysisURL      string
	WeightsURL       string
	Intelligence     float64
	ParametersB      float64
	ActiveParameters float64
	Rank             int
	ContextTokens    int
}

type GKENodePool struct {
	ID          string
	Name        string
	GPU         string
	PriceModel  string
	Operational string
	HBMGB       float64
	HourlyUSD   float64
	GPUCount    int
	Committed   bool
}

type Quantization struct {
	ID            string
	Name          string
	Guidance      string
	BytesPerParam float64
}

type DemandPreset struct {
	ID, Name, Description                                 string
	RequestsPerDay, ActiveDays, InputTokens, OutputTokens float64
}

type APIBaseline struct {
	Name, SourceURL, Note, CacheURL                                       string
	VerifiedOn, ReviewOn, ValidThrough                                    string
	CacheReadPerMillion, CacheWritePerMillion, CacheStoragePerMillionHour float64
	CacheMinimum                                                          float64
	InputPerMillion, OutputPerMillion                                     float64
}

type APIComparison struct {
	ModeNote, Freshness                                   string
	Baseline                                              APIBaseline
	CacheOverheadUSD                                      float64
	MonthlyUSD, PerThousandRequestsUSD, BreakEvenRequests float64
	BreakEvenFits, NeedsReview                            bool
}

type PrecisionComparison struct {
	Quantization Quantization
	Estimate     HostingEstimate
}

type HostingInputs struct {
	ModelID                                                                    string
	NodePoolID                                                                 string
	QuantizationID                                                             string
	APIMode                                                                    string
	Replicas                                                                   int
	DutyCyclePercent                                                           float64
	MemoryOverheadPct                                                          float64
	TokensPerSecond                                                            float64
	TargetUtilization                                                          float64
	OutputTokensRequest                                                        float64
	RequestsPerDay                                                             float64
	ActiveDays                                                                 float64
	InputTokensRequest                                                         float64
	PlatformMonthlyUSD                                                         float64
	CachePrefixTokens                                                          float64
	CacheRequests                                                              int
	Concurrency, MeasuredConcurrency                                           int
	TargetFirstToken, TargetCompletion, MeasuredFirstToken, MeasuredCompletion float64
	TasksPerMonth, ReviewHourlyUSD                                             float64
	Quality                                                                    [4]TaskQuality
	QualityEnabled                                                             bool
}

type TaskQuality struct {
	AcceptancePercent, CallsPerTask, ReviewMinutes float64
}

type TaskComparison struct {
	ID, Name                                                string
	Quality                                                 TaskQuality
	Requests, Accepted, ModelUSD, ReviewUSD, PerAcceptedUSD float64
	Fits                                                    bool
}

type CostFrame struct {
	X, Label, Summary, URL string
	Requests               float64
}

type (
	PlotLine struct{ Name, Points string }
	PlotTick struct{ Position, Label string }
	CostPlot struct {
		CapacityX, CapacityWidth, CapacityLabel, FleetY string
		Lines                                           []PlotLine
		Frames                                          []CostFrame
		XTicks, YTicks                                  []PlotTick
		BreakEvens                                      []PlotTick
		Selected                                        int
	}
)

type SensitivityCell struct {
	URL, Verdict                string
	Inputs                      HostingInputs
	CapacityPct, CheapestAPIUSD float64
	Fits                        bool
}
type SensitivityRow struct {
	Label string
	Cells []SensitivityCell
}

type HostingEstimate struct {
	WeightMemoryGB         float64
	RequiredMemoryGB       float64
	NodesPerReplica        int
	TotalNodes             int
	TotalGPUs              int
	ComputeMonthlyUSD      float64
	ControlMonthlyUSD      float64
	PlatformMonthlyUSD     float64
	TotalMonthlyUSD        float64
	CapacityTokensMonth    float64
	CapacityRequestsDay    float64
	RequestsMonth          float64
	InputTokensMonth       float64
	OutputTokensMonth      float64
	DemandCapacityPct      float64
	PerThousandRequestsUSD float64
	DemandFits             bool
}

type ModelComparison struct {
	Decision string
	Model    FrontierModel
	Estimate HostingEstimate
}

type LLMSelfHostingView struct {
	SnapshotDate                string
	IndexVersion                string
	ModelSourceURL              string
	GKESourceURL                string
	PriceSourceURL              string
	DemandLabel                 string
	LatencyTitle, LatencyDetail string
	Models                      []FrontierModel
	NodePools                   []GKENodePool
	Quantizations               []Quantization
	Comparison                  []ModelComparison
	Presets                     []DemandPreset
	APIs                        []APIComparison
	Precisions                  []PrecisionComparison
	Validation                  []string
	Sensitivity                 []SensitivityRow
	Tasks                       []TaskComparison
	RelatedArticles             []Article
	CostPlot                    CostPlot
	SelectedQuant               Quantization
	SelectedNode                GKENodePool
	SelectedModel               FrontierModel
	Inputs                      HostingInputs
	Estimate                    HostingEstimate
}

func FormatUSD(value float64) string {
	return "$" + FormatDecimal(value, 0)
}

func FormatUSD2(value float64) string {
	return "$" + FormatDecimal(value, 2)
}

func FormatNumber(value float64) string {
	switch {
	case value >= 1e12:
		return fmt.Sprintf("%.2fT", value/1e12)
	case value >= 1e9:
		return fmt.Sprintf("%.2fB", value/1e9)
	case value >= 1e6:
		return fmt.Sprintf("%.2fM", value/1e6)
	case value >= 1e3:
		return fmt.Sprintf("%.1fk", value/1e3)
	default:
		return fmt.Sprintf("%.0f", value)
	}
}

func GetSiteStructuredData(page SitePage) (string, error) {
	encoded, err := json.Marshal(map[string]any{
		"@context":            "https://schema.org",
		"@type":               "WebApplication",
		"name":                page.Title,
		"description":         page.Description,
		"url":                 page.URL,
		"applicationCategory": "BusinessApplication",
		"operatingSystem":     "Web",
		"author": map[string]string{
			"@type": "Person",
			"name":  METADATA.Name,
			"url":   METADATA.SiteURL,
		},
	})
	if err != nil {
		return "", fmt.Errorf("marshal site-page structured data: %w", err)
	}
	return string(encoded), nil
}

// Group the integer part after rounding so dollar amounts stay readable at any scale.
func FormatDecimal(value float64, digits int) string {
	// Round at the displayed decimal place before formatting binary floating-point values.
	scale := math.Pow10(digits)
	parts := strings.Split(strconv.FormatFloat(math.Round(value*scale)/scale, 'f', digits, 64), ".")
	integer := parts[0]
	for i := len(integer) - 3; i > 0; i -= 3 {
		if integer[i-1] != '-' {
			integer = integer[:i] + "," + integer[i:]
		}
	}
	if len(parts) == 2 {
		return integer + "." + parts[1]
	}
	return integer
}

func FormatCount(value int, noun string) string {
	suffix := "s"
	if value == 1 {
		suffix = ""
	}
	return FormatDecimal(float64(value), 0) + " " + noun + suffix
}

func (page SitePage) RelatesTo(slug string) bool {
	for _, candidate := range page.ArticleSlugs {
		if candidate == slug {
			return true
		}
	}
	return false
}
