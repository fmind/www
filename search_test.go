package site

import (
	"strings"
	"testing"
	"time"

	"github.com/fmind/www/templates"
)

func searchArticle(slug, title, description, body string, tags ...string) templates.Article {
	return templates.Article{
		Slug:        slug,
		Title:       title,
		Description: description,
		Markdown:    body,
		Tags:        tags,
		Date:        time.Date(2026, time.January, 1, 0, 0, 0, 0, time.UTC),
	}
}

func searchSlugs(index *searchIndex, query string) []string {
	ranked := index.Search(query)
	slugs := make([]string, len(ranked))
	for i, article := range ranked {
		slugs[i] = article.Slug
	}
	return slugs
}

// TestSearchRanksTitleAndTagMatchesFirst pins the field boosts: an article whose
// title is about the query must outrank one that merely mentions it in passing,
// otherwise the ranking is no better than a substring filter.
func TestSearchRanksTitleAndTagMatchesFirst(t *testing.T) {
	index := newSearchIndex([]templates.Article{
		searchArticle("passing-mention", "Unrelated notes", "Nothing to see", "A long body that mentions kubeflow exactly once. "+strings.Repeat("filler words here. ", 100), "Cloud"),
		searchArticle("about-kubeflow", "Installing Kubeflow", "A guide to Kubeflow pipelines", "Body text about pipelines.", "Cloud"),
	})

	got := searchSlugs(index, "kubeflow")
	want := []string{"about-kubeflow", "passing-mention"}
	if len(got) != len(want) {
		t.Fatalf("results = %v, want %v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Errorf("result[%d] = %q, want %q (full order %v)", i, got[i], want[i], got)
		}
	}
}

// TestSearchMatchesAcrossFieldsAndPlurals covers the two things a reader assumes
// work: finding an article by a word that only appears in its body, and typing a
// plural (or singular) form of the indexed term.
func TestSearchMatchesAcrossFieldsAndPlurals(t *testing.T) {
	index := newSearchIndex([]templates.Article{
		searchArticle("agents", "Designing agents", "Agent architecture", "Body about orchestration.", "Agent"),
		searchArticle("bodies", "Something else", "Another topic", "Only this body mentions terraform.", "Cloud"),
	})

	cases := []struct {
		query string
		want  string
	}{
		{query: "agent", want: "agents"},         // query singular, document plural
		{query: "agents", want: "agents"},        // query plural, document singular
		{query: "terraform", want: "bodies"},     // body-only match
		{query: "ORCHESTRATION", want: "agents"}, // case-insensitive
	}
	for _, tc := range cases {
		got := searchSlugs(index, tc.query)
		if len(got) == 0 || got[0] != tc.want {
			t.Errorf("search(%q) = %v, want %q first", tc.query, got, tc.want)
		}
	}
}

func TestSearchIgnoresEmptyAndUnknownQueries(t *testing.T) {
	index := newSearchIndex([]templates.Article{
		searchArticle("only", "Title", "Description", "Body", "Agent"),
	})

	for _, query := range []string{"", "   ", "!!!", "zzzznotaword"} {
		if got := index.Search(query); len(got) != 0 {
			t.Errorf("search(%q) = %v, want no results", query, got)
		}
	}
}

func TestNormalizeSearchQueryTrimsAndCaps(t *testing.T) {
	if got := normalizeSearchQuery("  agents  "); got != "agents" {
		t.Errorf("normalized query = %q, want %q", got, "agents")
	}
	// The cap counts runes: a multi-byte query must not be cut mid-character.
	long := strings.Repeat("é", searchQueryLimit+50)
	got := normalizeSearchQuery(long)
	if runes := []rune(got); len(runes) != searchQueryLimit {
		t.Errorf("capped query runes = %d, want %d", len(runes), searchQueryLimit)
	}
	if !strings.ContainsRune(got, 'é') || strings.ContainsRune(got, '�') {
		t.Errorf("capped query is not valid UTF-8: %q", got)
	}
}

// TestArticleIndexDataComposesSearchAndTag proves the two filters narrow the
// same list: a tag chip clicked during a search must not silently widen it back.
func TestArticleIndexDataComposesSearchAndTag(t *testing.T) {
	articles := []templates.Article{
		searchArticle("agent-cloud", "Agents on Cloud Run", "Deploying agents", "Body.", "Agent", "Cloud"),
		searchArticle("agent-python", "Agents in Python", "Writing agents", "Body.", "Agent", "Python"),
	}
	index := newSearchIndex(articles)

	view := articleIndexData(articles, index, "", "agents")
	if !view.Searching() || len(view.Results) != 2 {
		t.Fatalf("search results = %d, want 2 (searching=%v)", len(view.Results), view.Searching())
	}
	if len(view.Years) != 0 {
		t.Error("a search view must not also render the year-grouped archive")
	}

	filtered := articleIndexData(articles, index, "python", "agents")
	if len(filtered.Results) != 1 || filtered.Results[0].Slug != "agent-python" {
		t.Errorf("tag-filtered search results = %v, want [agent-python]", filtered.Results)
	}
	if filtered.ActiveTag != "Python" {
		t.Errorf("active tag = %q, want %q", filtered.ActiveTag, "Python")
	}
}
