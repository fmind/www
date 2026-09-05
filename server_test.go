package site_test

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"regexp"
	"slices"
	"strings"
	"testing"
	"time"

	sdktrace "go.opentelemetry.io/otel/sdk/trace"

	site "github.com/fmind/www"
	"github.com/fmind/www/config"
	"github.com/fmind/www/templates"
)

// newServer spins the real application handler in development mode.
func newServer(t *testing.T) *httptest.Server {
	return newServerForEnvironment(t, config.Development)
}

func newServerForEnvironment(t *testing.T, environment config.Environment) *httptest.Server {
	t.Helper()
	handler, err := site.NewAppHandler(slog.New(slog.DiscardHandler), config.Config{
		Environment: environment,
		Port:        8080,
	})
	if err != nil {
		t.Fatalf("build application handler: %v", err)
	}
	srv := httptest.NewServer(handler)
	t.Cleanup(srv.Close)
	return srv
}

// get performs a GET and returns the status, headers, and body — closing the
// response body internally so callers never leak it.
func get(t *testing.T, url string) (int, http.Header, string) {
	t.Helper()
	resp, err := http.Get(url)
	if err != nil {
		t.Fatalf("GET %s: %v", url, err)
	}
	defer closeBody(t, resp.Body)
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("read body: %v", err)
	}
	return resp.StatusCode, resp.Header, string(body)
}

func closeBody(t *testing.T, body io.Closer) {
	t.Helper()
	if err := body.Close(); err != nil {
		t.Errorf("close response body: %v", err)
	}
}

func TestHomePage(t *testing.T) {
	srv := newServer(t)

	status, hdr, body := get(t, srv.URL+"/")
	if status != http.StatusOK {
		t.Fatalf("status = %d, want 200", status)
	}
	if ct := hdr.Get("Content-Type"); !strings.HasPrefix(ct, "text/html") {
		t.Errorf("Content-Type = %q, want text/html", ct)
	}
	if got := hdr.Get("Cache-Control"); got != "no-cache" {
		t.Errorf("Cache-Control = %q, want no-cache", got)
	}
	for _, want := range []string{
		"Médéric Hurier",
		"AI Architect (PhD) • VC Expert Advisor • AAIF Ambassador • GCP Certified Cloud Architect • AI Agents, MLOps &amp; Security",
		"33N Ventures",
		"Leadership & Community",
		"Agentic Orchestration",
		"Work Experience",
		"ArcelorMittal",
		"Certifications",
		"Specializations & Foundations",
		"MCP 2026–07–28: Stateless core, enterprise authorization, and SDK betas",
		"The Affordable AI Agents",
		"Agent Levers: A Plan-Do-Check-Act Loop That Makes Coding Agents Finish What They Start",
		`rel="alternate" type="application/json"`,
		"</html>",
		"application/ld+json",
	} {
		if !strings.Contains(body, want) {
			t.Errorf("home page missing %q", want)
		}
	}
	if strings.Contains(body, "googletagmanager") {
		t.Error("home page should not load behavioral analytics")
	}
	assertVisibleSocials(t, body)
	assertFooter(t, body)
	assertArticlesSection(t, body)

	const schemaStart = `<script type="application/ld+json">`
	start := strings.Index(body, schemaStart)
	if start < 0 {
		t.Fatal("home page is missing JSON-LD structured data")
	}
	contentStart := start + len(schemaStart)
	end := strings.Index(body[contentStart:], "</script>")
	if end < 0 {
		t.Fatal("home page has unterminated JSON-LD structured data")
	}
	var schema struct {
		Graph []struct {
			Type string `json:"@type"`
		} `json:"@graph"`
	}
	schemaJSON := body[contentStart : contentStart+end]
	if err := json.Unmarshal([]byte(schemaJSON), &schema); err != nil {
		t.Fatalf("decode JSON-LD: %v", err)
	}
	if len(schema.Graph) != 3 {
		t.Errorf("JSON-LD graph nodes = %d, want 3", len(schema.Graph))
	}
	types := make(map[string]bool, len(schema.Graph))
	for _, node := range schema.Graph {
		types[node.Type] = true
	}
	for _, want := range []string{"ProfilePage", "Person", "WebSite"} {
		if !types[want] {
			t.Errorf("JSON-LD graph missing %s", want)
		}
	}
}

func assertVisibleSocials(t *testing.T, body string) {
	t.Helper()
	visible := []string{"LinkedIn", "X (Twitter)", "Medium", "GitHub", "YouTube"}
	for _, region := range []struct {
		name  string
		start string
		end   string
	}{
		{name: "header", start: "<header", end: "</header>"},
		{name: "footer", start: "<footer", end: "</footer>"},
	} {
		html := extractRegion(t, body, region.name, region.start, region.end)
		previous := -1
		for _, social := range visible {
			index := strings.Index(html, `aria-label="`+social+`"`)
			if index < 0 {
				t.Errorf("%s missing visible %s link", region.name, social)
				continue
			}
			if index <= previous {
				t.Errorf("%s social %s is out of order", region.name, social)
			}
			previous = index
		}
		if strings.Contains(html, `aria-label="Bluesky"`) {
			t.Errorf("%s should show the requested five social links only", region.name)
		}
	}
}

func assertFooter(t *testing.T, body string) {
	t.Helper()
	footer := extractRegion(t, body, "footer", "<footer", "</footer>")
	if got := strings.Count(footer, "<p "); got != 2 {
		t.Errorf("footer paragraph rows = %d, want 2", got)
	}
	// Keep the combined row, but allow it to wrap on a 320px screen.
	if got := strings.Count(footer, `class="flex flex-wrap`); got != 1 {
		t.Errorf("footer wrapping icon/link groups = %d, want 1", got)
	}

	previous := -1
	for _, content := range []string{
		"Everyday excellence builds tomorrow's success.",
		`aria-label="Social profiles"`,
		">For AI agents</a>",
		">JSON profile</a>",
		"All rights reserved.",
	} {
		index := strings.Index(footer, content)
		if index < 0 {
			t.Errorf("footer missing %q", content)
			continue
		}
		if index <= previous {
			t.Errorf("footer content %q is out of order", content)
		}
		previous = index
	}
}

// assertArticlesSection pins the home page's editorial balance: the articles
// section is articles only, no academic showcase, and the index is reachable as a
// destination rather than as a nav anchor.
func assertArticlesSection(t *testing.T, body string) {
	t.Helper()
	articlesSection := extractRegion(t, body, "articles section", `id="articles"`, "</section>")

	for _, want := range []string{
		fmt.Sprintf("Browse all %d articles", site.PublicArticleCount(t)),
		"min read",
	} {
		if !strings.Contains(articlesSection, want) {
			t.Errorf("articles section missing %q", want)
		}
	}
	if got := strings.Count(articlesSection, "<article "); got != 6 {
		t.Errorf("articles section article cards = %d, want 6", got)
	}
	// The doctorate and papers stay in the machine-readable surfaces (llms.txt,
	// /api/profile, MCP) but are no longer part of the page's narrative.
	for _, gone := range []string{
		"PhD Thesis",
		"Academic Research",
		"PhD in AI &amp; Computer Security",
		"orbilu.uni.lu",
		`id="publications"`,
		`href="/#publications"`,
	} {
		if strings.Contains(body, gone) {
			t.Errorf("home page still shows retired research content %q", gone)
		}
	}
	// Every nav entry must behave the same way: same-page anchors in the list,
	// with the full-page destinations (Articles, Sites) kept out as buttons.
	nav := extractRegion(t, body, "navigation", "<nav ", "</nav>")
	if !strings.Contains(nav, `href="/#`) {
		t.Error("navigation is missing its section anchors")
	}
	if got := strings.Count(nav, `href="/articles/"`); got != 2 {
		t.Errorf("navigation articles links = %d, want 2 (desktop button + mobile menu)", got)
	}
	if got := strings.Count(nav, `href="/sites/"`); got != 2 {
		t.Errorf("navigation sites links = %d, want 2 (desktop button + mobile menu)", got)
	}
	if strings.Index(nav, `href="/articles/"`) > strings.Index(nav, `href="/sites/"`) {
		t.Error("navigation articles link should appear before sites link")
	}
	if !strings.Contains(nav, "🌐") {
		t.Error("navigation is missing the www emoji for sites")
	}
	if !strings.Contains(nav, `btn btn-sm btn-outline btn-primary rounded-xl font-semibold gap-1.5 px-4" href="/articles/"`) {
		t.Error("navigation articles button is missing rounded-xl outline styling")
	}
	if !strings.Contains(nav, `btn btn-sm btn-outline btn-primary rounded-xl font-semibold gap-1.5 px-4" href="/sites/"`) {
		t.Error("navigation sites button is missing rounded-xl outline styling")
	}
}

func extractRegion(t *testing.T, body, name, startTag, endTag string) string {
	t.Helper()
	start := strings.Index(body, startTag)
	if start < 0 {
		t.Fatalf("home page missing %s", name)
	}
	end := strings.Index(body[start:], endTag)
	if end < 0 {
		t.Fatalf("home page has unterminated %s", name)
	}
	return body[start : start+end]
}

func TestNotFound(t *testing.T) {
	srv := newServer(t)

	status, _, body := get(t, srv.URL+"/does-not-exist")
	if status != http.StatusNotFound {
		t.Fatalf("status = %d, want 404", status)
	}
	if !strings.Contains(body, "</html>") {
		t.Error("404 should render the full layout")
	}
}

func TestSecurityTxt(t *testing.T) {
	srv := newServer(t)

	// RFC 9116 mandates the file at /.well-known/security.txt; /security.txt is a
	// legacy fallback. Both must serve a policy whose Expires is always future.
	for _, path := range []string{"/security.txt", "/.well-known/security.txt"} {
		status, hdr, body := get(t, srv.URL+path)
		if status != http.StatusOK {
			t.Fatalf("%s status = %d, want 200", path, status)
		}
		if ct := hdr.Get("Content-Type"); !strings.HasPrefix(ct, "text/plain") {
			t.Errorf("%s Content-Type = %q, want text/plain", path, ct)
		}
		if !strings.Contains(body, "Contact: mailto:contact@fmind.dev") {
			t.Errorf("%s missing Contact line:\n%s", path, body)
		}

		var expires string
		for _, line := range strings.Split(body, "\n") {
			if after, ok := strings.CutPrefix(line, "Expires: "); ok {
				expires = after
				break
			}
		}
		if expires == "" {
			t.Fatalf("%s missing Expires line:\n%s", path, body)
		}
		ts, err := time.Parse(time.RFC3339, expires)
		if err != nil {
			t.Fatalf("%s Expires %q is not RFC 3339: %v", path, expires, err)
		}
		if !ts.After(time.Now()) {
			t.Errorf("%s Expires %q is not in the future", path, expires)
		}
	}
}

func TestHealth(t *testing.T) {
	srv := newServer(t)

	status, _, body := get(t, srv.URL+"/health")
	if status != http.StatusOK {
		t.Fatalf("status = %d, want 200", status)
	}
	if !strings.Contains(body, `"ok"`) {
		t.Errorf("health body = %q", body)
	}
}

func TestProfileAPI(t *testing.T) {
	srv := newServer(t)

	status, hdr, body := get(t, srv.URL+"/api/profile")
	if status != http.StatusOK {
		t.Fatalf("status = %d, want 200", status)
	}
	if ct := hdr.Get("Content-Type"); !strings.HasPrefix(ct, "application/json") {
		t.Errorf("Content-Type = %q, want application/json", ct)
	}
	if cors := hdr.Get("Access-Control-Allow-Origin"); cors != "*" {
		t.Errorf("Access-Control-Allow-Origin = %q, want *", cors)
	}
	var payload site.Portfolio
	if err := json.Unmarshal([]byte(body), &payload); err != nil {
		t.Fatalf("decode profile: %v", err)
	}
	const headline = "AI Architect (PhD) • VC Expert Advisor • AAIF Ambassador • GCP Certified Cloud Architect • AI Agents, MLOps & Security"
	if payload.Metadata.HeadlinePrimary != headline {
		t.Errorf("profile headline = %q, want %q", payload.Metadata.HeadlinePrimary, headline)
	}
	if payload.Metadata.JobTitle != "AI Architect (PhD) • Freelancer" {
		t.Errorf("profile job title = %q", payload.Metadata.JobTitle)
	}

	// The tag vocabulary ships with the profile so a consumer can filter the
	// article list without inferring the taxonomy from the articles themselves.
	assertOrderedValues(t, "profile tags", tagNames(payload.Tags), templates.TagNames())
	for _, tag := range payload.Tags {
		if tag.Description == "" {
			t.Errorf("tag %q has no description", tag.Name)
		}
	}
	for _, article := range payload.Articles {
		for _, tag := range article.Tags {
			if !templates.IsTag(tag) {
				t.Errorf("article %q carries unknown tag %q", article.Slug, tag)
			}
		}
	}

	wantSocials := []struct {
		name   string
		header bool
	}{
		{name: "LinkedIn", header: true},
		{name: "X (Twitter)", header: true},
		{name: "Bluesky", header: false},
		{name: "Medium", header: true},
		{name: "GitHub", header: true},
		{name: "YouTube", header: true},
	}
	if len(payload.Metadata.Socials) != len(wantSocials) {
		t.Fatalf("profile socials = %d, want %d", len(payload.Metadata.Socials), len(wantSocials))
	}
	for i, want := range wantSocials {
		got := payload.Metadata.Socials[i]
		if got.Name != want.name || got.Header != want.header {
			t.Errorf("profile social %d = (%q, header=%t), want (%q, header=%t)", i, got.Name, got.Header, want.name, want.header)
		}
	}

	if len(payload.Biography) != 3 {
		t.Fatalf("biography paragraphs = %d, want 3", len(payload.Biography))
	}
	if !strings.Contains(payload.Biography[0], "**freelance AI Architect**") {
		t.Errorf("profile biography should preserve Markdown emphasis: %q", payload.Biography[0])
	}
	for index, paragraph := range payload.Biography {
		if strings.TrimSpace(paragraph) == "" {
			t.Errorf("biography paragraph %d is empty", index)
		}
	}

	expertise := make([]string, len(payload.Expertise))
	for i, item := range payload.Expertise {
		expertise[i] = item.Title
	}
	assertOrderedValues(t, "expertise", expertise, []string{
		"Agentic Orchestration",
		"Production MLOps",
		"Security-First AI",
		"Technical Strategy",
		"Data Science & ML",
		"Python Development",
	})

	experience := make([]string, len(payload.Experience))
	for i, item := range payload.Experience {
		experience[i] = item.Company
	}
	assertOrderedValues(t, "experience", experience, []string{
		"Decathlon",
		"European Commission",
		"ArcelorMittal",
		"BNP Paribas",
		"Google",
		"SFEIR",
		"University of Luxembourg",
		"Clearstream",
	})

	certifications := make([]string, len(payload.Certifications))
	for i, item := range payload.Certifications {
		certifications[i] = item.Title
	}
	assertOrderedValues(t, "certifications", certifications, []string{
		"Agentic AI Foundation Ambassador",
		"Professional Cloud Architect",
		"Professional ML Engineer",
		"Machine Learning Associate",
		"Data Scientist Associate",
		"Graph Data Science",
	})
	if len(payload.Specializations) != 9 {
		t.Errorf("profile specializations = %d, want 9", len(payload.Specializations))
	}
	if len(payload.Leadership) != 3 {
		t.Errorf("profile leadership roles = %d, want 3", len(payload.Leadership))
	}

	// Derived from the embedded set so publishing an article does not fail the suite;
	// the invariant under test is that the profile exposes every public article.
	if want := site.PublicArticleCount(t); len(payload.Articles) != want {
		t.Fatalf("profile articles = %d, want %d", len(payload.Articles), want)
	}
	// Article ordering is asserted against the frozen Medium import, identified by
	// its syndication URL: a natively published article legitimately becomes the
	// newest entry and must not turn this reverse-chronology check into a failure.
	newestArchived := -1
	for i, article := range payload.Articles {
		if strings.HasPrefix(article.Syndicated, "https://medium.com/@fmind/") || strings.HasPrefix(article.Syndicated, "https://fmind.medium.com/") {
			newestArchived = i
			break
		}
	}
	if newestArchived < 0 {
		t.Fatal("profile exposes no imported Medium article")
	}
	newest := payload.Articles[newestArchived]
	if newest.Title != "MCP 2026–07–28: Stateless core, enterprise authorization, and SDK betas" {
		t.Errorf("newest archived article = %q", newest.Title)
	}
	if newest.URL != "https://www.fmind.dev/articles/mcp-2026-07-28-stateless-core-enterprise-authorization-and-sdk-betas/" {
		t.Errorf("newest archived article URL = %q", newest.URL)
	}
}

func TestArticlePagesAndDiscovery(t *testing.T) {
	srv := newServer(t)
	const slug = "mcp-2026-07-28-stateless-core-enterprise-authorization-and-sdk-betas"
	const title = "MCP 2026–07–28: Stateless core, enterprise authorization, and SDK betas"

	status, _, index := get(t, srv.URL+"/articles/")
	if status != http.StatusOK {
		t.Fatalf("article index status = %d, want 200", status)
	}
	newest := strings.Index(index, title)
	next := strings.Index(index, "The Affordable AI Agents")
	if newest < 0 || next < 0 || newest >= next {
		t.Errorf("article index is not reverse chronological: newest=%d next=%d", newest, next)
	}
	for _, want := range []string{"2026", "min read", "?tag=Agent", "/articles/" + slug + "/"} {
		if !strings.Contains(index, want) {
			t.Errorf("article index missing %q", want)
		}
	}

	status, _, article := get(t, srv.URL+"/articles/"+slug+"/")
	if status != http.StatusOK {
		t.Fatalf("article status = %d, want 200", status)
	}
	for _, want := range []string{
		`<link rel="canonical" href="https://www.fmind.dev/articles/` + slug + `/"`,
		`<meta property="og:type" content="article"`,
		`<meta name="twitter:card" content="summary_large_image"`,
		`<meta name="description"`,
		`/static/img/articles/` + slug + `/cover.`,
		`"@type":"BlogPosting"`,
		`"author":{"@id":"https://www.fmind.dev/#person"}`,
		`<link rel="preload" href="/static/img/articles/` + slug + `/cover.webp" imagesrcset="/static/img/articles/` + slug + `/cover-800.webp 800w,`,
		`fetchpriority="high"`,
		`srcset="/static/img/articles/` + slug + `/cover-800.webp 800w,`,
	} {
		if !strings.Contains(article, want) {
			t.Errorf("article page missing %q", want)
		}
	}

	// The preload scanner and the layout must resolve the cover to the same file.
	// With href alone the phone fetches the full-size cover for the preload and the
	// 800px derivative for the paint, paying twice for one image.
	preloadSrcset := attributeValue(t, article, `<link rel="preload" href="/static/img/articles/`+slug+`/cover.webp"`, "imagesrcset")
	renderedSrcset := attributeValue(t, article, `<img fetchpriority="high"`, "srcset")
	if preloadSrcset == "" || preloadSrcset != renderedSrcset {
		t.Errorf("preload imagesrcset %q does not match rendered srcset %q", preloadSrcset, renderedSrcset)
	}
	preloadSizes := attributeValue(t, article, `<link rel="preload" href="/static/img/articles/`+slug+`/cover.webp"`, "imagesizes")
	renderedSizes := attributeValue(t, article, `<img fetchpriority="high"`, "sizes")
	if preloadSizes == "" || preloadSizes != renderedSizes {
		t.Errorf("preload imagesizes %q does not match rendered sizes %q", preloadSizes, renderedSizes)
	}
	if got := strings.Count(article, `"@type":"Person"`); got != 1 {
		t.Errorf("Person JSON-LD definitions = %d, want 1", got)
	}

	// Readers land on an article first (search engines and syndicated copies point
	// here), so the page has to attribute the author and offer a next step.
	for _, want := range []string{
		"Keep reading",
		"Book a Session",
		"Contact Me",
		"Subscribe (Atom)",
		templates.METADATA.JobTitle,
	} {
		if !strings.Contains(article, want) {
			t.Errorf("article page missing %q", want)
		}
	}
	if got := strings.Count(article, `href="/articles/`+slug+`/"`); got != 0 {
		t.Errorf("article page links to itself %d times, want 0", got)
	}

	status, headers, feed := get(t, srv.URL+"/articles/feed.xml")
	if status != http.StatusOK || !strings.HasPrefix(headers.Get("Content-Type"), "application/atom+xml") {
		t.Fatalf("Atom response status=%d content-type=%q", status, headers.Get("Content-Type"))
	}
	if got, want := strings.Count(feed, "<entry>"), site.PublicArticleCount(t); got != want {
		t.Errorf("Atom entries = %d, want %d", got, want)
	}
	if got := strings.Count(feed, `<content type="html">`); got != 15 {
		t.Errorf("Atom full-content entries = %d, want 15", got)
	}
	if strings.Contains(feed, `href="/`) || strings.Contains(feed, `src="/`) {
		t.Error("Atom feed contains a relative URL")
	}
	if !strings.Contains(feed, "https://www.fmind.dev/articles/"+slug+"/") {
		t.Error("Atom feed is missing the newest article URL")
	}

	status, _, sitemap := get(t, srv.URL+"/sitemap.xml")
	if status != http.StatusOK {
		t.Fatalf("sitemap status = %d, want 200", status)
	}
	// This site is canonical for everything it publishes, so every public article
	// and registered decision tool belongs beside the three index pages.
	if got, want := strings.Count(sitemap, "<url>"), site.SitemapArticleCount(t)+3+len(templates.SITE_PAGES); got != want {
		t.Errorf("sitemap URLs = %d, want %d", got, want)
	}
	if !strings.Contains(sitemap, "/articles/"+slug+"/") {
		t.Error("sitemap is missing a published article")
	}

	status, _, llms := get(t, srv.URL+"/llms.txt")
	if status != http.StatusOK || !strings.Contains(llms, title) {
		t.Errorf("llms.txt status=%d, newest article present=%t", status, strings.Contains(llms, title))
	}
	for _, want := range []string{"/llms-full.txt", "/articles/feed.xml", "/sitemap.xml", "## Optional"} {
		if !strings.Contains(llms, want) {
			t.Errorf("llms.txt missing %q", want)
		}
	}
	status, _, llmsFull := get(t, srv.URL+"/llms-full.txt")
	if status != http.StatusOK || !strings.Contains(llmsFull, "## Full articles") || !strings.Contains(llmsFull, title) {
		t.Errorf("llms-full.txt status=%d has full corpus=%t", status, strings.Contains(llmsFull, "## Full articles"))
	}
}

func TestArticleTagFilterIsServerRendered(t *testing.T) {
	srv := newServer(t)

	status, _, body := get(t, srv.URL+"/articles/?tag=MLOps")
	if status != http.StatusOK {
		t.Fatalf("status = %d, want 200", status)
	}
	if !strings.Contains(body, "Make your MLOps code base SOLID") {
		t.Error("MLOps filter is missing a matching article")
	}
	if strings.Contains(body, "The Affordable AI Agents") {
		t.Error("MLOps filter includes an article without that tag")
	}
	if !strings.Contains(body, `class="tag tag-active" data-tag="MLOps"`) {
		t.Error("the active tag chip is not marked as selected")
	}
}

// TestArticleTagsUseTheCanonicalVocabulary guards the property the closed
// vocabulary exists for: the filter row can only ever show known, colored chips,
// listed in vocabulary order rather than alphabetically.
func TestArticleTagsUseTheCanonicalVocabulary(t *testing.T) {
	srv := newServer(t)

	_, _, index := get(t, srv.URL+"/articles/")
	chips := regexp.MustCompile(`data-tag="([^"]+)"`).FindAllStringSubmatch(index, -1)
	if len(chips) == 0 {
		t.Fatal("article index renders no tag chips")
	}

	seen := make([]string, 0, len(templates.TAGS))
	for _, chip := range chips {
		tag := chip[1]
		if !templates.IsTag(tag) {
			t.Errorf("article index shows unknown tag %q", tag)
		}
		if !slices.Contains(seen, tag) {
			seen = append(seen, tag)
		}
	}
	// The filter nav is rendered before any card, so first appearance follows the
	// vocabulary order.
	ordered := slices.IsSortedFunc(seen, func(a, b string) int {
		return templates.TagOrder(a) - templates.TagOrder(b)
	})
	if !ordered {
		t.Errorf("tag chips are not in vocabulary order: %v", seen)
	}
	// Every tag in the vocabulary must carry its own color, so no two chips are
	// rendered with the same fallback hue. Quoting varies once the CSS is minified.
	for _, tag := range templates.TagNames() {
		rule := regexp.MustCompile(`\[data-tag=['"]?` + regexp.QuoteMeta(tag) + `['"]?\]`)
		if !rule.MatchString(templates.InlineStyles) {
			t.Errorf("tag %q has no color rule in the stylesheet", tag)
		}
	}
}

func tagNames(tags []templates.Tag) []string {
	names := make([]string, 0, len(tags))
	for _, tag := range tags {
		names = append(names, tag.Name)
	}
	return names
}

func assertOrderedValues(t *testing.T, name string, got, want []string) {
	t.Helper()
	if len(got) != len(want) {
		t.Fatalf("%s count = %d, want %d", name, len(got), len(want))
	}
	for i := range want {
		if got[i] != want[i] {
			t.Errorf("%s[%d] = %q, want %q", name, i, got[i], want[i])
		}
	}
}

func TestSecurityHeaders(t *testing.T) {
	srv := newServer(t)

	_, hdr, _ := get(t, srv.URL+"/")
	checks := map[string]string{
		"X-Content-Type-Options": "nosniff",
		"X-Frame-Options":        "DENY",
		"Referrer-Policy":        "strict-origin-when-cross-origin",
	}
	for header, want := range checks {
		if got := hdr.Get(header); got != want {
			t.Errorf("%s = %q, want %q", header, got, want)
		}
	}
	if csp := hdr.Get("Content-Security-Policy"); !strings.Contains(csp, "default-src 'self'") {
		t.Errorf("CSP missing default-src: %q", csp)
	}
	// HSTS must NOT be set in development.
	if hdr.Get("Strict-Transport-Security") != "" {
		t.Error("HSTS should be absent in development")
	}
}

func TestProductionSecurityHeadersIncludeHSTS(t *testing.T) {
	handler := site.SecurityHeaders(config.Production)(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	}))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, "https://www.fmind.dev/", nil))

	if got := recorder.Header().Get("Strict-Transport-Security"); got != "max-age=63072000; includeSubDomains; preload" {
		t.Errorf("Strict-Transport-Security = %q", got)
	}
	if csp := recorder.Header().Get("Content-Security-Policy"); strings.Contains(csp, "'unsafe-inline'") || !strings.Contains(csp, "style-src 'self' 'nonce-") {
		t.Errorf("CSP does not enforce nonced styles: %q", csp)
	}
}

func TestCanonicalHost(t *testing.T) {
	next := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusNoContent) })

	redirect := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodGet, "http://fmind.dev:8080/articles/?tag=Agent", nil)
	request.Host = "fmind.dev:8080"
	site.CanonicalHost(config.Production)(next).ServeHTTP(redirect, request)
	if redirect.Code != http.StatusMovedPermanently {
		t.Fatalf("apex status = %d, want 301", redirect.Code)
	}
	if got := redirect.Header().Get("Location"); got != "https://www.fmind.dev/articles/?tag=Agent" {
		t.Errorf("apex Location = %q", got)
	}

	passthrough := httptest.NewRecorder()
	site.CanonicalHost(config.Development)(next).ServeHTTP(passthrough, request)
	if passthrough.Code != http.StatusNoContent {
		t.Errorf("development status = %d, want 204", passthrough.Code)
	}
}

func TestDraftArticleRoutesUseInjectedCollection(t *testing.T) {
	article := templates.Article{
		Title:          "Draft fixture",
		Description:    "A route-level draft fixture.",
		Date:           time.Date(2026, time.August, 1, 0, 0, 0, 0, time.UTC),
		Updated:        time.Date(2026, time.August, 1, 0, 0, 0, 0, time.UTC),
		Slug:           "draft-fixture",
		URL:            templates.METADATA.SiteURL + "/articles/draft-fixture/",
		ImageURL:       templates.METADATA.SiteURL + "/static/img/og-image.jpg",
		CardImageURL:   templates.METADATA.SiteURL + "/static/img/og-image.jpg",
		ImageAlt:       "Draft fixture",
		HTML:           "<p>Draft body</p>",
		Markdown:       "Draft body",
		Tags:           []string{"Agent"},
		ReadingMinutes: 1,
		Draft:          true,
	}

	for _, testCase := range []struct {
		name        string
		environment config.Environment
		wantBody    string
		wantStatus  int
	}{
		{name: "production hides draft", environment: config.Production, wantStatus: http.StatusNotFound, wantBody: "Page not found"},
		{name: "development renders noindex", environment: config.Development, wantStatus: http.StatusOK, wantBody: `<meta name="robots" content="noindex, follow"`},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			srv := httptest.NewServer(site.NewTestAppHandler(t, testCase.environment, []templates.Article{article}))
			t.Cleanup(srv.Close)
			status, _, body := get(t, srv.URL+"/articles/draft-fixture/")
			if status != testCase.wantStatus || !strings.Contains(body, testCase.wantBody) {
				t.Errorf("draft response status=%d body contains %q=%t", status, testCase.wantBody, strings.Contains(body, testCase.wantBody))
			}
		})
	}

	srv := httptest.NewServer(site.NewTestAppHandler(t, config.Development, []templates.Article{article}))
	t.Cleanup(srv.Close)
	client := &http.Client{CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse }}
	resp, err := client.Get(srv.URL + "/articles/draft-fixture")
	if err != nil {
		t.Fatalf("GET draft without slash: %v", err)
	}
	defer closeBody(t, resp.Body)
	if resp.StatusCode != http.StatusMovedPermanently || resp.Header.Get("Location") != "/articles/draft-fixture/" {
		t.Errorf("canonical redirect status=%d location=%q", resp.StatusCode, resp.Header.Get("Location"))
	}
}

func TestRequestLoggerRecordsFirstFinalStatus(t *testing.T) {
	var logs bytes.Buffer
	logger := slog.New(slog.NewJSONHandler(&logs, nil))
	handler := site.RequestLogger(logger)(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusCreated)
		w.WriteHeader(http.StatusTeapot)
	}))

	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, "/logged", nil))

	if recorder.Code != http.StatusCreated {
		t.Fatalf("response status = %d, want 201", recorder.Code)
	}
	if got := logs.String(); !strings.Contains(got, `"status":201`) {
		t.Errorf("log = %q, want status 201", got)
	}
}

func TestAnalyticsLoggerEmitsOnlyAggregatePageviewFields(t *testing.T) {
	var logs bytes.Buffer
	logger := slog.New(slog.NewJSONHandler(&logs, nil))
	handler := site.AnalyticsLogger(logger)(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.WriteHeader(http.StatusNotFound)
	}))

	req := httptest.NewRequest(http.MethodGet, "https://www.fmind.dev/reset/alice@example.com/?utm_source=linkedin&utm_medium=social&utm_campaign=launch", nil)
	req.Header.Set("Referer", "https://news.example/path?private=value")
	req.Header.Set("User-Agent", "ExampleCrawler/1.0 secret-fingerprint")
	req.Header.Set("X-Client-Geo", "fr")
	req.RemoteAddr = "203.0.113.42:1234"
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, req)

	var record map[string]any
	if err := json.Unmarshal(logs.Bytes(), &record); err != nil {
		t.Fatalf("decode analytics log: %v", err)
	}
	wants := map[string]any{
		"msg":          "analytics_pageview",
		"path":         "/404",
		"status":       float64(http.StatusNotFound),
		"referer":      "news.example",
		"utm_source":   "linkedin",
		"utm_medium":   "social",
		"utm_campaign": "launch",
		"country":      "FR",
		"bot":          true,
	}
	for key, want := range wants {
		if got := record[key]; got != want {
			t.Errorf("analytics %s = %#v, want %#v", key, got, want)
		}
	}
	for _, forbidden := range []string{"ip", "remote_addr", "user_agent", "session", "visitor", "trace_id", "span_id"} {
		if _, found := record[forbidden]; found {
			t.Errorf("analytics record must not contain %q", forbidden)
		}
	}
	serialized := logs.String()
	for _, secret := range []string{"203.0.113.42", "secret-fingerprint", "/path?private=value", "alice@example.com"} {
		if strings.Contains(serialized, secret) {
			t.Errorf("analytics record leaked %q: %s", secret, serialized)
		}
	}
}

func TestOtelHandlerCorrelatesNormalLogsButNeverAnalytics(t *testing.T) {
	provider := sdktrace.NewTracerProvider(sdktrace.WithSampler(sdktrace.AlwaysSample()))
	t.Cleanup(func() {
		if err := provider.Shutdown(context.Background()); err != nil {
			t.Errorf("shutdown tracer provider: %v", err)
		}
	})
	ctx, span := provider.Tracer("test").Start(context.Background(), "active")
	defer span.End()

	var logs bytes.Buffer
	handler := (&site.OtelHandler{Handler: slog.NewJSONHandler(&logs, nil)}).
		WithAttrs([]slog.Attr{slog.String("component", "test")}).
		WithGroup("scope")
	logger := slog.New(handler)
	logger.InfoContext(ctx, "normal")
	logger.InfoContext(ctx, "analytics_pageview")

	lines := strings.Split(strings.TrimSpace(logs.String()), "\n")
	if len(lines) != 2 {
		t.Fatalf("log lines = %d, want 2: %s", len(lines), logs.String())
	}
	for _, want := range []string{`"component":"test"`, `"trace_id":"`, `"span_id":"`, `"scope":{`} {
		if !strings.Contains(lines[0], want) {
			t.Errorf("normal log missing %s: %s", want, lines[0])
		}
	}
	for _, forbidden := range []string{`"trace_id"`, `"span_id"`} {
		if strings.Contains(lines[1], forbidden) {
			t.Errorf("analytics log contains %s: %s", forbidden, lines[1])
		}
	}
	if !strings.Contains(lines[1], `"component":"test"`) {
		t.Errorf("WithAttrs was not preserved: %s", lines[1])
	}
}

func TestAnalyticsLoggerSkipsNonHTMLAndRedirects(t *testing.T) {
	var logs bytes.Buffer
	logger := slog.New(slog.NewJSONHandler(&logs, nil))
	for name, handler := range map[string]http.Handler{
		"JSON": http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			w.Header().Set("Content-Type", "application/json")
		}),
		"redirect": http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			http.Redirect(w, r, "/articles/", http.StatusMovedPermanently)
		}),
	} {
		t.Run(name, func(t *testing.T) {
			site.AnalyticsLogger(logger)(handler).ServeHTTP(httptest.NewRecorder(), httptest.NewRequest(http.MethodGet, "/test", nil))
		})
	}
	if logs.Len() != 0 {
		t.Errorf("unexpected analytics logs: %s", logs.String())
	}
}

func TestStaticAssetImmutableCache(t *testing.T) {
	srv := newServer(t)

	status, hdr, _ := get(t, srv.URL+"/static/img/avatar-192.webp?v=abcdef01")
	if status != http.StatusOK {
		t.Fatalf("status = %d, want 200", status)
	}
	if cc := hdr.Get("Cache-Control"); !strings.Contains(cc, "immutable") {
		t.Errorf("versioned asset Cache-Control = %q, want immutable", cc)
	}
}

func TestStaticAssetETagRevalidation(t *testing.T) {
	srv := newServer(t)
	assetURL := srv.URL + "/static/img/avatar-192.webp"

	status, headers, _ := get(t, assetURL)
	if status != http.StatusOK {
		t.Fatalf("initial status = %d, want 200", status)
	}
	etag := headers.Get("ETag")
	if etag == "" {
		t.Fatal("static response is missing ETag")
	}
	req, err := http.NewRequest(http.MethodGet, assetURL, nil)
	if err != nil {
		t.Fatalf("new revalidation request: %v", err)
	}
	req.Header.Set("If-None-Match", "W/"+etag)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("revalidate static asset: %v", err)
	}
	defer closeBody(t, resp.Body)
	if resp.StatusCode != http.StatusNotModified {
		t.Errorf("revalidation status = %d, want 304", resp.StatusCode)
	}

	status, headers, _ = get(t, assetURL+"?xv=1")
	if status != http.StatusOK || strings.Contains(headers.Get("Cache-Control"), "immutable") {
		t.Errorf("non-v query cache policy = %q", headers.Get("Cache-Control"))
	}
}

func TestMCPServerCardDiscovery(t *testing.T) {
	srv := newServer(t)
	for _, path := range []string{"/mcp/server-card", "/.well-known/mcp/server-card.json"} {
		status, headers, body := get(t, srv.URL+path)
		if status != http.StatusOK {
			t.Fatalf("%s status = %d, want 200", path, status)
		}
		if contentType := headers.Get("Content-Type"); !strings.HasPrefix(contentType, "application/mcp-server-card+json") {
			t.Errorf("%s content type = %q", path, contentType)
		}
		if headers.Get("Access-Control-Allow-Origin") != "*" {
			t.Errorf("%s missing public CORS", path)
		}
		for _, want := range []string{
			`"protocolVersion": "2026-07-28"`,
			`"type": "streamable-http"`,
			`"endpoint": "https://www.fmind.dev/mcp"`,
			`"name": "get_profile"`,
			`"name": "assess_fit"`,
			`"resources"`,
		} {
			if !strings.Contains(body, want) {
				t.Errorf("%s card missing %s: %s", path, want, body)
			}
		}
	}
}

func TestPrecompressedAssetsAreNotRecompressed(t *testing.T) {
	srv := newServer(t)
	client := &http.Client{Transport: &http.Transport{DisableCompression: true}}

	for _, asset := range []string{
		"/favicon.ico",
		"/static/img/avatar-192.webp",
		"/static/img/favicons/icon-192.png",
		"/static/fonts/Inter-Variable.woff2",
	} {
		t.Run(asset, func(t *testing.T) {
			req, err := http.NewRequest(http.MethodGet, srv.URL+asset, nil)
			if err != nil {
				t.Fatalf("new request: %v", err)
			}
			req.Header.Set("Accept-Encoding", "zstd, gzip")
			resp, err := client.Do(req)
			if err != nil {
				t.Fatalf("GET: %v", err)
			}
			defer closeBody(t, resp.Body)
			if encoding := resp.Header.Get("Content-Encoding"); encoding != "" {
				t.Errorf("Content-Encoding = %q, want identity", encoding)
			}
		})
	}
}

// TestRenderedInternalLinksResolve walks every same-origin link and asset the
// rendered pages emit and requires each to answer 200 with a fragment that
// actually exists. Broken internal links are invisible in unit tests otherwise:
// each surface renders fine on its own, and only the crossing fails.
func TestRenderedInternalLinksResolve(t *testing.T) {
	srv := newServer(t)
	linkPattern := regexp.MustCompile(`(?:href|src)="([^"]+)"`)
	idPattern := regexp.MustCompile(`\sid="([^"]+)"`)

	// One page of every kind the site renders, so a link that only exists in the
	// article layout or on the 404 page is still covered.
	pages := []string{"/", "/articles/", "/articles/the-affordable-ai-agents/", "/no-such-page"}
	seen := make(map[string]bool)
	for _, page := range pages {
		_, _, body := get(t, srv.URL+page)
		for _, match := range linkPattern.FindAllStringSubmatch(body, -1) {
			link := strings.TrimPrefix(match[1], templates.METADATA.SiteURL)
			if !strings.HasPrefix(link, "/") || seen[link] {
				continue
			}
			seen[link] = true
			path, fragment, _ := strings.Cut(link, "#")
			if path == "" {
				path = page
			}
			status, headers, target := get(t, srv.URL+path)
			if status != http.StatusOK {
				t.Errorf("%s (linked from %s) = %d, want 200", link, page, status)
				continue
			}
			if fragment == "" || !strings.HasPrefix(headers.Get("Content-Type"), "text/html") {
				continue
			}
			if !slices.ContainsFunc(idPattern.FindAllStringSubmatch(target, -1), func(id []string) bool {
				return id[1] == fragment
			}) {
				t.Errorf("%s (linked from %s) targets a missing anchor", link, page)
			}
		}
	}
	if len(seen) == 0 {
		t.Fatal("no internal links were discovered")
	}
}

// TestArticleSearchPage covers the search surface end to end: a plain GET form
// produces ranked results, composes with the tag filter, and stays out of the
// search-engine index (a result page is a view of articles, not a new page).
func TestArticleSearchPage(t *testing.T) {
	srv := newServer(t)

	status, _, page := get(t, srv.URL+"/articles/?q=kubeflow")
	if status != http.StatusOK {
		t.Fatalf("search status = %d, want 200", status)
	}
	for _, want := range []string{
		`name="q"`,
		"result",
		"kubeflow",
		"/articles/how-to-install-kubeflow-on-apple-silicon/",
		`<meta name="robots" content="noindex, follow"`,
	} {
		if !strings.Contains(page, want) {
			t.Errorf("search page missing %q", want)
		}
	}
	// The archive view groups by year; ranked results must not also be grouped.
	if strings.Contains(page, `id="year-`) {
		t.Error("search page still renders the year-grouped archive")
	}
	// Tag chips keep the query, so the two filters compose instead of resetting.
	if !strings.Contains(page, "q=kubeflow&amp;tag=") && !strings.Contains(page, "tag=Cloud&amp;q=kubeflow") {
		t.Error("tag chips drop the active search query")
	}

	_, _, empty := get(t, srv.URL+"/articles/?q=zzzznotaword")
	if !strings.Contains(empty, "No articles match this search") {
		t.Error("empty search result is missing its explanation")
	}

	// A query with no matching tag must return nothing rather than falling back
	// to the whole archive, which would look like the filter was ignored.
	_, _, mismatched := get(t, srv.URL+"/articles/?q=kubeflow&tag=Python")
	if strings.Contains(mismatched, "/articles/how-to-install-kubeflow-on-apple-silicon/") {
		t.Error("tag filter is ignored while searching")
	}
}

// TestArticleMarkdownSource covers the agent-facing Markdown surface: the source
// of any article, self-describing and with absolute links so it stands alone.
func TestArticleMarkdownSource(t *testing.T) {
	srv := newServer(t)
	const slug = "the-affordable-ai-agents"

	status, headers, body := get(t, srv.URL+"/articles/"+slug+".md")
	if status != http.StatusOK {
		t.Fatalf("markdown status = %d, want 200", status)
	}
	if contentType := headers.Get("Content-Type"); !strings.HasPrefix(contentType, "text/markdown") {
		t.Errorf("Content-Type = %q, want text/markdown", contentType)
	}
	if headers.Get("Access-Control-Allow-Origin") != "*" {
		t.Error("markdown source is not readable cross-origin by agents")
	}
	for _, want := range []string{
		"# The Affordable AI Agents",
		"- Tags: ",
		"- URL: https://www.fmind.dev/articles/" + slug + "/",
	} {
		if !strings.Contains(body, want) {
			t.Errorf("markdown source missing %q", want)
		}
	}
	// Root-relative asset links would break the moment the file is read off-site.
	if strings.Contains(body, "](/static/") {
		t.Error("markdown source keeps root-relative links")
	}
	if strings.HasPrefix(body, "+++") {
		t.Error("markdown source leaks TOML frontmatter")
	}

	if status, _, _ := get(t, srv.URL+"/articles/not-an-article.md"); status != http.StatusNotFound {
		t.Errorf("unknown markdown source status = %d, want 404", status)
	}

	// Discovery: the article page announces it and llms.txt lists it.
	_, _, page := get(t, srv.URL+"/articles/"+slug+"/")
	if !strings.Contains(page, `<link rel="alternate" type="text/markdown" href="/articles/`+slug+`.md"`) {
		t.Error("article page does not announce its Markdown source")
	}
	_, _, llms := get(t, srv.URL+"/llms.txt")
	if !strings.Contains(llms, "https://www.fmind.dev/articles/"+slug+".md") {
		t.Error("llms.txt does not list the Markdown source")
	}
}

func TestSitePagesAndLLMSelfHostingCalculator(t *testing.T) {
	srv := newServer(t)

	status, _, index := get(t, srv.URL+"/sites/")
	if status != http.StatusOK {
		t.Fatalf("site index status = %d, want 200", status)
	}
	for _, want := range []string{"Sites", "LLM self-hosting on GKE", `href="/sites/llm-self-hosting/"`} {
		if !strings.Contains(index, want) {
			t.Errorf("site index missing %q", want)
		}
	}

	status, _, calculator := get(t, srv.URL+"/sites/llm-self-hosting/?model=qwen3-8-27b&node=a2-ultra-1g&quant=fp4&replicas=2")
	if status != http.StatusOK {
		t.Fatalf("calculator status = %d, want 200", status)
	}
	for _, want := range []string{
		"When does self-hosting an LLM pay off?",
		"Gemini 3.8 Flash",
		"Claude Sonnet 5",
		"GPT-6 Astra",
		"Small team · 5–10 people",
		"4, 8, or 16-bit: what are you trading?",
		"cost per accepted task",
		"Top 10 open-weight models",
		"Qwen3.8 27B (xhigh)",
		"2 nodes · 2 GPUs",
		"Artificial Analysis model leaderboard",
		`<link rel="canonical" href="https://www.fmind.dev/sites/llm-self-hosting/"`,
		`"@type":"WebApplication"`,
	} {
		if !strings.Contains(calculator, want) {
			t.Errorf("calculator missing %q", want)
		}
	}
	if got := strings.Count(calculator, "https://artificialanalysis.ai/models/"); got != 10 {
		t.Errorf("ranked model links = %d, want 10", got)
	}

	if status, _, _ := get(t, srv.URL+"/sites/not-a-tool/"); status != http.StatusNotFound {
		t.Errorf("unknown site page status = %d, want 404", status)
	}

	_, _, sitemap := get(t, srv.URL+"/sitemap.xml")
	_, _, llms := get(t, srv.URL+"/llms.txt")
	for surface, body := range map[string]string{"sitemap": sitemap, "llms.txt": llms} {
		if !strings.Contains(body, "https://www.fmind.dev/sites/llm-self-hosting/") {
			t.Errorf("%s is missing the calculator URL", surface)
		}
	}
}

func TestContentRoutesRejectNestedPaths(t *testing.T) {
	srv := newServer(t)
	for _, path := range []string{
		"/articles/agentgateway-vs-litellm/extra",
		"/articles/agentgateway-vs-litellm/extra/",
		"/sites/llm-self-hosting/extra",
		"/sites/llm-self-hosting/extra/",
	} {
		t.Run(path, func(t *testing.T) {
			status, _, body := get(t, srv.URL+path)
			if status != http.StatusNotFound || !strings.Contains(body, `content="noindex, follow"`) {
				t.Errorf("nested content route: status = %d, want a noindex 404", status)
			}
		})
	}
}

func TestCalculatorRedirectPreservesScenario(t *testing.T) {
	srv := newServer(t)
	status, _, body := get(t, srv.URL+"/sites/llm-self-hosting?requests=234&replicas=2")
	if status != http.StatusOK || !strings.Contains(body, `value="234"`) || !strings.Contains(body, "2 nodes · 2 GPUs") {
		t.Fatal("canonical redirect lost the shared calculator assumptions")
	}
}

func TestHostingDemandAndCapacityStates(t *testing.T) {
	srv := newServer(t)
	for _, tc := range []struct {
		name, query  string
		want, absent []string
	}{
		{name: "small team", query: "preset=small-team", want: []string{"$13.20", "$35.20", "$176.00", "Start with an API on cost grounds", `aria-pressed="true"`, `aria-describedby="input-tokens-help"`}},
		{name: "one-off job", query: "preset=single-job&replicas=3", want: []string{"$0.68", "3 nodes · 3 GPUs", "Your scenario · Single job"}},
		{name: "overloaded", query: "preset=service&throughput=0.1", want: []string{"This fleet cannot cover the modeled demand", "Insufficient capacity", "Beyond this fleet"}, absent: []string{"Self-hosting has a cost case to test", "Start with an API on cost grounds"}},
		{name: "cost case", query: "preset=service&throughput=10000", want: []string{"Self-hosting has a cost case to test", "Within modeled capacity"}},
		{name: "invalid demand", query: "requests=NaN&days=32", want: []string{`role="alert"`, "Some inputs need attention", "requests must be between", "days must be between", "$13.20"}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			status, _, body := get(t, srv.URL+"/sites/llm-self-hosting/?"+tc.query)
			if status != http.StatusOK {
				t.Fatalf("status = %d", status)
			}
			for _, want := range tc.want {
				if !strings.Contains(body, want) {
					t.Errorf("missing %q", want)
				}
			}
			for _, absent := range tc.absent {
				if strings.Contains(body, absent) {
					t.Errorf("unexpected %q", absent)
				}
			}
		})
	}
}

// attributeValue reads one attribute from the first tag in body that starts with
// prefix, so a test can compare what two tags actually agreed on rather than
// asserting the same literal twice.
func attributeValue(t *testing.T, body, prefix, attribute string) string {
	t.Helper()
	start := strings.Index(body, prefix)
	if start < 0 {
		t.Errorf("no tag starting with %q", prefix)
		return ""
	}
	tag := body[start:]
	if end := strings.Index(tag, ">"); end >= 0 {
		tag = tag[:end]
	}
	marker := " " + attribute + `="`
	value := strings.Index(tag, marker)
	if value < 0 {
		return ""
	}
	rest := tag[value+len(marker):]
	quote := strings.Index(rest, `"`)
	if quote < 0 {
		return ""
	}
	return rest[:quote]
}

func TestHostingExplorersAndArticleConnections(t *testing.T) {
	srv := newServer(t)
	_, _, body := get(t, srv.URL+"/sites/llm-self-hosting/")
	for _, want := range []string{`data-cost-explorer`, `data-cost-frame`, `aria-valuetext="3,520 requests/month"`, `href="#cost-explorer"`, `id="sensitivity"`, `form="calculator"`, `API monthly cost cards`, `Responsiveness is still unproved`, `Verified 2026-09-05`, `Introductory rates through Dec 31, 2026`, `/articles/the-affordable-ai-agents/`} {
		if !strings.Contains(body, want) {
			t.Errorf("hosting page missing %q", want)
		}
	}
	if strings.Contains(body, "Cost per accepted task · your entered assumptions") {
		t.Error("quality results must require opting in")
	}
	_, _, quality := get(t, srv.URL+"/sites/llm-self-hosting/?quality=on&quality-0-acceptance=0")
	if !strings.Contains(quality, "No accepted tasks; cost per accepted task is undefined.") || !strings.Contains(quality, "Cost per accepted task · your entered assumptions") {
		t.Error("zero acceptance must not produce a misleading zero cost")
	}
	_, _, article := get(t, srv.URL+"/articles/the-affordable-ai-agents/")
	if !strings.Contains(article, "Put the ideas into practice") || !strings.Contains(article, `href="/sites/llm-self-hosting/"`) {
		t.Error("related article must link to the decision tool")
	}
}

func TestHostingPageKeepsSettingsVisibleAndAvoidsForcedAnchors(t *testing.T) {
	srv := newServer(t)
	_, _, body := get(t, srv.URL+"/sites/llm-self-hosting/")
	for _, absent := range []string{"New to tokens?", "Read break-even carefully.", "Adjust model, infrastructure, capacity, and API options (optional)", "The better metric: cost per accepted task", `formaction="/sites/llm-self-hosting/#`, `action="/sites/llm-self-hosting/#`, "Decision tools"} {
		if strings.Contains(body, absent) {
			t.Errorf("unexpected content or forced navigation: %q", absent)
		}
	}
	for _, want := range []string{`id="hosting-options"`, `data-hosting-calculator`, `data-scenario-link`, `id="update-comparison"`, `id="model"`, `id="throughput"`, `id="api-mode"`, `id="hosting-method"`, `id="hosting-sources"`} {
		if !strings.Contains(body, want) {
			t.Errorf("missing calculator control: %q", want)
		}
	}
	form := extractRegion(t, body, "calculator", `<form id="calculator"`, "</form>")
	if strings.Contains(form, "<details") {
		t.Error("main calculator settings must not collapse")
	}
	if strings.Contains(body, `<html lang="en" class="scroll-smooth"`) {
		t.Error("calculator must avoid animated anchor scrolling")
	}
}
