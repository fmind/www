package site

import (
	"bytes"
	"fmt"
	"image"
	"image/png"
	"io/fs"
	"path"
	"regexp"
	"strings"
	"testing"
	"testing/fstest"
	"time"

	"github.com/yuin/goldmark/ast"
	"github.com/yuin/goldmark/text"

	"github.com/fmind/www/templates"
)

// The Medium import is frozen, so its size and shape are asserted exactly. The
// import is identified by its `syndicated` URL, which records where a copy also
// lives; this site is canonical for every article it publishes. Articles authored
// natively are additive and ship a cover the template renders rather than the body,
// so the archive invariants below are scoped to the imported subset.
const (
	mediumArchiveArticles = 57
	mediumArchiveImages   = 295
)

func TestLoadArticlesValidatesImportedArchive(t *testing.T) {
	collection, err := loadArticles()
	if err != nil {
		t.Fatalf("load articles: %v", err)
	}

	archive := make([]templates.Article, 0, len(collection.all))
	for _, article := range collection.all {
		if isMediumURL(article.Syndicated) {
			archive = append(archive, article)
		}
	}
	if len(archive) != mediumArchiveArticles {
		t.Fatalf("imported archive articles = %d, want %d", len(archive), mediumArchiveArticles)
	}
	if archive[0].Slug != "mcp-2026-07-28-stateless-core-enterprise-authorization-and-sdk-betas" {
		t.Errorf("newest archive article = %q", archive[0].Slug)
	}

	imagePattern := regexp.MustCompile(`\]\((/static/img/articles/[^)[:space:]]+)`)
	archiveImages := make(map[string]bool)
	archiveSlugs := make(map[string]bool, len(archive))
	syndications := make(map[string]bool, len(archive))
	for _, article := range archive {
		archiveSlugs[article.Slug] = true
		if syndications[article.Syndicated] {
			t.Errorf("%s duplicates syndicated URL %q", article.Slug, article.Syndicated)
		}
		syndications[article.Syndicated] = true
		if strings.Contains(article.Markdown, "medium.com/max/") || strings.Contains(article.Markdown, "cdn-images-") {
			t.Errorf("%s still references a Medium image CDN", article.Slug)
		}
		for _, match := range imagePattern.FindAllStringSubmatch(article.Markdown, -1) {
			archiveImages[strings.TrimPrefix(match[1], "/")] = true
		}
	}

	// Rendering and draft state hold for every article, imported or native.
	for _, article := range collection.all {
		if article.Draft {
			t.Errorf("published article %s is unexpectedly a draft", article.Slug)
		}
		if strings.TrimSpace(article.HTML) == "" || article.ReadingMinutes < 1 {
			t.Errorf("%s did not render usable content", article.Slug)
		}
		if strings.Contains(article.HTML, "<script") || strings.Contains(article.HTML, "<style") {
			t.Errorf("%s rendered raw HTML", article.Slug)
		}
		// Reclaimed SEO: this site is canonical for its whole archive. A syndicated
		// copy is recorded as provenance and must never hand ranking away again.
		if article.Canonical != "" {
			t.Errorf("%s declares an external canonical %q", article.Slug, article.Canonical)
		}
		// Syndication is deliberately not asserted here: a natively published
		// article reaches the site weeks before a Medium copy exists, if one ever
		// does. The frozen count above is what guards the imported subset, so the
		// first native publication adds an article instead of turning the suite red.
	}

	if len(archiveImages) != mediumArchiveImages {
		t.Errorf("unique archive image references = %d, want %d", len(archiveImages), mediumArchiveImages)
	}
	for image := range archiveImages {
		if _, err := fs.Stat(staticFS, image); err != nil {
			t.Errorf("image reference %q: %v", image, err)
		}
	}
	// Derivatives are generated from the sources and referenced by templates or
	// by a srcset rather than by an article body, so they are counted separately:
	// what the bodies reference must be exactly the set of sources on disk, with
	// no orphan file and no reference to a file that is not there.
	cardCover := fmt.Sprintf("cover-%d.webp", templates.CardCoverWidth)
	isDerivative := func(name string) bool {
		for _, width := range templates.DerivativeWidths {
			if strings.HasSuffix(name, fmt.Sprintf("-%d.webp", width)) {
				return true
			}
		}
		return false
	}
	sources, derivatives, cardCovers := 0, 0, 0
	if err := fs.WalkDir(staticFS, "static/img/articles", func(name string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.IsDir() || !archiveSlugs[articleImageSlug(name)] {
			return nil
		}
		switch {
		case entry.Name() == cardCover:
			cardCovers++
		case isDerivative(entry.Name()):
			derivatives++
		default:
			sources++
		}
		return nil
	}); err != nil {
		t.Fatalf("walk article images: %v", err)
	}
	if cardCovers != len(archive) {
		t.Errorf("generated card covers = %d, want one per article (%d)", cardCovers, len(archive))
	}
	if sources != len(archiveImages) {
		t.Errorf("archive image sources = %d, references = %d", sources, len(archiveImages))
	}

	// Every ladder rung a source is wide enough to earn must exist on disk. A
	// missing rung is silent: bodySourceSet simply omits that candidate, and the
	// phone that needed it downloads the full-resolution diagram instead.
	for image := range archiveImages {
		config, err := imageConfig(staticFS, image)
		if err != nil {
			continue // Videos and other non-decodable references are checked above.
		}
		stem := strings.TrimSuffix(image, path.Ext(image))
		for _, width := range templates.DerivativeWidths {
			if width >= config.Width {
				continue
			}
			rung := fmt.Sprintf("%s-%d.webp", stem, width)
			if _, err := fs.Stat(staticFS, rung); err != nil {
				t.Errorf("source %q is %dpx wide but has no %dpx rung: run `mise run build:images`", image, config.Width, width)
			}
		}
	}
	if derivatives == 0 {
		t.Error("no body-figure derivatives were generated at all")
	}
}

// exampleAssets is the minimal asset set a fixture article needs: an original
// cover in the given format, the generated card derivative, and one decodable
// figure a body can reference.
func exampleAssets(t *testing.T, extension string) fstest.MapFS {
	t.Helper()
	return fstest.MapFS{
		"static/img/articles/example/cover" + extension:                                    {Data: []byte("image")},
		fmt.Sprintf("static/img/articles/example/cover-%d.webp", templates.CardCoverWidth): {Data: []byte("image")},
		"static/img/articles/example/figure.png":                                           {Data: examplePNG(t)},
	}
}

// examplePNG encodes a real image so the renderer can read intrinsic dimensions;
// the 4x3 shape makes a transposed width/height obvious in an assertion.
func examplePNG(t *testing.T) []byte {
	t.Helper()
	var encoded bytes.Buffer
	if err := png.Encode(&encoded, image.NewRGBA(image.Rect(0, 0, 4, 3))); err != nil {
		t.Fatalf("encode example png: %v", err)
	}
	return encoded.Bytes()
}

func isMediumURL(canonical string) bool {
	return strings.HasPrefix(canonical, "https://medium.com/@fmind/") ||
		strings.HasPrefix(canonical, "https://fmind.medium.com/")
}

// articleImageSlug maps static/img/articles/<slug>/<file> back to <slug>.
func articleImageSlug(name string) string {
	rest, ok := strings.CutPrefix(name, "static/img/articles/")
	if !ok {
		return ""
	}
	slug, _, _ := strings.Cut(rest, "/")
	return slug
}

func TestParseArticleRejectsUnknownFrontmatterWithLine(t *testing.T) {
	data := []byte(`+++
title = "Example"
description = "Example article"
date = "2026-08-01"
tags = ["Agent"]
slug = "example"
canonical = "https://fmind.medium.com/example-123"
draft = false
surprise = "not allowed"
+++

Body.
`)
	assets := exampleAssets(t, ".webp")
	_, err := parseArticle("content/articles/example.md", data, assets)
	if err == nil {
		t.Fatal("unknown frontmatter key should fail")
	}
	if message := err.Error(); !strings.Contains(message, "surprise") || !strings.Contains(message, "line 9") {
		t.Errorf("error = %q, want key and source line", message)
	}
}

func TestParseArticleRendersMarkdownWithoutRawHTML(t *testing.T) {
	data := []byte(`+++
title = "Example"
description = "Example article"
date = "2026-08-01"
tags = ["Agent"]
slug = "example"
draft = false
+++

## Heading

Text with ~~old~~ syntax and a footnote.[^1]

<script>alert("unsafe")</script>

[^1]: Detail.
`)
	assets := exampleAssets(t, ".png")
	article, err := parseArticle("content/articles/example.md", data, assets)
	if err != nil {
		t.Fatalf("parse article: %v", err)
	}
	for _, want := range []string{`id="heading"`, "<del>old</del>", "footnote"} {
		if !strings.Contains(article.HTML, want) {
			t.Errorf("rendered article missing %q: %s", want, article.HTML)
		}
	}
	if strings.Contains(article.HTML, "<script>") {
		t.Error("raw HTML was rendered")
	}
}

// TestParseArticleNormalizesHeadingsAndDefersImages covers the two rendering
// rules the page outline and image loading depend on: the body never emits a
// second <h1> or skips a level under the title, and the LCP image is eager.
func TestParseArticleNormalizesHeadingsAndDefersImages(t *testing.T) {
	frontmatter := `+++
title = "Example"
description = "Example article"
date = "2026-08-01"
tags = ["Agent"]
slug = "example"
draft = false
+++

`
	assets := exampleAssets(t, ".webp")

	cases := []struct {
		name string
		body string
		want []string
		deny []string
	}{
		{
			name: "imported bodies starting at h3 are promoted",
			body: "### Section\n\n#### Detail\n\n![figure](/static/img/articles/example/figure.png)\n",
			want: []string{"<h2 id=\"section\">", "<h3 id=\"detail\">", `<img fetchpriority="high" decoding="async" width="4" height="3"`},
			deny: []string{"<h1", "<h4", `loading="lazy"`},
		},
		{
			name: "bodies starting at h1 are demoted below the page title",
			body: "# Section\n\n## Detail\n",
			want: []string{"<h2 id=\"section\">", "<h3 id=\"detail\">"},
			deny: []string{"<h1"},
		},
		{
			name: "bodies already starting at h2 are left alone",
			body: "## Section\n\n### Detail\n",
			want: []string{"<h2 id=\"section\">", "<h3 id=\"detail\">"},
			deny: []string{"<h1", "<h4"},
		},
	}
	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			article, err := parseArticle("content/articles/example.md", []byte(frontmatter+testCase.body), assets)
			if err != nil {
				t.Fatalf("parse article: %v", err)
			}
			for _, want := range testCase.want {
				if !strings.Contains(article.HTML, want) {
					t.Errorf("rendered article missing %q: %s", want, article.HTML)
				}
			}
			for _, deny := range testCase.deny {
				if strings.Contains(article.HTML, deny) {
					t.Errorf("rendered article should not contain %q: %s", deny, article.HTML)
				}
			}
		})
	}
}

func TestEnhanceBodyImagesPrioritizesCoverAndDefersFigures(t *testing.T) {
	assets := fstest.MapFS{
		"static/img/articles/example/cover.webp":     {Data: sizedPNG(t, 1_200, 600)},
		"static/img/articles/example/cover-800.webp": {Data: []byte("derivative")},
		"static/img/articles/example/figure.png":     {Data: sizedPNG(t, 400, 300)},
	}
	body := `<p><img src="/static/img/articles/example/cover.webp" alt="cover"></p>` +
		`<p><img src="/static/img/articles/example/figure.png" alt="figure"></p>`

	got, _, err := enhanceBodyImages(body, assets)
	if err != nil {
		t.Fatalf("enhance images: %v", err)
	}
	for _, want := range []string{
		`<img fetchpriority="high" decoding="async" width="1200" height="600"`,
		`srcset="/static/img/articles/example/cover-800.webp 800w, /static/img/articles/example/cover.webp 1200w"`,
		`sizes="(max-width: 1312px) calc(100vw - 2rem), 1280px"`,
		`<img loading="lazy" decoding="async" width="400" height="300"`,
	} {
		if !strings.Contains(got, want) {
			t.Errorf("enhanced body missing %q: %s", want, got)
		}
	}
}

// A cover exported as PNG must still get the downscaled WebP candidate. `pub
// export` copies the reviewed diagrams/cover.png verbatim, so keying the srcset
// on the .webp filename made the next published article silently serve its
// full-size original as the mobile LCP image.
func TestEnhanceBodyImagesServesResponsiveCoverForEveryCoverFormat(t *testing.T) {
	for _, extension := range []string{"webp", "png", "jpg", "gif"} {
		t.Run(extension, func(t *testing.T) {
			cover := "static/img/articles/example/cover." + extension
			assets := fstest.MapFS{
				cover: {Data: sizedPNG(t, 1_200, 600)},
				"static/img/articles/example/cover-800.webp": {Data: []byte("derivative")},
			}
			body := `<p><img src="/` + cover + `" alt="cover"></p>`

			got, _, err := enhanceBodyImages(body, assets)
			if err != nil {
				t.Fatalf("enhance images: %v", err)
			}
			want := `srcset="/static/img/articles/example/cover-800.webp 800w, /` + cover + ` 1200w"`
			if !strings.Contains(got, want) {
				t.Errorf("enhanced body missing %q: %s", want, got)
			}
		})
	}
}

// Every body image wide enough to have been downscaled offers both candidates,
// not just the cover. Diagrams are the widest images an article ships and the
// ones a phone most needs the small candidate for.
func TestEnhanceBodyImagesServesResponsiveNonCoverFigures(t *testing.T) {
	assets := fstest.MapFS{
		"static/img/articles/example/architecture.webp":     {Data: sizedPNG(t, 4_368, 550)},
		"static/img/articles/example/architecture-800.webp": {Data: []byte("derivative")},
	}
	body := `<p><img src="/static/img/articles/example/architecture.webp" alt="architecture"></p>`

	got, _, err := enhanceBodyImages(body, assets)
	if err != nil {
		t.Fatalf("enhance images: %v", err)
	}
	want := `srcset="/static/img/articles/example/architecture-800.webp 800w, /static/img/articles/example/architecture.webp 4368w"`
	if !strings.Contains(got, want) {
		t.Errorf("enhanced body missing %q: %s", want, got)
	}
}

// The ladder is offered in full when it exists. Without the middle rung, a
// 390 CSS px phone at DPR 3 resolves 1170px, finds only an 800px candidate
// below that, and correctly but expensively reaches for the 2048px source.
func TestEnhanceBodyImagesOffersEveryLadderRung(t *testing.T) {
	assets := fstest.MapFS{
		"static/img/articles/example/02.webp":      {Data: sizedPNG(t, 2_074, 1_138)},
		"static/img/articles/example/02-800.webp":  {Data: []byte("small")},
		"static/img/articles/example/02-1280.webp": {Data: []byte("medium")},
	}
	body := `<p><img src="/static/img/articles/example/02.webp" alt="screenshot"></p>`

	got, _, err := enhanceBodyImages(body, assets)
	if err != nil {
		t.Fatalf("enhance images: %v", err)
	}
	want := `srcset="/static/img/articles/example/02-800.webp 800w, ` +
		`/static/img/articles/example/02-1280.webp 1280w, ` +
		`/static/img/articles/example/02.webp 2074w"`
	if !strings.Contains(got, want) {
		t.Errorf("enhanced body missing %q: %s", want, got)
	}
}

// A paragraph that repeats an illustration's alt text is that illustration's
// caption and belongs inside its figure; anything else is the next paragraph of
// the article and must survive untouched. The cover case is the one that matters
// most: every article opens with a cover image followed by its first paragraph,
// and a position-only rule would silently turn all of them into captions.
func TestFoldBodyCaptions(t *testing.T) {
	assets := fstest.MapFS{"static/img/articles/example/02.webp": {Data: sizedPNG(t, 1_200, 800)}}

	for name, testCase := range map[string]struct {
		alt, next   string
		wantCaption bool
	}{
		"caption repeats the alt": {
			alt:         "Relationship between Coding Agents and Agent Levers",
			next:        "Relationship between Coding Agents and Agent Levers",
			wantCaption: true,
		},
		// The Typographer spaces a rendered em dash with hair spaces the alt
		// attribute never sees, and the Medium import left non-breaking spaces
		// behind; neither changes what the caption says.
		"typographic spacing differs": {
			alt:         "Agent Lever: Multiply the force — https://example.com/levers",
			next:        "Agent Lever: Multiply the force — https://example.com/levers",
			wantCaption: true,
		},
		// The caption links a URL that the alt can only spell out.
		"caption links what the alt spells out": {
			alt:         "Agent Docs — https://example.com/agent-docs",
			next:        "Agent Docs — [https://example.com/agent-docs](https://example.com/agent-docs)",
			wantCaption: true,
		},
		"opening paragraph after a cover": {
			alt:         "Source: Gemini App",
			next:        "In 2026, AI agents have become incredibly smart, yet they are limited.",
			wantCaption: false,
		},
	} {
		t.Run(name, func(t *testing.T) {
			body := fmt.Sprintf("![%s](/static/img/articles/example/02.webp)\n\n%s\n", testCase.alt, testCase.next)
			var rendered bytes.Buffer
			if err := articleMarkdown.Convert([]byte(body), &rendered); err != nil {
				t.Fatalf("render markdown: %v", err)
			}
			got, _, err := enhanceBodyImages(rendered.String(), assets)
			if err != nil {
				t.Fatalf("enhance images: %v", err)
			}

			if strings.Contains(got, "<figcaption>") != testCase.wantCaption {
				t.Fatalf("figcaption present = %t, want %t: %s", !testCase.wantCaption, testCase.wantCaption, got)
			}
			if !testCase.wantCaption {
				return
			}
			if !strings.Contains(got, `alt=""`) {
				// The visible caption and the link's accessible name both carry the
				// description already; a third copy in alt is announced twice.
				t.Errorf("captioned image should drop its duplicate alt: %s", got)
			}
			if strings.Contains(got, "</figure>\n<p>") {
				t.Errorf("caption left outside its figure: %s", got)
			}
		})
	}
}

// Every body figure fits the article's width, whatever its aspect ratio: an
// illustration too wide to read when fitted is fixed at its source, never
// turned into something the reader has to pan. The regression this guards is a
// reintroduced per-image escape hatch — a marker attribute or a `sizes` that
// quotes anything other than the one figure layout.
func TestEnhanceBodyImagesFitsEveryAspectRatio(t *testing.T) {
	for name, dimensions := range map[string]struct{ width, height int }{
		"8:1 architecture diagram": {8968, 1129},
		"3:1 diagram":              {2400, 800},
		"16:9 screenshot":          {2073, 1138},
		"portrait":                 {938, 1215},
	} {
		t.Run(name, func(t *testing.T) {
			assets := fstest.MapFS{
				"static/img/articles/example/03.webp":      {Data: sizedPNG(t, dimensions.width, dimensions.height)},
				"static/img/articles/example/03-800.webp":  {Data: []byte("small")},
				"static/img/articles/example/03-1280.webp": {Data: []byte("medium")},
			}
			body := `<p><img src="/static/img/articles/example/03.webp" alt="architecture"></p>`

			got, _, err := enhanceBodyImages(body, assets)
			if err != nil {
				t.Fatalf("enhance images: %v", err)
			}
			if !strings.Contains(got, fmt.Sprintf(`sizes="%s"`, figureSizes)) {
				t.Errorf("enhanced body does not quote the figure layout: %s", got)
			}
			if strings.Contains(got, "data-wide") {
				t.Errorf("enhanced body marks an image for horizontal panning: %s", got)
			}
		})
	}
}

// A rung at or above the source width would be an upscale, so the generator
// never writes it and the renderer must not name it either — a srcset claiming
// a 1280w candidate that is really 1000px wide makes the browser pick badly.
func TestEnhanceBodyImagesSkipsRungsWiderThanTheSource(t *testing.T) {
	assets := fstest.MapFS{
		"static/img/articles/example/02.webp":     {Data: sizedPNG(t, 1_000, 600)},
		"static/img/articles/example/02-800.webp": {Data: []byte("small")},
	}
	body := `<p><img src="/static/img/articles/example/02.webp" alt="screenshot"></p>`

	got, _, err := enhanceBodyImages(body, assets)
	if err != nil {
		t.Fatalf("enhance images: %v", err)
	}
	if strings.Contains(got, "1280w") {
		t.Errorf("srcset named a rung wider than the source: %s", got)
	}
	want := `srcset="/static/img/articles/example/02-800.webp 800w, /static/img/articles/example/02.webp 1000w"`
	if !strings.Contains(got, want) {
		t.Errorf("enhanced body missing %q: %s", want, got)
	}
}

// A figure narrower than the derivative width has no second candidate on disk,
// and must not claim one: a srcset naming a missing file makes the browser fall
// back to `src` after a wasted request.
func TestEnhanceBodyImagesLeavesPhoneSizedFiguresUnscaled(t *testing.T) {
	assets := fstest.MapFS{
		"static/img/articles/example/chart.png": {Data: sizedPNG(t, 500, 300)},
	}
	body := `<p><img src="/static/img/articles/example/chart.png" alt="chart"></p>`

	got, _, err := enhanceBodyImages(body, assets)
	if err != nil {
		t.Fatalf("enhance images: %v", err)
	}
	if strings.Contains(got, "srcset") {
		t.Errorf("phone-sized figure should not gain a srcset: %s", got)
	}
}

// A standalone image is an illustration and becomes a breakout <figure> linked
// to its full resolution — the only way an 8:1 architecture diagram is readable.
// An image sharing its paragraph with prose is inline and must stay in the text
// column, or the breakout rule would drag the sentence around it off-measure.
func TestEnhanceBodyImagesWrapsStandaloneImagesOnly(t *testing.T) {
	assets := fstest.MapFS{
		"static/img/articles/example/diagram.png": {Data: sizedPNG(t, 400, 300)},
		"static/img/articles/example/icon.png":    {Data: sizedPNG(t, 16, 16)},
	}
	body := `<p><img src="/static/img/articles/example/diagram.png" alt="a &amp; b"></p>` +
		`<p>See <img src="/static/img/articles/example/icon.png" alt="icon"> inline.</p>`

	got, _, err := enhanceBodyImages(body, assets)
	if err != nil {
		t.Fatalf("enhance images: %v", err)
	}
	for _, want := range []string{
		`<figure><a href="/static/img/articles/example/diagram.png" target="_blank" rel="noopener"`,
		`aria-label="a &amp; b (opens the full-resolution image in a new tab)"`,
		`</a></figure>`,
		`<p>See <img loading="lazy" decoding="async" width="16" height="16" src="/static/img/articles/example/icon.png" alt="icon"> inline.</p>`,
	} {
		if !strings.Contains(got, want) {
			t.Errorf("enhanced body missing %q: %s", want, got)
		}
	}
	if strings.Count(got, "<figure>") != 1 {
		t.Errorf("only the standalone image should become a figure: %s", got)
	}
}

func TestEnhanceBodyImagesConvertsExplicitMP4ToVideo(t *testing.T) {
	body := `<p><img src="/static/img/articles/example/demo.mp4" alt="editor demo"></p>`
	got, _, err := enhanceBodyImages(body, fstest.MapFS{})
	if err != nil {
		t.Fatalf("enhance video: %v", err)
	}
	for _, want := range []string{"<video muted loop playsinline autoplay controls", `type="video/mp4"`, `aria-label="editor demo"`} {
		if !strings.Contains(got, want) {
			t.Errorf("enhanced video missing %q: %s", want, got)
		}
	}
}

func TestParseArticleUpdatedDate(t *testing.T) {
	data := []byte(`+++
title = "Example"
description = "Example article"
date = "2026-07-01"
updated = "2026-08-01"
tags = ["Agent"]
slug = "example"
draft = false
+++

Body.
`)
	article, err := parseArticle("content/articles/example.md", data, exampleAssets(t, ".webp"))
	if err != nil {
		t.Fatalf("parse updated article: %v", err)
	}
	if got := article.ModifiedDate().Format(time.DateOnly); got != "2026-08-01" {
		t.Errorf("modified date = %q, want 2026-08-01", got)
	}
}

func sizedPNG(t *testing.T, width, height int) []byte {
	t.Helper()
	var encoded bytes.Buffer
	if err := png.Encode(&encoded, image.NewRGBA(image.Rect(0, 0, width, height))); err != nil {
		t.Fatalf("encode %dx%d png: %v", width, height, err)
	}
	return encoded.Bytes()
}

func TestParseArticleRejectsTagsOutsideTheVocabulary(t *testing.T) {
	data := []byte(`+++
title = "Example"
description = "Example article"
date = "2026-08-01"
tags = ["Data Science"]
slug = "example"
draft = false
+++

Body.
`)
	assets := exampleAssets(t, ".webp")

	_, err := parseArticle("content/articles/example.md", data, assets)
	if err == nil {
		t.Fatal("a tag outside the canonical vocabulary should fail")
	}
	if message := err.Error(); !strings.Contains(message, "Data Science") || !strings.Contains(message, "Agent") {
		t.Errorf("error = %q, want the rejected tag and the allowed list", message)
	}
}

func TestVisibleArticlesExcludesDrafts(t *testing.T) {
	articles := []templates.Article{
		{Slug: "new", Date: time.Date(2026, 8, 1, 0, 0, 0, 0, time.UTC)},
		{Slug: "draft", Date: time.Date(2026, 7, 1, 0, 0, 0, 0, time.UTC), Draft: true},
	}
	if got := visibleArticles(articles, false); len(got) != 1 || got[0].Slug != "new" {
		t.Errorf("production visible articles = %#v", got)
	}
	if got := visibleArticles(articles, true); len(got) != 2 {
		t.Errorf("development visible articles = %d, want 2", len(got))
	}
}

// TestEveryTagIsUsed keeps the vocabulary lean: a tag nobody writes under is a
// dead entry plus a dead color rule, and it silently rots (the "Go" tag did).
// Tags exist to slice the archive, so one with no articles has no reason to ship.
func TestEveryTagIsUsed(t *testing.T) {
	collection, err := loadArticles()
	if err != nil {
		t.Fatalf("load articles: %v", err)
	}
	used := make(map[string]int, len(templates.TAGS))
	for _, article := range collection.all {
		for _, tag := range article.Tags {
			used[tag]++
		}
	}
	for _, tag := range templates.TAGS {
		if used[tag.Name] == 0 {
			t.Errorf("tag %q is in the vocabulary but tags no article", tag.Name)
		}
	}
}

// TestSiteIsCanonicalForEveryArticle pins the reclaimed SEO decision: this site
// owns the canonical URL of everything it publishes, so no article hands ranking
// to a syndicated copy and every public article reaches the sitemap. A canonical
// pointing back here is rejected too — the site treats a non-empty canonical as
// "belongs elsewhere" and would silently drop the article from the sitemap.
func TestSiteIsCanonicalForEveryArticle(t *testing.T) {
	collection, err := loadArticles()
	if err != nil {
		t.Fatalf("load articles: %v", err)
	}
	for _, article := range collection.all {
		if article.Canonical != "" {
			t.Errorf("%s declares canonical %q; this site is the canonical home", article.Slug, article.Canonical)
		}
		if got := article.CanonicalURL(); got != article.URL {
			t.Errorf("%s canonical URL = %q, want %q", article.Slug, got, article.URL)
		}
	}

	sitemap, err := renderSitemap(visibleArticles(collection.all, false))
	if err != nil {
		t.Fatalf("render sitemap: %v", err)
	}
	for _, article := range visibleArticles(collection.all, false) {
		if !strings.Contains(string(sitemap), "<loc>"+article.URL+"</loc>") {
			t.Errorf("sitemap is missing %s", article.Slug)
		}
	}
}

// TestArticleRejectsSelfCanonical proves the guard that makes the invariant above
// enforceable at parse time rather than by convention.
func TestArticleRejectsSelfCanonical(t *testing.T) {
	source := []byte(`+++
title = "Example"
description = "Example"
date = "2026-08-01"
slug = "example"
canonical = "https://www.fmind.dev/articles/example/"
tags = ["Agent"]
+++

Body.
`)
	if _, err := parseArticle("content/articles/example.md", source, exampleAssets(t, ".webp")); err == nil {
		t.Fatal("a canonical pointing at this site was accepted")
	} else if !strings.Contains(err.Error(), "canonical must not point at this site") {
		t.Errorf("unexpected error: %v", err)
	}
}

// TestEveryCodeBlockDeclaresALanguage keeps highlighting exact rather than
// inferred. The guesser in highlight.go is a fallback for content this site did
// not author; everything in content/articles/ states its own language, including
// an explicit "text" for trees, transcripts, and console output.
func TestEveryCodeBlockDeclaresALanguage(t *testing.T) {
	names, err := fs.Glob(articleFS, articleContentPattern)
	if err != nil {
		t.Fatalf("list articles: %v", err)
	}
	for _, name := range names {
		data, err := fs.ReadFile(articleFS, name)
		if err != nil {
			t.Fatalf("read %q: %v", name, err)
		}
		_, markdown, err := splitFrontmatter(data)
		if err != nil {
			t.Fatalf("parse %q: %v", name, err)
		}
		document := articleMarkdown.Parser().Parse(text.NewReader(markdown))
		_ = ast.Walk(document, func(node ast.Node, entering bool) (ast.WalkStatus, error) {
			if !entering {
				return ast.WalkContinue, nil
			}
			switch block := node.(type) {
			case *ast.CodeBlock:
				t.Errorf("%s: indented code block; fence it and declare a language", name)
			case *ast.FencedCodeBlock:
				if len(block.Language(markdown)) == 0 {
					t.Errorf("%s: fenced code block without a language", name)
				}
			}
			return ast.WalkContinue, nil
		})
	}
}
