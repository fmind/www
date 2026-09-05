package site

import (
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/fmind/www/templates"
)

// article builds a minimal fixture: only the slug, date, and tags drive the
// recommendation ranking under test.
func article(slug string, day int, tags ...string) templates.Article {
	return templates.Article{
		Slug: slug,
		Date: time.Date(2026, time.January, day, 0, 0, 0, 0, time.UTC),
		Tags: tags,
	}
}

func TestRenderSitemapExcludesExternalCanonicalsAndUsesUpdatedDate(t *testing.T) {
	native := article("native", 2, "AI")
	native.URL = templates.METADATA.SiteURL + "/articles/native/"
	native.Updated = time.Date(2026, time.February, 3, 0, 0, 0, 0, time.UTC)
	syndicated := article("syndicated", 1, "AI")
	syndicated.URL = templates.METADATA.SiteURL + "/articles/syndicated/"
	syndicated.Canonical = "https://medium.example/syndicated"

	body, err := renderSitemap([]templates.Article{native, syndicated})
	if err != nil {
		t.Fatalf("render sitemap: %v", err)
	}
	got := string(body)
	if !strings.Contains(got, native.URL) || !strings.Contains(got, "<lastmod>2026-02-03</lastmod>") {
		t.Errorf("sitemap missing native updated article: %s", got)
	}
	if strings.Contains(got, syndicated.URL) {
		t.Errorf("sitemap contains externally canonical article: %s", got)
	}
}

func TestRenderAtomFeedLimitsFullContent(t *testing.T) {
	articles := make([]templates.Article, atomFullContentLimit+2)
	for i := range articles {
		articles[i] = article(fmt.Sprintf("article-%d", i), atomFullContentLimit+2-i, "AI")
		articles[i].Title = fmt.Sprintf("Article %d", i)
		articles[i].Description = "Summary"
		articles[i].URL = fmt.Sprintf("%s/articles/article-%d/", templates.METADATA.SiteURL, i)
		articles[i].HTML = "<p>Full body</p>"
	}
	articles[0].Updated = time.Date(2026, time.February, 3, 0, 0, 0, 0, time.UTC)

	body, err := renderAtomFeed(articles)
	if err != nil {
		t.Fatalf("render Atom feed: %v", err)
	}
	if got := strings.Count(string(body), `<content type="html">`); got != atomFullContentLimit {
		t.Errorf("full-content entries = %d, want %d", got, atomFullContentLimit)
	}
	if !strings.Contains(string(body), "<updated>2026-02-03T00:00:00Z</updated>") {
		t.Errorf("Atom feed does not surface the updated date: %s", body)
	}
}

func TestArticleIndexUnknownTagFallsBackToAllArticles(t *testing.T) {
	articles := []templates.Article{
		article("first", 2, "AI"),
		article("second", 1, "Cloud"),
	}
	view := articleIndexData(articles, newSearchIndex(articles), "not-a-real-tag", "")
	if view.ActiveTag != "" {
		t.Errorf("active tag = %q, want empty", view.ActiveTag)
	}
	count := 0
	for _, group := range view.Years {
		count += len(group.Articles)
	}
	if count != len(articles) {
		t.Errorf("fallback article count = %d, want %d", count, len(articles))
	}
}

func slugsOf(articles []templates.Article) []string {
	slugs := make([]string, 0, len(articles))
	for _, item := range articles {
		slugs = append(slugs, item.Slug)
	}
	return slugs
}

func TestRelatedArticlesRanksSharedTagsThenRecency(t *testing.T) {
	// Reverse-chronological, matching the collection handlers pass in.
	articles := []templates.Article{
		article("newest-unrelated", 5, "Cloud"),
		article("one-shared-tag", 4, "AI"),
		article("current", 3, "AI", "MLOps"),
		article("two-shared-tags", 2, "AI", "MLOps"),
		article("older-unrelated", 1, "Security"),
	}

	related := relatedArticles(articles[2], articles)

	want := []string{"two-shared-tags", "one-shared-tag", "newest-unrelated"}
	got := slugsOf(related)
	if len(got) != len(want) {
		t.Fatalf("related slugs = %v, want %v", got, want)
	}
	for i, slug := range want {
		if got[i] != slug {
			t.Errorf("related[%d] = %q, want %q (full order %v)", i, got[i], slug, got)
		}
	}
}

func TestRelatedArticlesExcludesCurrentAndBoundsLimit(t *testing.T) {
	articles := []templates.Article{
		article("current", 3, "AI"),
		article("other", 2, "AI"),
	}

	if got := relatedArticles(articles[0], articles); len(got) != 1 || got[0].Slug != "other" {
		t.Errorf("related = %v, want [other]", slugsOf(got))
	}
	// A single-article collection has nothing to recommend, so the block is empty
	// rather than self-referential.
	if got := relatedArticles(articles[0], articles[:1]); len(got) != 0 {
		t.Errorf("related for a lone article = %v, want none", slugsOf(got))
	}
}

func TestRelatedArticleIndexCoversEveryArticle(t *testing.T) {
	collection, err := loadArticles()
	if err != nil {
		t.Fatalf("load articles: %v", err)
	}
	articles := visibleArticles(collection.all, false)
	index := relatedArticleIndex(articles)

	if len(index) != len(articles) {
		t.Fatalf("index entries = %d, want %d", len(index), len(articles))
	}
	for _, item := range articles {
		related := index[item.Slug]
		if len(related) != relatedArticleCount {
			t.Errorf("%s has %d related articles, want %d", item.Slug, len(related), relatedArticleCount)
		}
		for _, suggestion := range related {
			if suggestion.Slug == item.Slug {
				t.Errorf("%s recommends itself", item.Slug)
			}
		}
	}
}
