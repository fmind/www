// Package site wires the portfolio's HTTP server: routing, embedded static
// assets, content-hash cache busting, the read-only MCP endpoint, security
// middleware, and OpenTelemetry-correlated logging.
package site

import (
	"bytes"
	"crypto/sha256"
	"embed"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io/fs"
	"log/slog"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/a-h/templ"
	"github.com/klauspost/compress/gzhttp"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"

	"github.com/fmind/www/config"
	"github.com/fmind/www/templates"
)

// ServiceName labels the app in traces and the OTel resource.
const ServiceName = "www"

// markdownExtension is the suffix that asks for an article's raw Markdown source
// (`/articles/<slug>.md`) instead of its rendered page.
const markdownExtension = ".md"

//go:embed static
var staticFS embed.FS

// rootFiles maps top-level well-known URLs to their embedded source and content
// type, so crawlers and agents can fetch them from the domain root.
var rootFileSources = map[string]struct{ file, contentType string }{
	"/favicon.ico":      {"static/favicon.ico", "image/x-icon"},
	"/robots.txt":       {"static/robots.txt", "text/plain; charset=utf-8"},
	"/humans.txt":       {"static/humans.txt", "text/plain; charset=utf-8"},
	"/site.webmanifest": {"static/site.webmanifest", "application/manifest+json"},
}

type applicationAssets struct {
	rootFiles map[string]staticResponse
}

type staticResponse struct {
	contentType string
	body        []byte
}

// initAssets performs immutable embedded-asset setup once without discarding
// failures. A missing generated stylesheet or unreadable file aborts startup.
var initAssets = sync.OnceValues(func() (applicationAssets, error) {
	return loadApplicationAssets(staticFS)
})

// initArticles parses, validates, and highlights the embedded archive once. The
// result is immutable, so every handler built in this process shares it instead
// of repeating the most expensive work at startup.
var initArticles = sync.OnceValues(loadArticles)

// NewAppHandler builds the root application handler: the router wrapped in the
// security/logging middleware chain and an outer OpenTelemetry span.
func NewAppHandler(logger *slog.Logger, cfg config.Config) (http.Handler, error) {
	assets, err := initAssets()
	if err != nil {
		return nil, fmt.Errorf("initialize assets: %w", err)
	}
	collection, err := initArticles()
	if err != nil {
		return nil, fmt.Errorf("load articles: %w", err)
	}
	return newAppHandler(logger, cfg, collection, assets)
}

func newAppHandler(logger *slog.Logger, cfg config.Config, collection articleCollection, assets applicationAssets) (http.Handler, error) {
	publicArticles := visibleArticles(collection.all, false)
	pageArticles := visibleArticles(collection.all, cfg.Environment == config.Development)
	summaries := articleSummaries(publicArticles)
	related := relatedArticleIndex(pageArticles)
	articleMarkdown := articleMarkdownIndex(collection.all)
	// Two indexes rather than one shared: the rendered pages may include drafts in
	// development, while MCP is a public surface and must never rank one.
	pageSearch := newSearchIndex(pageArticles)
	publicSearch := newSearchIndex(publicArticles)
	structuredHome, err := templates.GetStructuredData(nil)
	if err != nil {
		return nil, fmt.Errorf("build home structured data: %w", err)
	}
	siteIndexPage := templates.SitePage{
		Title:       "Sites",
		Description: "Source-backed decision tools for AI architecture, infrastructure, and operating economics.",
		URL:         templates.METADATA.SiteURL + "/sites/",
	}
	structuredSiteIndex, err := templates.GetSiteStructuredData(siteIndexPage)
	if err != nil {
		return nil, fmt.Errorf("build site index structured data: %w", err)
	}
	structuredSitePages := make(map[string]string, len(templates.SITE_PAGES))
	for _, page := range templates.SITE_PAGES {
		structured, structuredErr := templates.GetSiteStructuredData(page)
		if structuredErr != nil {
			return nil, fmt.Errorf("build site-page structured data for %q: %w", page.Slug, structuredErr)
		}
		structuredSitePages[page.Slug] = structured
	}
	articleMetadataBySlug := make(map[string]templates.PageMetadata, len(collection.bySlug))
	for slug, article := range collection.bySlug {
		articleStructured, structuredErr := templates.GetStructuredData(&article)
		if structuredErr != nil {
			return nil, fmt.Errorf("build structured data for %q: %w", slug, structuredErr)
		}
		articleMetadataBySlug[slug] = articleMetadata(article, articleStructured)
	}
	profile, err := json.MarshalIndent(snapshot(summaries), "", "  ")
	if err != nil {
		return nil, fmt.Errorf("encode profile: %w", err)
	}
	profile = append(profile, '\n')
	feed, err := renderAtomFeed(publicArticles)
	if err != nil {
		return nil, fmt.Errorf("render Atom feed: %w", err)
	}
	sitemap, err := renderSitemap(publicArticles)
	if err != nil {
		return nil, fmt.Errorf("render sitemap: %w", err)
	}
	llms := renderLLMSTxt(publicArticles)
	llmsFull := renderLLMSFull(llms, publicArticles)
	serverCard, err := renderMCPServerCard()
	if err != nil {
		return nil, fmt.Errorf("render MCP server card: %w", err)
	}
	notFoundPage := templates.Layout(templates.NotFound(), notFoundMetadata(structuredHome))

	mux := http.NewServeMux()

	// Embedded static assets (long-cached when content-hashed via ?v=).
	mux.Handle("GET /static/", StaticCache(http.FileServer(http.FS(staticFS))))

	// Liveness/readiness probe.
	mux.HandleFunc("GET /health", health)
	mux.HandleFunc("GET /healthz", health)

	// Root well-known files.
	for path, response := range assets.rootFiles {
		mux.HandleFunc("GET "+path, serveStaticResponse(response, "public, max-age=86400, must-revalidate", false))
	}
	mux.HandleFunc("GET /llms.txt", serveStaticResponse(staticResponse{"text/plain; charset=utf-8", llms}, "public, max-age=3600, must-revalidate", false))
	mux.HandleFunc("GET /llms-full.txt", serveStaticResponse(staticResponse{"text/plain; charset=utf-8", llmsFull}, "public, max-age=3600, must-revalidate", false))
	mux.HandleFunc("GET /sitemap.xml", serveStaticResponse(staticResponse{"application/xml; charset=utf-8", sitemap}, "public, max-age=3600, must-revalidate", false))

	// security.txt (RFC 9116) is generated rather than a static file, so its
	// Expires date is always one year ahead and the policy never silently lapses.
	mux.HandleFunc("GET /security.txt", serveSecurityTxt)
	mux.HandleFunc("GET /.well-known/security.txt", serveSecurityTxt)

	// Machine-readable surfaces for AI agents: a single JSON document and a
	// read-only MCP server (Streamable HTTP) over the same portfolio data.
	mux.HandleFunc("GET /api/profile", serveStaticResponse(staticResponse{"application/json; charset=utf-8", profile}, "public, max-age=3600", true))
	cardResponse := staticResponse{"application/mcp-server-card+json; charset=utf-8", serverCard}
	mux.HandleFunc("GET /mcp/server-card", serveStaticResponse(cardResponse, "public, max-age=3600, must-revalidate", true))
	// Keep the SEP-1649 well-known probe for client compatibility while the
	// experimental extension standardizes on the MCP-relative discovery route.
	mux.HandleFunc("GET /.well-known/mcp/server-card.json", serveStaticResponse(cardResponse, "public, max-age=3600, must-revalidate", true))
	// 1 MiB is ample for any JSON-RPC call to this read-only server; larger
	// bodies fail fast instead of being buffered whole into memory.
	mcpHandler := MaxBody(1 << 20)(newMCPHandler(summaries, publicSearch))
	mux.Handle("/mcp", mcpHandler)
	mux.Handle("/mcp/", mcpHandler)

	// Articles are parsed once above; every human and machine surface reads the
	// same immutable, reverse-chronological collection.
	mux.HandleFunc("GET /articles/feed.xml", serveStaticResponse(staticResponse{"application/atom+xml; charset=utf-8", feed}, "public, max-age=3600, must-revalidate", false))
	mux.HandleFunc("GET /articles/{$}", func(w http.ResponseWriter, r *http.Request) {
		query := r.URL.Query()
		view := articleIndexData(pageArticles, pageSearch, query.Get("tag"), query.Get("q"))
		renderPage(logger, w, r, http.StatusOK, templates.Layout(
			templates.ArticleIndex(view),
			articleIndexMetadata(view, structuredHome),
		))
	})
	// One route serves both "/articles/{slug}" (canonicalized to the trailing
	// slash) and "/articles/{slug}.md": net/http patterns cannot express a suffix,
	// and splitting them would mean two overlapping wildcards on the same segment.
	mux.HandleFunc("GET /articles/{slug}", func(w http.ResponseWriter, r *http.Request) {
		slug := r.PathValue("slug")
		if source, found := strings.CutSuffix(slug, markdownExtension); found {
			article, ok := collection.bySlug[source]
			if !ok || article.Draft && cfg.Environment == config.Production {
				renderNotFound(logger, w, r, notFoundPage)
				return
			}
			serveStaticResponse(
				staticResponse{"text/markdown; charset=utf-8", articleMarkdown[source]},
				"public, max-age=3600, must-revalidate",
				true,
			)(w, r)
			return
		}
		target := "/articles/" + url.PathEscape(slug) + "/"
		if r.URL.RawQuery != "" {
			target += "?" + r.URL.RawQuery
		}
		http.Redirect(w, r, target, http.StatusMovedPermanently) //nolint:gosec // G710: fixed same-origin route with one escaped segment
	})
	mux.HandleFunc("GET /articles/{slug}/{$}", func(w http.ResponseWriter, r *http.Request) {
		article, ok := collection.bySlug[r.PathValue("slug")]
		if !ok || article.Draft && cfg.Environment == config.Production {
			renderNotFound(logger, w, r, notFoundPage)
			return
		}
		renderPage(logger, w, r, http.StatusOK, templates.Layout(
			templates.ArticlePage(article, related[article.Slug]),
			articleMetadataBySlug[article.Slug],
		))
	})

	// Site pages share one registry and route family. Each page keeps its domain
	// calculation in Go and its interface in Templ, so adding one cannot fork the
	// site's navigation, metadata, styling, or security model.
	mux.HandleFunc("GET /sites", func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, "/sites/", http.StatusMovedPermanently)
	})
	mux.HandleFunc("GET /sites/{$}", func(w http.ResponseWriter, r *http.Request) {
		renderPage(logger, w, r, http.StatusOK, templates.Layout(
			templates.SiteIndex(templates.SITE_PAGES),
			siteIndexMetadata(structuredSiteIndex),
		))
	})
	mux.HandleFunc("GET /sites/{slug}", func(w http.ResponseWriter, r *http.Request) {
		target := "/sites/" + url.PathEscape(r.PathValue("slug")) + "/"
		if r.URL.RawQuery != "" {
			target += "?" + r.URL.RawQuery
		}
		http.Redirect(w, r, target, http.StatusMovedPermanently) //nolint:gosec // G710: fixed same-origin route with one escaped segment
	})
	mux.HandleFunc("GET /sites/{slug}/{$}", func(w http.ResponseWriter, r *http.Request) {
		if r.PathValue("slug") != "llm-self-hosting" {
			renderNotFound(logger, w, r, notFoundPage)
			return
		}
		page := templates.SITE_PAGES[0]
		view := llmSelfHostingView(r.URL.Query())
		for _, article := range publicArticles {
			if page.RelatesTo(article.Slug) {
				view.RelatedArticles = append(view.RelatedArticles, article)
			}
		}
		renderPage(logger, w, r, http.StatusOK, templates.Layout(
			templates.LLMSelfHosting(view),
			sitePageMetadata(page, structuredSitePages[page.Slug]),
		))
	})

	// Home page.
	mux.HandleFunc("GET /{$}", func(w http.ResponseWriter, r *http.Request) {
		renderPage(logger, w, r, http.StatusOK, templates.Layout(templates.Home(pageArticles), homeMetadata(structuredHome)))
	})

	// Catch-all: render the 404 page for anything unmatched. It is served noindex
	// (and without the homepage canonical) so crawlers never index an error page.
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		renderNotFound(logger, w, r, notFoundPage)
	})

	// Compress text responses with zstd/gzip. SkipPrecompressed prevents binary
	// assets such as WebP, PNG, and WOFF2 from growing under a second compression
	// pass. SecurityHeaders is outermost so even the apex->www 301 redirect (which
	// short-circuits CanonicalHost) still carries HSTS.
	handler := Chain(
		gzhttp.GzipHandler(SkipPrecompressed(mux)),
		SecurityHeaders(cfg.Environment),
		CanonicalHost(cfg.Environment),
		RequestLogger(logger),
		AnalyticsLogger(logger),
	)
	// otelhttp is outermost so the server span is open before anything logs.
	return otelhttp.NewHandler(handler, "http.server"), nil
}

// health reports process liveness.
func health(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	if _, err := w.Write([]byte(`{"status":"ok"}`)); err != nil {
		slog.DebugContext(r.Context(), "write health response", "error", err)
	}
}

func renderPage(logger *slog.Logger, w http.ResponseWriter, r *http.Request, status int, page templ.Component) {
	var body bytes.Buffer
	if err := page.Render(r.Context(), &body); err != nil {
		logger.ErrorContext(r.Context(), "render page", "path", r.URL.Path, "error", err)
		http.Error(w, http.StatusText(http.StatusInternalServerError), http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Header().Set("Cache-Control", "no-cache")
	w.WriteHeader(status)
	if _, err := w.Write(body.Bytes()); err != nil {
		logger.DebugContext(r.Context(), "write page", "path", r.URL.Path, "error", err)
	}
}

func renderNotFound(logger *slog.Logger, w http.ResponseWriter, r *http.Request, page templ.Component) {
	renderPage(logger, w, r, http.StatusNotFound, page)
}

func homeMetadata(structured string) templates.PageMetadata {
	return templates.PageMetadata{
		Title:          templates.METADATA.Title,
		Description:    templates.METADATA.Description,
		Canonical:      templates.METADATA.SiteURL + "/",
		ImageURL:       templates.METADATA.SiteURL + "/static/img/og-image.jpg",
		ImageAlt:       templates.METADATA.Name + " — " + templates.METADATA.JobTitle,
		Kind:           "website",
		StructuredData: structured,
		IsHome:         true,
	}
}

// articleIndexMetadata builds the index head. The view carries the filtered
// result so the first card's cover — the page's LCP image — is preloaded per
// filter, and search result pages are kept out of the index: they are a view of
// existing articles, not content of their own.
func articleIndexMetadata(view templates.ArticleIndexView, structured string) templates.PageMetadata {
	preload := ""
	switch {
	case len(view.Results) > 0:
		preload = view.Results[0].CardImagePath()
	case len(view.Years) > 0 && len(view.Years[0].Articles) > 0:
		preload = view.Years[0].Articles[0].CardImagePath()
	}
	title := "Articles | Médéric Hurier (Fmind)"
	if view.Searching() {
		title = "Search: " + view.Query + " | Articles | Médéric Hurier (Fmind)"
	}
	return templates.PageMetadata{
		Title:          title,
		Description:    "Articles on AI agents, MLOps, cloud architecture, security, and pragmatic engineering systems.",
		Canonical:      templates.METADATA.SiteURL + "/articles/",
		ImageURL:       templates.METADATA.SiteURL + "/static/img/og-image.jpg",
		ImageAlt:       "Articles by " + templates.METADATA.Name,
		Kind:           "website",
		StructuredData: structured,
		PreloadImage:   preload,
		NoIndex:        view.Searching(),
	}
}

func articleMetadata(article templates.Article, structured string) templates.PageMetadata {
	return templates.PageMetadata{
		Title:              article.Title + " | Fmind",
		Description:        article.Description,
		Canonical:          article.CanonicalURL(),
		ImageURL:           article.ImageURL,
		ImageAlt:           article.ImageAlt,
		Kind:               "article",
		StructuredData:     structured,
		PreloadImage:       article.ImagePath(),
		PreloadImageSrcset: article.CoverSrcset,
		PreloadImageSizes:  article.CoverSizes,
		NoIndex:            article.Draft,
		Article:            &article,
	}
}

func siteIndexMetadata(structured string) templates.PageMetadata {
	return templates.PageMetadata{
		Title:          "Sites | " + templates.METADATA.SiteName,
		Description:    "Source-backed decision tools for AI architecture, infrastructure, and operating economics.",
		Canonical:      templates.METADATA.SiteURL + "/sites/",
		ImageURL:       templates.METADATA.SiteURL + "/static/img/og-image.jpg",
		ImageAlt:       "Fmind Sites",
		Kind:           "website",
		StructuredData: structured,
	}
}

func sitePageMetadata(page templates.SitePage, structured string) templates.PageMetadata {
	return templates.PageMetadata{
		InstantScroll:  true,
		Title:          page.Title + " | " + templates.METADATA.SiteName,
		Description:    page.Description,
		Canonical:      page.URL,
		ImageURL:       templates.METADATA.SiteURL + "/static/img/og-image.jpg",
		ImageAlt:       page.Title,
		Kind:           "website",
		StructuredData: structured,
	}
}

func notFoundMetadata(structured string) templates.PageMetadata {
	return templates.PageMetadata{
		Title:          "Page not found | Fmind",
		Description:    "The requested page could not be found.",
		Canonical:      templates.METADATA.SiteURL + "/",
		ImageURL:       templates.METADATA.SiteURL + "/static/img/og-image.jpg",
		ImageAlt:       templates.METADATA.Name + " — " + templates.METADATA.JobTitle,
		Kind:           "website",
		StructuredData: structured,
		NoIndex:        true,
	}
}

// serveSecurityTxt renders an RFC 9116 security.txt whose Expires date is
// recomputed one year ahead on every request, so the published policy never
// lapses regardless of deploy cadence. Contact and canonical URLs derive from
// the site metadata, keeping a single source of truth.
func serveSecurityTxt(w http.ResponseWriter, r *http.Request) {
	siteURL := templates.METADATA.SiteURL
	expires := time.Now().AddDate(1, 0, 0).UTC().Format(time.RFC3339)

	body := strings.Join([]string{
		"# Security contact information for " + strings.TrimPrefix(siteURL, "https://") + " (" + templates.METADATA.Name + ")",
		"# Spec: https://www.rfc-editor.org/rfc/rfc9116",
		"",
		"Contact: mailto:" + templates.METADATA.Email,
		"Expires: " + expires,
		"Preferred-Languages: en,fr",
		"Canonical: " + siteURL + "/.well-known/security.txt",
		"Canonical: " + siteURL + "/security.txt",
		"",
	}, "\n")

	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	w.Header().Set("Cache-Control", "public, max-age=86400, must-revalidate")
	if _, err := w.Write([]byte(body)); err != nil {
		slog.DebugContext(r.Context(), "write security.txt", "error", err)
	}
}

func serveStaticResponse(response staticResponse, cacheControl string, cors bool) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", response.contentType)
		w.Header().Set("Cache-Control", cacheControl)
		if cors {
			w.Header().Set("Access-Control-Allow-Origin", "*")
		}
		if _, err := w.Write(response.body); err != nil {
			slog.DebugContext(r.Context(), "write static response", "path", r.URL.Path, "error", err)
		}
	}
}

func loadApplicationAssets(assets fs.FS) (applicationAssets, error) {
	css, err := fs.ReadFile(assets, "static/dist/styles.css")
	if err != nil {
		return applicationAssets{}, fmt.Errorf("read generated stylesheet: %w", err)
	}
	hashes := make(map[string]string)
	if err := fs.WalkDir(assets, "static", func(p string, d fs.DirEntry, err error) error {
		if err != nil || d.IsDir() {
			return err
		}
		data, err := fs.ReadFile(assets, p)
		if err != nil {
			return fmt.Errorf("read %q for hashing: %w", p, err)
		}
		sum := sha256.Sum256(data)
		hashes["/"+p] = hex.EncodeToString(sum[:])[:8]
		return nil
	}); err != nil {
		return applicationAssets{}, fmt.Errorf("hash static assets: %w", err)
	}

	rootFiles := make(map[string]staticResponse, len(rootFileSources))
	for route, source := range rootFileSources {
		data, err := fs.ReadFile(assets, source.file)
		if err != nil {
			return applicationAssets{}, fmt.Errorf("read root file %q: %w", source.file, err)
		}
		rootFiles[route] = staticResponse{contentType: source.contentType, body: data}
	}

	// The code theme's classes are generated from the same Chroma style that
	// rendered the articles, so palette and markup can never drift apart.
	if highlighterErr != nil {
		return applicationAssets{}, fmt.Errorf("initialize code highlighter: %w", highlighterErr)
	}
	highlightCSS, highlightErr := highlighter.CSS()
	if highlightErr != nil {
		return applicationAssets{}, highlightErr
	}

	// Publish the fully validated immutable values together, so templates never
	// observe a partially initialized asset map.
	templates.AssetHashes = hashes
	templates.InlineStyles = string(css) + highlightCSS
	return applicationAssets{rootFiles: rootFiles}, nil
}
