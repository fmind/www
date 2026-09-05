package site

import (
	"math"
	"slices"
	"strings"
	"unicode"

	"github.com/fmind/www/templates"
)

// Okapi BM25 with its standard parameters. The archive is a few dozen long-form
// articles of similar length, so tuning beyond the defaults would be fitting
// noise. Everything is computed once at startup and read-only afterwards.
const (
	bm25K1 = 1.2
	bm25B  = 0.75

	// Field boosts. A term in the title or a tag says far more about what an
	// article is about than the same term buried three sections into the body.
	titleBoost       = 3
	tagBoost         = 3
	descriptionBoost = 2
	bodyBoost        = 1

	// searchQueryLimit caps the accepted query length in runes. Anything longer is
	// a scraper or a probe, not a reader, and is truncated rather than rejected.
	searchQueryLimit = 128

	// minimumPluralLength guards the naive plural fold below: shorter words are
	// left alone so "gcp" or "ops" never lose their last letter.
	minimumPluralLength = 4
)

// searchIndex is an immutable inverted-frequency index over one article
// collection, built once at startup and safe for concurrent reads. It owns the
// articles it indexes, so every caller ranks and resolves through one structure
// and cannot accidentally rank against a different visibility set.
type searchIndex struct {
	documentFrequency map[string]int
	articles          []templates.Article
	documents         []searchDocument
	averageLength     float64
}

type searchDocument struct {
	terms  map[string]int
	length int
}

// newSearchIndex indexes title, tags, description, and full Markdown body of
// every article, so a reader can find an article by a term that only ever
// appears in one of its paragraphs.
func newSearchIndex(articles []templates.Article) *searchIndex {
	index := &searchIndex{
		articles:          articles,
		documents:         make([]searchDocument, 0, len(articles)),
		documentFrequency: make(map[string]int),
	}
	total := 0
	for _, article := range articles {
		terms := make(map[string]int)
		countTerms(terms, article.Title, titleBoost)
		countTerms(terms, strings.Join(article.Tags, " "), tagBoost)
		countTerms(terms, article.Description, descriptionBoost)
		countTerms(terms, article.Markdown, bodyBoost)

		length := 0
		for term, count := range terms {
			length += count
			index.documentFrequency[term]++
		}
		index.documents = append(index.documents, searchDocument{terms: terms, length: length})
		total += length
	}
	if len(index.documents) > 0 {
		index.averageLength = float64(total) / float64(len(index.documents))
	}
	return index
}

// Search ranks the indexed articles by BM25 relevance, best first. It returns
// nothing for an empty query or one whose terms appear nowhere.
func (index *searchIndex) Search(query string) []templates.Article {
	terms := slices.Compact(slices.Sorted(slices.Values(tokenize(query))))
	if len(terms) == 0 || len(index.documents) == 0 {
		return nil
	}

	type hit struct {
		score    float64
		position int
	}
	hits := make([]hit, 0, len(index.documents))
	documentCount := float64(len(index.documents))
	for position, document := range index.documents {
		score := 0.0
		for _, term := range terms {
			frequency := float64(document.terms[term])
			if frequency == 0 {
				continue
			}
			// Standard BM25: inverse document frequency times a saturating,
			// length-normalized term frequency.
			matches := float64(index.documentFrequency[term])
			idf := math.Log(1 + (documentCount-matches+0.5)/(matches+0.5))
			norm := 1 - bm25B + bm25B*float64(document.length)/index.averageLength
			score += idf * (frequency * (bm25K1 + 1)) / (frequency + bm25K1*norm)
		}
		if score > 0 {
			hits = append(hits, hit{position: position, score: score})
		}
	}
	// documents keeps the collection's reverse-chronological order, so a stable
	// sort leaves recency as the tie-break between equally relevant articles.
	slices.SortStableFunc(hits, func(a, b hit) int {
		switch {
		case a.score > b.score:
			return -1
		case a.score < b.score:
			return 1
		default:
			return 0
		}
	})
	ranked := make([]templates.Article, len(hits))
	for i, hit := range hits {
		ranked[i] = index.articles[hit.position]
	}
	return ranked
}

func countTerms(terms map[string]int, text string, boost int) {
	for _, term := range tokenize(text) {
		terms[term] += boost
	}
}

// tokenize lowercases, splits on anything that is not a letter or a digit, and
// folds a trailing plural "s". The fold is deliberately naive: it is applied
// identically to documents and queries, so "agents" finds "agent" without a
// stemmer, a stopword list, or a language model in the request path.
func tokenize(text string) []string {
	fields := strings.FieldsFunc(strings.ToLower(text), func(r rune) bool {
		return !unicode.IsLetter(r) && !unicode.IsDigit(r)
	})
	terms := make([]string, 0, len(fields))
	for _, field := range fields {
		terms = append(terms, foldPlural(field))
	}
	return terms
}

func foldPlural(term string) string {
	if len(term) < minimumPluralLength || !strings.HasSuffix(term, "s") {
		return term
	}
	// "class" and "status" are not plurals; trimming them would merge unrelated
	// terms and drag irrelevant articles into the results.
	if strings.HasSuffix(term, "ss") || strings.HasSuffix(term, "us") {
		return term
	}
	return strings.TrimSuffix(term, "s")
}

// normalizeSearchQuery trims a raw query and caps its length at the boundary, so
// nothing downstream has to defend against an unbounded request parameter. The
// cap counts runes, never splitting a multi-byte character in half.
func normalizeSearchQuery(query string) string {
	query = strings.TrimSpace(query)
	if runes := []rune(query); len(runes) > searchQueryLimit {
		query = strings.TrimSpace(string(runes[:searchQueryLimit]))
	}
	return query
}
