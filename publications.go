package site

import (
	"bytes"
	"encoding/xml"
	"fmt"
	"slices"
	"strings"
	"time"

	"github.com/fmind/www/templates"
)

type atomFeed struct {
	XMLName xml.Name    `xml:"feed"`
	XMLNS   string      `xml:"xmlns,attr"`
	Title   string      `xml:"title"`
	ID      string      `xml:"id"`
	Updated string      `xml:"updated"`
	Links   []atomLink  `xml:"link"`
	Author  atomAuthor  `xml:"author"`
	Entries []atomEntry `xml:"entry"`
}

type atomLink struct {
	Href string `xml:"href,attr"`
	Rel  string `xml:"rel,attr,omitempty"`
	Type string `xml:"type,attr,omitempty"`
}

type atomAuthor struct {
	Name string `xml:"name"`
	URI  string `xml:"uri"`
}

type atomEntry struct {
	Title     string       `xml:"title"`
	ID        string       `xml:"id"`
	Published string       `xml:"published"`
	Updated   string       `xml:"updated"`
	Link      atomLink     `xml:"link"`
	Content   *atomContent `xml:"content,omitempty"`
	Summary   atomContent  `xml:"summary"`
}

type atomContent struct {
	Type string `xml:"type,attr"`
	Body string `xml:",chardata"`
}

type sitemap struct {
	XMLName xml.Name     `xml:"urlset"`
	XMLNS   string       `xml:"xmlns,attr"`
	URLs    []sitemapURL `xml:"url"`
}

type sitemapURL struct {
	Location string `xml:"loc"`
	LastMod  string `xml:"lastmod,omitempty"`
}

const atomFullContentLimit = 15

func renderAtomFeed(articles []templates.Article) ([]byte, error) {
	updated := time.Unix(0, 0).UTC()
	feed := atomFeed{
		XMLNS: "http://www.w3.org/2005/Atom",
		Title: "Fmind articles",
		ID:    templates.METADATA.SiteURL + "/articles/",
		Links: []atomLink{
			{Href: templates.METADATA.SiteURL + "/articles/feed.xml", Rel: "self", Type: "application/atom+xml"},
			{Href: templates.METADATA.SiteURL + "/articles/", Rel: "alternate", Type: "text/html"},
		},
		Author:  atomAuthor{Name: templates.METADATA.Name, URI: templates.METADATA.SiteURL + "/"},
		Entries: make([]atomEntry, 0, len(articles)),
	}
	for index, article := range articles {
		modified := article.ModifiedDate()
		if modified.After(updated) {
			updated = modified
		}
		entry := atomEntry{
			Title:     article.Title,
			ID:        article.URL,
			Published: atomTime(article.Date),
			Updated:   atomTime(modified),
			Link:      atomLink{Href: article.URL, Rel: "alternate", Type: "text/html"},
			Summary:   atomContent{Type: "text", Body: article.Description},
		}
		if index < atomFullContentLimit {
			entry.Content = &atomContent{Type: "html", Body: absoluteArticleHTML(article.HTML)}
		}
		feed.Entries = append(feed.Entries, entry)
	}
	feed.Updated = atomTime(updated)
	return encodeXML(feed)
}

func renderSitemap(articles []templates.Article) ([]byte, error) {
	urls := []sitemapURL{
		{Location: templates.METADATA.SiteURL + "/"},
		{Location: templates.METADATA.SiteURL + "/articles/"},
		{Location: templates.METADATA.SiteURL + "/sites/"},
	}
	for _, page := range templates.SITE_PAGES {
		urls = append(urls, sitemapURL{Location: page.URL})
	}
	for _, article := range articles {
		// This site is canonical for everything it publishes, so the whole archive
		// belongs in the sitemap. The guard remains for an article that ever
		// genuinely belongs to another site.
		if article.Canonical != "" {
			continue
		}
		urls = append(urls, sitemapURL{Location: article.URL, LastMod: article.ModifiedDate().Format(time.DateOnly)})
	}
	return encodeXML(sitemap{XMLNS: "http://www.sitemaps.org/schemas/sitemap/0.9", URLs: urls})
}

func renderLLMSTxt(articles []templates.Article) []byte {
	var body strings.Builder
	fmt.Fprintf(&body, "# %s — %s\n\n> %s\n\n", templates.METADATA.Name, templates.METADATA.AlternateName, templates.METADATA.HeadlinePrimary)
	body.WriteString("## Machine-readable portfolio\n\n")
	fmt.Fprintf(&body, "- [MCP server](%s/mcp): Read-only portfolio tools, resources, and prompts.\n", templates.METADATA.SiteURL)
	fmt.Fprintf(&body, "- [JSON profile](%s/api/profile): Canonical portfolio and article index.\n", templates.METADATA.SiteURL)
	fmt.Fprintf(&body, "- [Full LLM context](%s/llms-full.txt): This index plus every public article in Markdown.\n", templates.METADATA.SiteURL)
	fmt.Fprintf(&body, "- Article source: append `.md` to any article slug (%s/articles/<slug>.md) for its raw Markdown.\n", templates.METADATA.SiteURL)
	fmt.Fprintf(&body, "- [Atom feed](%s/articles/feed.xml): Reverse-chronological publication feed.\n", templates.METADATA.SiteURL)
	fmt.Fprintf(&body, "- [Sitemap](%s/sitemap.xml): Canonical hosted pages.\n\n", templates.METADATA.SiteURL)
	body.WriteString("## Sites\n\n")
	for _, page := range templates.SITE_PAGES {
		fmt.Fprintf(&body, "- [%s](%s) — %s\n", page.Title, page.URL, page.Description)
	}
	body.WriteString("\n")
	body.WriteString("## Articles\n\n")
	for _, article := range articles {
		fmt.Fprintf(&body, "- [%s](%s) — %s ([Markdown](%s))\n", article.Title, article.URL, article.Description, article.MarkdownURL())
	}
	body.WriteString("\n## Optional\n\n")
	fmt.Fprintf(&body, "- [PhD thesis](%s): %s\n", templates.THESIS.URL, templates.THESIS.Title)
	for _, paper := range templates.PAPERS {
		fmt.Fprintf(&body, "- [%s](%s) — %s\n", paper.Title, paper.URL, paper.Venue)
	}
	return []byte(body.String())
}

func renderLLMSFull(index []byte, articles []templates.Article) []byte {
	var body strings.Builder
	body.Write(index)
	body.WriteString("\n## Full articles\n")
	for _, article := range articles {
		fmt.Fprintf(&body, "\n### [%s](%s)\n\n%s\n", article.Title, article.URL, article.Markdown)
	}
	return []byte(body.String())
}

func encodeXML(value any) ([]byte, error) {
	var body bytes.Buffer
	body.WriteString(xml.Header)
	if err := xml.NewEncoder(&body).Encode(value); err != nil {
		return nil, fmt.Errorf("encode XML: %w", err)
	}
	return body.Bytes(), nil
}

func atomTime(date time.Time) string {
	return date.UTC().Format(time.RFC3339)
}

func absoluteArticleHTML(body string) string {
	// This string rewrite relies on two renderer invariants: Goldmark escapes
	// quotes in text and code, and raw HTML stays disabled (no WithUnsafe).
	body = strings.ReplaceAll(body, `href="/`, `href="`+templates.METADATA.SiteURL+`/`)
	return strings.ReplaceAll(body, `src="/`, `src="`+templates.METADATA.SiteURL+`/`)
}

// relatedArticleCount bounds the "keep reading" block rendered under an article.
const relatedArticleCount = 3

// relatedArticleIndex precomputes each article's suggested next reads at startup,
// keyed by slug, so request handlers stay allocation-free lookups.
func relatedArticleIndex(articles []templates.Article) map[string][]templates.Article {
	index := make(map[string][]templates.Article, len(articles))
	for _, article := range articles {
		index[article.Slug] = relatedArticles(article, articles)
	}
	return index
}

// relatedArticles ranks the rest of the collection by shared tags and then by
// recency, returning at most relatedArticleCount entries, so every article
// offers a next read even when it shares no tag with any other one.
func relatedArticles(current templates.Article, articles []templates.Article) []templates.Article {
	type candidate struct {
		article templates.Article
		shared  int
	}
	candidates := make([]candidate, 0, len(articles))
	for _, article := range articles {
		if article.Slug == current.Slug {
			continue
		}
		shared := 0
		for _, tag := range article.Tags {
			if slices.Contains(current.Tags, tag) {
				shared++
			}
		}
		candidates = append(candidates, candidate{article: article, shared: shared})
	}
	// articles arrives reverse-chronological, so sorting stably on the shared tag
	// count alone leaves recency as the tie-break.
	slices.SortStableFunc(candidates, func(a, b candidate) int { return b.shared - a.shared })
	limit := min(relatedArticleCount, len(candidates))
	related := make([]templates.Article, 0, limit)
	for _, candidate := range candidates[:limit] {
		related = append(related, candidate.article)
	}
	return related
}

// articleIndexData resolves one request's index view. A query switches the page
// from the year-grouped archive to relevance-ranked results; the tag filter
// applies in both modes, so the two narrow the same list instead of competing.
func articleIndexData(articles []templates.Article, index *searchIndex, requestedTag, requestedQuery string) templates.ArticleIndexView {
	tagSet := make(map[string]bool)
	for _, article := range articles {
		for _, tag := range article.Tags {
			tagSet[tag] = true
		}
	}
	tags := make([]string, 0, len(tagSet))
	for tag := range tagSet {
		tags = append(tags, tag)
	}
	// Canonical vocabulary order, not alphabetical: the filter row then reads
	// topic-first (Agent, Coding, LLM, …) instead of scattering related chips.
	templates.SortTags(tags)

	activeTag := ""
	for _, tag := range tags {
		if strings.EqualFold(tag, requestedTag) {
			activeTag = tag
			break
		}
	}
	matchesTag := func(article templates.Article) bool {
		return activeTag == "" || slices.Contains(article.Tags, activeTag)
	}

	view := templates.ArticleIndexView{Query: normalizeSearchQuery(requestedQuery), ActiveTag: activeTag, Tags: tags}
	if view.Searching() {
		view.Results = make([]templates.Article, 0)
		for _, article := range index.Search(view.Query) {
			if matchesTag(article) {
				view.Results = append(view.Results, article)
			}
		}
		return view
	}

	view.Years = make([]templates.ArticleYear, 0)
	for _, article := range articles {
		if !matchesTag(article) {
			continue
		}
		year := article.Date.Year()
		if len(view.Years) == 0 || view.Years[len(view.Years)-1].Year != year {
			view.Years = append(view.Years, templates.ArticleYear{Year: year})
		}
		view.Years[len(view.Years)-1].Articles = append(view.Years[len(view.Years)-1].Articles, article)
	}
	return view
}

// renderArticleMarkdown emits the agent-facing source of one article: the body
// the HTML page renders, prefixed with the metadata needed to cite it. TOML
// frontmatter stays out (it is repository syntax, not a published contract) and
// root-relative links are absolutized so the document stands alone off-site.
func renderArticleMarkdown(article templates.Article) []byte {
	var body strings.Builder
	fmt.Fprintf(&body, "# %s\n\n> %s\n\n", article.Title, article.Description)
	fmt.Fprintf(&body, "- Published: %s\n", article.Date.Format(time.DateOnly))
	if article.ModifiedDate().After(article.Date) {
		fmt.Fprintf(&body, "- Updated: %s\n", article.ModifiedDate().Format(time.DateOnly))
	}
	fmt.Fprintf(&body, "- Reading time: %d min\n", article.ReadingMinutes)
	fmt.Fprintf(&body, "- Tags: %s\n", strings.Join(article.Tags, ", "))
	fmt.Fprintf(&body, "- URL: %s\n", article.URL)
	if article.Canonical != "" {
		fmt.Fprintf(&body, "- Canonical: %s\n", article.Canonical)
	}
	if article.Syndicated != "" {
		fmt.Fprintf(&body, "- Also published at: %s\n", article.Syndicated)
	}
	fmt.Fprintf(&body, "\n%s\n", absoluteMarkdownLinks(article.Markdown))
	return []byte(body.String())
}

// absoluteMarkdownLinks rewrites root-relative Markdown links and images to the
// site origin. It relies on the same renderer invariant as absoluteArticleHTML:
// bodies are validated Markdown, so "](/" only ever opens a link destination.
func absoluteMarkdownLinks(markdown string) string {
	return strings.ReplaceAll(markdown, "](/", "]("+templates.METADATA.SiteURL+"/")
}

// articleMarkdownIndex precomputes every article's Markdown surface at startup,
// keyed by slug, so the route stays a map lookup and a write.
func articleMarkdownIndex(articles []templates.Article) map[string][]byte {
	index := make(map[string][]byte, len(articles))
	for _, article := range articles {
		index[article.Slug] = renderArticleMarkdown(article)
	}
	return index
}
