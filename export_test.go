package site

import (
	"log/slog"
	"net/http"
	"slices"
	"sync"
	"testing"

	"github.com/fmind/www/config"
	"github.com/fmind/www/templates"
)

var testArticles = sync.OnceValues(loadArticles)

// PublicArticleCount exposes the embedded public article count to the external test
// package, so surface assertions track the published content instead of a literal
// that has to be edited every time an article ships.
func PublicArticleCount(t *testing.T) int {
	t.Helper()
	collection, err := testArticles()
	if err != nil {
		t.Fatalf("load articles: %v", err)
	}
	return len(visibleArticles(collection.all, false))
}

func SitemapArticleCount(t *testing.T) int {
	t.Helper()
	collection, err := testArticles()
	if err != nil {
		t.Fatalf("load articles: %v", err)
	}
	// Only an article that genuinely belongs to another site is excluded; the
	// syndicated Medium copies do not change what this sitemap claims.
	count := 0
	for _, article := range visibleArticles(collection.all, false) {
		if article.Canonical == "" {
			count++
		}
	}
	return count
}

// NewTestAppHandler injects a small article collection so external route tests
// can prove draft behavior without coupling the suite to published content.
func NewTestAppHandler(t *testing.T, env config.Environment, articles []templates.Article) http.Handler {
	t.Helper()
	collection := articleCollection{
		all:    slices.Clone(articles),
		bySlug: make(map[string]templates.Article, len(articles)),
	}
	for _, article := range articles {
		collection.bySlug[article.Slug] = article
	}
	assets, err := initAssets()
	if err != nil {
		t.Fatalf("initialize test assets: %v", err)
	}
	handler, err := newAppHandler(slog.New(slog.DiscardHandler), config.Config{Environment: env, Port: 8080}, collection, assets)
	if err != nil {
		t.Fatalf("build injected application handler: %v", err)
	}
	return handler
}
