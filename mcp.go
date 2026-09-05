package site

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"runtime/debug"

	"github.com/modelcontextprotocol/go-sdk/mcp"

	"github.com/fmind/www/templates"
)

// mcpProfileURI is the stable URI of the full-portfolio MCP resource.
const mcpProfileURI = "portfolio://profile.json"

const mcpCacheTTL = 60 * 60 * 1000

const mcpProtocolVersion = "2026-07-28"

// Result bounds for search_articles: enough for an agent to reason over, capped
// so one call can never return the whole archive as tool output.
const (
	defaultSearchResults = 10
	maximumSearchResults = 50
)

// noArgs is the input type for tools that take no parameters. The MCP SDK infers
// an empty-object JSON schema from it, which the spec requires for every tool.
type noArgs struct{}

// Portfolio is the complete, machine-readable snapshot of the site's content. It
// backs both the MCP `portfolio://profile.json` resource and the get_profile tool.
type Portfolio struct {
	Metadata        templates.Metadata             `json:"metadata"`
	Biography       []string                       `json:"biography"`
	Leadership      []templates.LeadershipRole     `json:"leadership"`
	Expertise       []templates.ExpertiseCard      `json:"expertise"`
	Experience      []templates.WorkExperience     `json:"experience"`
	Certifications  []templates.CertificationBadge `json:"certifications"`
	Specializations []templates.CertificationEntry `json:"specializations"`
	Thesis          templates.Thesis               `json:"thesis"`
	Papers          []templates.ResearchPaper      `json:"papers"`
	// Tags is the closed vocabulary every article is tagged from, so a consumer
	// can filter the article list without inferring the taxonomy from the data.
	Tags          []templates.Tag            `json:"tags"`
	Articles      []templates.ArticleSummary `json:"articles"`
	SitePages     []templates.SitePage       `json:"site_pages"`
	OpenSource    []templates.Project        `json:"open_source"`
	YouTubeSeries []templates.Playlist       `json:"youtube_series"`
	Services      []templates.Service        `json:"services"`
}

// snapshot assembles the current portfolio from the templates data package.
func snapshot(articles []templates.ArticleSummary) Portfolio {
	return Portfolio{
		Metadata:        templates.METADATA,
		Biography:       templates.BIOGRAPHY,
		Leadership:      templates.LEADERSHIP,
		Expertise:       templates.EXPERTISE,
		Experience:      templates.EXPERIENCES,
		Certifications:  templates.BADGES,
		Specializations: templates.SPECIALIZATIONS,
		Thesis:          templates.THESIS,
		Papers:          templates.PAPERS,
		Tags:            templates.TAGS,
		Articles:        articles,
		SitePages:       templates.SITE_PAGES,
		OpenSource:      templates.OPEN_SOURCE,
		YouTubeSeries:   templates.YOUTUBE_SERIES,
		Services:        templates.GetServices(),
	}
}

// profileResult is the get_profile tool's structured output: the "who am I" core.
type profileResult struct {
	Metadata   templates.Metadata         `json:"metadata"`
	Biography  []string                   `json:"biography"`
	Leadership []templates.LeadershipRole `json:"leadership"`
	Expertise  []templates.ExpertiseCard  `json:"expertise"`
}

type experienceResult struct {
	Experience []templates.WorkExperience `json:"experience"`
}

type certificationsResult struct {
	Certifications  []templates.CertificationBadge `json:"certifications"`
	Specializations []templates.CertificationEntry `json:"specializations"`
}

type publicationsResult struct {
	Thesis   templates.Thesis           `json:"thesis"`
	Papers   []templates.ResearchPaper  `json:"papers"`
	Articles []templates.ArticleSummary `json:"articles"`
}

type projectsResult struct {
	OpenSource    []templates.Project  `json:"open_source"`
	YouTubeSeries []templates.Playlist `json:"youtube_series"`
}

type servicesResult struct {
	Services []templates.Service `json:"services"`
}

// searchArticlesArgs is the only tool input on this server. Limit is optional:
// agents that omit it get a useful default instead of an error.
type searchArticlesArgs struct {
	Query string `json:"query" jsonschema:"words to search for across article titles, tags, descriptions, and full text"`
	Limit int    `json:"limit,omitempty" jsonschema:"maximum number of results to return (default 10, maximum 50)"`
}

type searchArticlesResult struct {
	Query    string                     `json:"query"`
	Articles []templates.ArticleSummary `json:"articles"`
	Total    int                        `json:"total"`
}

// readOnly marks every tool as non-mutating and closed-world: handlers only read
// the portfolio compiled into this binary and never call an external system.
// Go 1.26's new(expr) keeps the optional false hint concise and unambiguous.
var readOnly = &mcp.ToolAnnotations{ReadOnlyHint: true, OpenWorldHint: new(false)}

var portfolioIcons = []mcp.Icon{{
	Source:   "https://www.fmind.dev/static/img/favicons/icon-192.png",
	MIMEType: "image/png",
	Sizes:    []string{"192x192"},
}}

type mcpCardPrimitive struct {
	Name        string `json:"name"`
	Title       string `json:"title,omitempty"`
	Description string `json:"description,omitempty"`
}

var mcpCardTools = []mcpCardPrimitive{
	{Name: "get_profile", Title: "Get profile", Description: "Return Fmind's identity, biography, leadership, and expertise."},
	{Name: "list_experience", Title: "List work experience", Description: "List professional roles, companies, and skills."},
	{Name: "list_certifications", Title: "List credentials", Description: "List certifications, badges, and specializations."},
	{Name: "list_publications", Title: "List publications", Description: "List the thesis, papers, and hosted articles."},
	{Name: "search_articles", Title: "Search articles", Description: "Rank Fmind's articles by relevance to a query."},
	{Name: "list_projects", Title: "List projects", Description: "List open-source projects and educational series."},
	{Name: "get_services", Title: "Get professional services", Description: "List advisory and mentoring services."},
}

var mcpCardPrompts = []mcpCardPrimitive{
	{Name: "assess_fit", Title: "Assess a role or project fit", Description: "Evaluate a brief against Fmind's portfolio."},
	{Name: "brief_me", Title: "Brief me about Fmind", Description: "Create an audience-specific portfolio briefing."},
}

// newMCPServer builds the read-only MCP server exposing the portfolio as agent
// tools plus a single JSON resource. All handlers are pure reads of static data.
func newMCPServer(articles []templates.ArticleSummary, index *searchIndex) *mcp.Server {
	server := mcp.NewServer(
		&mcp.Implementation{
			Name:       "www",
			Version:    buildVersion(),
			Title:      "Médéric Hurier (Fmind) — AI Architect Portfolio",
			WebsiteURL: templates.METADATA.SiteURL + "/",
			Icons:      portfolioIcons,
		},
		&mcp.ServerOptions{
			Instructions: fmt.Sprintf(
				"Query the portfolio of %s (%s): %s. Explore profile, leadership, work experience, credentials, publications, projects, and services.",
				templates.METADATA.Name,
				templates.METADATA.AlternateName,
				templates.METADATA.HeadlinePrimary,
			),
			Capabilities: &mcp.ServerCapabilities{},
		},
	)
	server.AddReceivingMiddleware(cacheMCPResults)

	mcp.AddTool(server, &mcp.Tool{
		Name:        "get_profile",
		Title:       "Get profile",
		Description: "Return the core profile: identity, headline, job title, contact, socials, biography, and areas of expertise.",
		Annotations: readOnly,
	}, func(context.Context, *mcp.CallToolRequest, noArgs) (*mcp.CallToolResult, profileResult, error) {
		return nil, profileResult{
			Metadata:   templates.METADATA,
			Biography:  templates.BIOGRAPHY,
			Leadership: templates.LEADERSHIP,
			Expertise:  templates.EXPERTISE,
		}, nil
	})

	server.AddPrompt(&mcp.Prompt{
		Name:        "assess_fit",
		Title:       "Assess a role or project fit",
		Description: "Evaluate a role or project brief against Fmind's profile, experience, expertise, and services.",
		Arguments: []*mcp.PromptArgument{{
			Name:        "brief",
			Title:       "Role or project brief",
			Description: "The responsibilities, outcomes, constraints, and required expertise to assess.",
			Required:    true,
		}},
	}, func(_ context.Context, req *mcp.GetPromptRequest) (*mcp.GetPromptResult, error) {
		return promptResult(
			"Assess this brief against Fmind's portfolio: "+req.Params.Arguments["brief"]+"\n\nUse get_profile, list_experience, list_certifications, and get_services. Distinguish direct evidence, transferable strengths, gaps, and concrete next steps.",
			"A structured, evidence-based fit assessment using the portfolio tools.",
		), nil
	})

	server.AddPrompt(&mcp.Prompt{
		Name:        "brief_me",
		Title:       "Brief me about Fmind",
		Description: "Create an audience-specific introduction to Fmind from the complete portfolio.",
		Arguments: []*mcp.PromptArgument{{
			Name:        "audience",
			Title:       "Audience",
			Description: "Who will read the briefing, such as an executive, engineering leader, or conference organizer.",
			Required:    true,
		}},
	}, func(_ context.Context, req *mcp.GetPromptRequest) (*mcp.GetPromptResult, error) {
		return promptResult(
			"Brief this audience about Fmind: "+req.Params.Arguments["audience"]+". Use the portfolio resource and relevant tools. Lead with audience value, support claims with specific experience or publications, and keep the result concise.",
			"An audience-specific briefing grounded in the full portfolio.",
		), nil
	})

	mcp.AddTool(server, &mcp.Tool{
		Name:        "list_experience",
		Title:       "List work experience",
		Description: "List professional work experience: companies, roles, descriptions, and skill tags.",
		Annotations: readOnly,
	}, func(context.Context, *mcp.CallToolRequest, noArgs) (*mcp.CallToolResult, experienceResult, error) {
		return nil, experienceResult{Experience: templates.EXPERIENCES}, nil
	})

	mcp.AddTool(server, &mcp.Tool{
		Name:        "list_certifications",
		Title:       "List credentials",
		Description: "List professional certifications, badges, and course specializations with their issuers.",
		Annotations: readOnly,
	}, func(context.Context, *mcp.CallToolRequest, noArgs) (*mcp.CallToolResult, certificationsResult, error) {
		return nil, certificationsResult{Certifications: templates.BADGES, Specializations: templates.SPECIALIZATIONS}, nil
	})

	mcp.AddTool(server, &mcp.Tool{
		Name:        "list_publications",
		Title:       "List publications",
		Description: "List academic and written publications: the PhD thesis, peer-reviewed papers, and hosted articles.",
		Annotations: readOnly,
	}, func(context.Context, *mcp.CallToolRequest, noArgs) (*mcp.CallToolResult, publicationsResult, error) {
		return nil, publicationsResult{Thesis: templates.THESIS, Papers: templates.PAPERS, Articles: articles}, nil
	})

	mcp.AddTool(server, &mcp.Tool{
		Name:        "search_articles",
		Title:       "Search articles",
		Description: "Search the hosted articles by relevance (BM25 over titles, tags, descriptions, and full text) and return the best matches. Use it to answer what Fmind has written about a topic instead of listing every publication.",
		Annotations: readOnly,
	}, func(_ context.Context, _ *mcp.CallToolRequest, args searchArticlesArgs) (*mcp.CallToolResult, searchArticlesResult, error) {
		query := normalizeSearchQuery(args.Query)
		if query == "" {
			return nil, searchArticlesResult{}, errors.New("query must not be empty")
		}
		limit := args.Limit
		if limit <= 0 {
			limit = defaultSearchResults
		}
		limit = min(limit, maximumSearchResults)

		ranked := index.Search(query)
		matches := make([]templates.ArticleSummary, 0, min(limit, len(ranked)))
		for _, article := range ranked[:min(limit, len(ranked))] {
			matches = append(matches, article.Summary())
		}
		return nil, searchArticlesResult{Query: query, Total: len(ranked), Articles: matches}, nil
	})

	mcp.AddTool(server, &mcp.Tool{
		Name:        "list_projects",
		Title:       "List projects",
		Description: "List open-source projects and educational YouTube series.",
		Annotations: readOnly,
	}, func(context.Context, *mcp.CallToolRequest, noArgs) (*mcp.CallToolResult, projectsResult, error) {
		return nil, projectsResult{OpenSource: templates.OPEN_SOURCE, YouTubeSeries: templates.YOUTUBE_SERIES}, nil
	})

	mcp.AddTool(server, &mcp.Tool{
		Name:        "get_services",
		Title:       "Get professional services",
		Description: "List the professional services on offer (AI architecture advisory and mentoring) with availability and how to book.",
		Annotations: readOnly,
	}, func(context.Context, *mcp.CallToolRequest, noArgs) (*mcp.CallToolResult, servicesResult, error) {
		return nil, servicesResult{Services: templates.GetServices()}, nil
	})

	server.AddResource(&mcp.Resource{
		URI:         mcpProfileURI,
		Name:        "profile",
		Title:       "Full portfolio",
		Description: "The complete portfolio (profile, leadership, experience, credentials, publications, projects, services) as a single JSON document.",
		MIMEType:    "application/json",
	}, func(_ context.Context, req *mcp.ReadResourceRequest) (*mcp.ReadResourceResult, error) {
		data, err := json.Marshal(snapshot(articles))
		if err != nil {
			return nil, fmt.Errorf("marshaling portfolio: %w", err)
		}
		return &mcp.ReadResourceResult{
			Contents: []*mcp.ResourceContents{{URI: req.Params.URI, MIMEType: "application/json", Text: string(data)}},
		}, nil
	})

	return server
}

func promptResult(text, description string) *mcp.GetPromptResult {
	return &mcp.GetPromptResult{
		Description: description,
		Messages: []*mcp.PromptMessage{{
			Role:    "user",
			Content: &mcp.TextContent{Text: text},
		}},
	}
}

// cacheMCPResults opts immutable discovery and portfolio reads into SEP-2549
// client caching. The cache is public because every response is deploy-static.
func cacheMCPResults(next mcp.MethodHandler) mcp.MethodHandler {
	return func(ctx context.Context, method string, req mcp.Request) (mcp.Result, error) {
		result, err := next(ctx, method, req)
		if err != nil {
			return nil, err
		}
		cacheable := mcp.Cacheable{TTLMs: mcpCacheTTL, CacheScope: "public"}
		switch value := result.(type) {
		case *mcp.DiscoverResult:
			value.Cacheable = cacheable
		case *mcp.ListToolsResult:
			value.Cacheable = cacheable
		case *mcp.ListPromptsResult:
			value.Cacheable = cacheable
		case *mcp.ListResourcesResult:
			value.Cacheable = cacheable
		case *mcp.ListResourceTemplatesResult:
			value.Cacheable = cacheable
		case *mcp.ReadResourceResult:
			value.Cacheable = cacheable
		}
		return result, nil
	}
}

func buildVersion() string {
	info, ok := debug.ReadBuildInfo()
	if !ok || info.Main.Version == "" {
		return "(devel)"
	}
	return info.Main.Version
}

func renderMCPServerCard() ([]byte, error) {
	card := struct {
		Schema          string                     `json:"$schema"`
		Version         string                     `json:"version"`
		ProtocolVersion string                     `json:"protocolVersion"`
		ServerInfo      mcp.Implementation         `json:"serverInfo"`
		Description     string                     `json:"description"`
		IconURL         string                     `json:"iconUrl"`
		Documentation   string                     `json:"documentationUrl"`
		Transport       map[string]string          `json:"transport"`
		Capabilities    map[string]map[string]bool `json:"capabilities"`
		Instructions    string                     `json:"instructions"`
		Resources       []mcpCardPrimitive         `json:"resources"`
		Tools           []mcpCardPrimitive         `json:"tools"`
		Prompts         []mcpCardPrimitive         `json:"prompts"`
	}{
		Schema:          "https://static.modelcontextprotocol.io/schemas/mcp-server-card/v1.json",
		Version:         "1.0",
		ProtocolVersion: mcpProtocolVersion,
		ServerInfo: mcp.Implementation{
			Name:       "www",
			Title:      "Médéric Hurier (Fmind) — AI Architect Portfolio",
			Version:    buildVersion(),
			WebsiteURL: templates.METADATA.SiteURL + "/",
		},
		Description:   "Read-only portfolio tools, resources, and prompts for Fmind.",
		IconURL:       portfolioIcons[0].Source,
		Documentation: templates.METADATA.SiteURL + "/llms.txt",
		Transport: map[string]string{
			"type":     "streamable-http",
			"endpoint": templates.METADATA.SiteURL + "/mcp",
		},
		Capabilities: map[string]map[string]bool{
			"tools":     {},
			"resources": {},
			"prompts":   {},
		},
		Instructions: "Use the tools for focused queries, the portfolio resource for a complete snapshot, and prompts for guided assessments.",
		Resources: []mcpCardPrimitive{{
			Name:        "profile",
			Title:       "Full portfolio",
			Description: "The complete portfolio as JSON at portfolio://profile.json.",
		}},
		Tools:   mcpCardTools,
		Prompts: mcpCardPrompts,
	}
	data, err := json.MarshalIndent(card, "", "  ")
	if err != nil {
		return nil, fmt.Errorf("marshal MCP server card: %w", err)
	}
	return append(data, '\n'), nil
}

// newMCPHandler exposes the MCP server over the stateless Streamable HTTP
// transport as a plain http.Handler, mounted by the router at /mcp. JSONResponse
// keeps responses as application/json (no SSE), which is simplest behind the
// Gateway proxy for a read-only, horizontally-scaled service.
func newMCPHandler(articles []templates.ArticleSummary, index *searchIndex) http.Handler {
	server := newMCPServer(articles, index)
	handler := mcp.NewStreamableHTTPHandler(
		func(*http.Request) *mcp.Server { return server },
		&mcp.StreamableHTTPOptions{Stateless: true, JSONResponse: true},
	)
	return http.NewCrossOriginProtection().Handler(handler)
}
