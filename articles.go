package site

import (
	"bytes"
	"embed"
	"errors"
	"fmt"
	"html"
	"image"
	"unicode"

	// Registering the decoders lets image.DecodeConfig read the intrinsic size of
	// every format an article cover or figure can ship in.
	_ "image/gif"
	_ "image/jpeg"
	_ "image/png"
	"io/fs"
	"net/url"
	"path"
	"regexp"
	"slices"
	"strings"
	"time"

	_ "golang.org/x/image/webp"

	"github.com/pelletier/go-toml/v2"
	"github.com/yuin/goldmark"
	"github.com/yuin/goldmark/ast"
	"github.com/yuin/goldmark/extension"
	"github.com/yuin/goldmark/parser"
	"github.com/yuin/goldmark/renderer"
	"github.com/yuin/goldmark/text"
	"github.com/yuin/goldmark/util"

	"github.com/fmind/www/templates"
)

const (
	articleContentPattern = "content/articles/*.md"
	wordsPerMinute        = 200
)

var (
	//go:embed content/articles/*.md
	articleFS embed.FS

	articleSlugPattern = regexp.MustCompile(`^[a-z0-9]+(?:-[a-z0-9]+)*$`)
	// highlighter is built once and shared: it is stateless after construction and
	// only ever reads its formatter and style.
	highlighter, highlighterErr = newCodeHighlighter()
	bodyImagePattern            = regexp.MustCompile(`<img src="(/static/img/articles/[^"]+)"`)
	bodyVideoPattern            = regexp.MustCompile(`<img src="(/static/img/articles/[^"]+\.mp4)" alt="([^"]*)">`)
	// A body image alone in its paragraph is an illustration, not inline text, so
	// it becomes the <figure> the breakout layout widens. An image sharing a
	// paragraph with prose stays inline and keeps the text column's width.
	bodyFigurePattern = regexp.MustCompile(`<p>(<img src="(/static/img/articles/[^"]+)" alt="([^"]*)">)</p>`)
	// The imported articles caption an illustration by repeating its alt text in
	// the paragraph underneath. That paragraph is the caption, so it is folded
	// into the figure it belongs to — see foldBodyCaptions for why the match is
	// on the text rather than on position alone.
	bodyCaptionPattern = regexp.MustCompile(`(?s)<figure><a ([^>]*)><img src="([^"]+)" alt="([^"]*)"></a></figure>\s*<p>(.*?)</p>`)
	htmlTagPattern     = regexp.MustCompile(`<[^>]*>`)
	articleMarkdown    = goldmark.New(
		goldmark.WithExtensions(extension.GFM, extension.Footnote, extension.Typographer),
		goldmark.WithParserOptions(
			parser.WithAutoHeadingID(),
			parser.WithASTTransformers(util.Prioritized(headingNormalizer{}, 100)),
		),
		// Priority 1 beats goldmark's own code block renderers, so highlighted
		// markup is produced once at startup instead of by a script in the browser.
		goldmark.WithRendererOptions(renderer.WithNodeRenderers(util.Prioritized(highlighter, 1))),
	)
)

// headingNormalizer keeps a rendered body inside the page's heading outline. The
// article title is the page's only <h1>, so the shallowest heading in the body
// becomes <h2> and every deeper level shifts with it. Sources are inconsistent —
// some start at <h1>, most at <h3> — which otherwise skips levels and breaks the
// sequential outline screen readers navigate by.
type headingNormalizer struct{}

func (headingNormalizer) Transform(doc *ast.Document, _ text.Reader, _ parser.Context) {
	const noHeading = 7
	shallowest := noHeading
	walkHeadings(doc, func(heading *ast.Heading) {
		shallowest = min(shallowest, heading.Level)
	})
	if shallowest == noHeading || shallowest == 2 {
		return
	}
	shift := 2 - shallowest
	walkHeadings(doc, func(heading *ast.Heading) {
		heading.Level = min(6, heading.Level+shift)
	})
}

func walkHeadings(doc *ast.Document, visit func(*ast.Heading)) {
	// The walk only reads and mutates heading levels, so it cannot fail; goldmark
	// still returns an error to satisfy its generic callback signature.
	_ = ast.Walk(doc, func(node ast.Node, entering bool) (ast.WalkStatus, error) {
		if heading, ok := node.(*ast.Heading); ok && entering {
			visit(heading)
		}
		return ast.WalkContinue, nil
	})
}

type articleFrontmatter struct {
	Title       string   `toml:"title"`
	Description string   `toml:"description"`
	Date        string   `toml:"date"`
	Updated     string   `toml:"updated"`
	Slug        string   `toml:"slug"`
	Canonical   string   `toml:"canonical"`
	Syndicated  string   `toml:"syndicated"`
	Tags        []string `toml:"tags"`
	Draft       bool     `toml:"draft"`
}

type articleCollection struct {
	bySlug map[string]templates.Article
	all    []templates.Article
}

func loadArticles() (articleCollection, error) {
	if highlighterErr != nil {
		return articleCollection{}, fmt.Errorf("initialize code highlighter: %w", highlighterErr)
	}
	names, err := fs.Glob(articleFS, articleContentPattern)
	if err != nil {
		return articleCollection{}, fmt.Errorf("list embedded articles: %w", err)
	}
	if len(names) == 0 {
		return articleCollection{}, fmt.Errorf("list embedded articles: no files match %q", articleContentPattern)
	}

	collection := articleCollection{
		all:    make([]templates.Article, 0, len(names)),
		bySlug: make(map[string]templates.Article, len(names)),
	}
	for _, name := range names {
		data, err := fs.ReadFile(articleFS, name)
		if err != nil {
			return articleCollection{}, fmt.Errorf("read %q: %w", name, err)
		}
		article, err := parseArticle(name, data, staticFS)
		if err != nil {
			return articleCollection{}, err
		}
		if _, exists := collection.bySlug[article.Slug]; exists {
			return articleCollection{}, fmt.Errorf("parse %q: duplicate slug %q", name, article.Slug)
		}
		collection.all = append(collection.all, article)
		collection.bySlug[article.Slug] = article
	}

	slices.SortFunc(collection.all, func(a, b templates.Article) int {
		if order := b.Date.Compare(a.Date); order != 0 {
			return order
		}
		return strings.Compare(a.Slug, b.Slug)
	})
	return collection, nil
}

func parseArticle(name string, data []byte, assets fs.FS) (templates.Article, error) {
	header, markdown, err := splitFrontmatter(data)
	if err != nil {
		return templates.Article{}, fmt.Errorf("parse %q: %w", name, err)
	}

	var metadata articleFrontmatter
	decoder := toml.NewDecoder(bytes.NewReader(header)).DisallowUnknownFields()
	if decodeErr := decoder.Decode(&metadata); decodeErr != nil {
		return templates.Article{}, articleFrontmatterError(name, decodeErr)
	}
	if validationErr := validateArticleMetadata(name, metadata); validationErr != nil {
		return templates.Article{}, validationErr
	}

	published, err := time.Parse(time.DateOnly, metadata.Date)
	if err != nil {
		return templates.Article{}, fmt.Errorf("parse %q: date %q: %w", name, metadata.Date, err)
	}
	updated := published
	if metadata.Updated != "" {
		updated, err = time.Parse(time.DateOnly, metadata.Updated)
		if err != nil {
			return templates.Article{}, fmt.Errorf("parse %q: updated %q: %w", name, metadata.Updated, err)
		}
		if updated.Before(published) {
			return templates.Article{}, fmt.Errorf("parse %q: updated date must not precede publish date", name)
		}
	}
	imagePath, err := articleCover(assets, metadata.Slug)
	if err != nil {
		return templates.Article{}, fmt.Errorf("parse %q: %w", name, err)
	}
	cardImagePath, err := articleCardCover(assets, metadata.Slug)
	if err != nil {
		return templates.Article{}, fmt.Errorf("parse %q: %w", name, err)
	}

	var rendered bytes.Buffer
	if renderErr := articleMarkdown.Convert(markdown, &rendered); renderErr != nil {
		return templates.Article{}, fmt.Errorf("render %q: %w", name, renderErr)
	}
	body, lead, err := enhanceBodyImages(rendered.String(), assets)
	if err != nil {
		return templates.Article{}, fmt.Errorf("parse %q: %w", name, err)
	}
	words := len(strings.Fields(string(markdown)))
	readingMinutes := max(1, (words+wordsPerMinute-1)/wordsPerMinute)
	articleURL := templates.METADATA.SiteURL + "/articles/" + metadata.Slug + "/"

	return templates.Article{
		Title:          metadata.Title,
		Description:    metadata.Description,
		Date:           published.UTC(),
		Updated:        updated.UTC(),
		Tags:           metadata.Tags,
		Slug:           metadata.Slug,
		Canonical:      metadata.Canonical,
		Syndicated:     metadata.Syndicated,
		Draft:          metadata.Draft,
		URL:            articleURL,
		ImageURL:       templates.METADATA.SiteURL + "/" + imagePath,
		CardImageURL:   templates.METADATA.SiteURL + "/" + cardImagePath,
		CoverSrcset:    lead.srcset,
		CoverSizes:     lead.sizes,
		ImageAlt:       metadata.Title,
		ReadingMinutes: readingMinutes,
		Markdown:       string(markdown),
		HTML:           body,
	}, nil
}

// leadImage describes the first body image — the page's LCP element — so the
// <head> preload can name exactly the candidates the layout will paint.
type leadImage struct {
	srcset string
	sizes  string
}

// enhanceBodyImages gives every rendered body image what Markdown cannot express:
// intrinsic dimensions, so the layout reserves the space before the bytes arrive.
// The first image is prioritized as the page LCP element; later figures load
// lazily so a long article never fetches them ahead of its text. Raw HTML never
// survives rendering, so every <img> here comes from the renderer. It also reports
// the lead image's responsive candidates rather than having the caller decode the
// cover a second time to rediscover them.
func enhanceBodyImages(body string, assets fs.FS) (string, leadImage, error) {
	// A Markdown image whose source is MP4 is the repository's explicit, safe video
	// syntax. Raw HTML stays disabled, so imported content cannot inject elements.
	body = bodyVideoPattern.ReplaceAllString(body, `<video muted loop playsinline autoplay controls aria-label="$2"><source src="$1" type="video/mp4">Your browser does not support embedded video.</video>`)
	// Wrap first, enhance second: the enhancement pass rewrites every <img> it
	// finds, including the ones now nested in a figure's link. The link is the
	// escape hatch for detail the figure's width cannot show — a dense diagram
	// still rewards opening at full resolution. The alt text carries into the
	// link's accessible name so the affordance is not sighted-only.
	body = bodyFigurePattern.ReplaceAllString(
		body,
		`<figure><a href="${2}" target="_blank" rel="noopener" aria-label="${3} (opens the full-resolution image in a new tab)">${1}</a></figure>`,
	)
	body = foldBodyCaptions(body)
	matches := bodyImagePattern.FindAllStringSubmatchIndex(body, -1)
	if len(matches) == 0 {
		return body, leadImage{}, nil
	}

	var lead leadImage
	var enhanced strings.Builder
	end := 0
	for index, match := range matches {
		source := body[match[2]:match[3]]
		config, err := imageConfig(assets, strings.TrimPrefix(source, "/"))
		if err != nil {
			return "", leadImage{}, err
		}
		enhanced.WriteString(body[end:match[0]])
		loading := ` loading="lazy"`
		priority := ""
		srcset, sizes := bodySourceSet(assets, source, config.Width)
		if index == 0 {
			loading = ""
			priority = ` fetchpriority="high"`
			lead = leadImage{srcset: srcset, sizes: sizes}
		}
		responsive := ""
		if srcset != "" {
			responsive = fmt.Sprintf(` srcset="%s" sizes="%s"`, srcset, sizes)
		}
		fmt.Fprintf(
			&enhanced,
			`<img%s%s decoding="async" width="%d" height="%d"%s src="%s"`,
			loading, priority, config.Width, config.Height, responsive, source,
		)
		end = match[1]
	}
	enhanced.WriteString(body[end:])
	return enhanced.String(), lead, nil
}

// foldBodyCaptions moves an illustration's caption inside the figure it
// describes, so it is presented as that figure's caption rather than as the
// next paragraph of the article.
//
// The imported articles write a caption by repeating the image's alt text in
// the paragraph below it, and that repetition is the only reliable signal
// available: position alone would also swallow the opening paragraph of every
// article that leads with a cover image. So a paragraph is a caption when it
// says the same thing as the alt, and stays prose when it does not — 250 of the
// archive's 288 illustrations qualify, and none of the leading paragraphs do.
//
// The two are compared as text, not as markup, because Markdown rendering makes
// them differ in ways that carry no meaning: the caption may link a URL the alt
// spells out, and the Typographer replaces the plain spaces of an alt attribute
// with the hair and non-breaking spaces of rendered prose.
func foldBodyCaptions(body string) string {
	return bodyCaptionPattern.ReplaceAllStringFunc(body, func(match string) string {
		groups := bodyCaptionPattern.FindStringSubmatch(match)
		link, source, alt, caption := groups[1], groups[2], groups[3], groups[4]
		if captionText(caption) != captionText(alt) || captionText(alt) == "" {
			return match
		}
		// The caption now states the description on screen and the link still
		// carries it as an accessible name, so repeating it a third time in alt
		// would only make a screen reader announce the same sentence twice.
		return fmt.Sprintf(
			`<figure><a %s><img src="%s" alt=""></a><figcaption>%s</figcaption></figure>`,
			link, source, caption,
		)
	})
}

// captionText reduces rendered markup and an alt attribute to the words they
// have in common, so the two can be compared for sameness of meaning.
func captionText(fragment string) string {
	text := html.UnescapeString(htmlTagPattern.ReplaceAllString(fragment, ""))
	return strings.Join(strings.FieldsFunc(text, isCaptionSpace), " ")
}

// isCaptionSpace treats the typographic spaces of rendered prose as ordinary
// separators. unicode.IsSpace does not: it reports false for the non-breaking
// space the Medium import left behind and for the hair space the Typographer
// puts either side of an em dash, and either one would make a caption differ
// from the alt text it repeats word for word.
func isCaptionSpace(r rune) bool {
	switch r {
	case '\u00a0', '\u2009', '\u200a', '\u202f', '\ufeff':
		return true
	}
	return unicode.IsSpace(r)
}

// figureSizes describes a rendered body figure's layout width at every
// breakpoint, and must stay in step with the breakout rule in input.css: the
// figure is the article's padded width (viewport minus the 1rem gutter on each
// side) until that reaches --figure-max-width, 1280px. The <img> and its <head>
// preload must quote this identically, or the preload scanner resolves the
// srcset against a different width than the layout does.
//
// Every figure fits that width; none pans horizontally. An illustration too
// wide to stay legible when fitted is a diagram laid out wrong at its source,
// and it is fixed there — the private diagram sources carry a layout engine
// chosen to keep them near 2:1. A viewer who still wants more
// detail has the figure's full-resolution link.
const figureSizes = "(max-width: 1312px) calc(100vw - 2rem), 1280px"

// bodySourceSet returns the responsive candidates for a body image, shared by
// the rendered <img> and the preload in <head>. Returning the pair rather than
// formatted markup is what keeps the two in step: a preload that names the
// full-size source while the srcset paints the 800px derivative makes every
// phone download the image twice.
//
// The candidates are discovered from disk rather than declared, so an image
// offers exactly the rungs `mise run build:images` had a reason to write. A
// source narrower than every rung is already phone-sized and ships as its own
// single candidate, with no srcset at all.
func bodySourceSet(assets fs.FS, source string, sourceWidth int) (string, string) {
	// Resolve derivatives by stem, not by full filename: a source may be any of
	// .webp/.gif/.png/.jpg — `pub export` re-encodes what it ships to WebP, but
	// the archive still carries an imported GIF — and a derivative is always WebP.
	name := path.Base(source)
	stem := strings.TrimSuffix(name, path.Ext(name))
	candidates := make([]string, 0, len(templates.DerivativeWidths)+1)
	for _, width := range templates.DerivativeWidths {
		if width >= sourceWidth {
			continue
		}
		derivative := path.Join(path.Dir(source), fmt.Sprintf("%s-%d.webp", stem, width))
		if _, err := fs.Stat(assets, strings.TrimPrefix(derivative, "/")); err != nil {
			continue
		}
		candidates = append(candidates, fmt.Sprintf("%s %dw", derivative, width))
	}
	if len(candidates) == 0 {
		return "", ""
	}
	candidates = append(candidates, fmt.Sprintf("%s %dw", source, sourceWidth))
	return strings.Join(candidates, ", "), figureSizes
}

// imageConfig reads an embedded image's header for its intrinsic dimensions.
func imageConfig(assets fs.FS, name string) (image.Config, error) {
	file, err := assets.Open(name)
	if err != nil {
		return image.Config{}, fmt.Errorf("open body image %q: %w", name, err)
	}
	defer func() { _ = file.Close() }()

	config, _, err := image.DecodeConfig(file)
	if err != nil {
		return image.Config{}, fmt.Errorf("decode body image %q: %w", name, err)
	}
	return config, nil
}

func articleFrontmatterError(name string, err error) error {
	var strict *toml.StrictMissingError
	if errors.As(err, &strict) && len(strict.Errors) > 0 {
		unknown := strict.Errors[0]
		line, column := unknown.Position()
		return fmt.Errorf(
			"parse %q frontmatter: unknown key %q at line %d, column %d: %w",
			name,
			strings.Join(unknown.Key(), "."),
			line+1,
			column,
			err,
		)
	}

	var decode *toml.DecodeError
	if errors.As(err, &decode) {
		line, column := decode.Position()
		return fmt.Errorf("parse %q frontmatter at line %d, column %d: %w", name, line+1, column, err)
	}
	return fmt.Errorf("parse %q frontmatter: %w", name, err)
}

func splitFrontmatter(data []byte) ([]byte, []byte, error) {
	const delimiter = "+++"
	if !bytes.HasPrefix(data, []byte(delimiter+"\n")) {
		return nil, nil, fmt.Errorf("frontmatter must start with %q on line 1", delimiter)
	}
	remainder := data[len(delimiter)+1:]
	end := bytes.Index(remainder, []byte("\n"+delimiter+"\n"))
	if end < 0 {
		return nil, nil, fmt.Errorf("frontmatter opened on line 1 has no closing %q line", delimiter)
	}
	header := remainder[:end]
	markdown := bytes.TrimSpace(remainder[end+len(delimiter)+2:])
	if len(markdown) == 0 {
		return nil, nil, errors.New("article body is empty")
	}
	return header, markdown, nil
}

func validateArticleMetadata(name string, metadata articleFrontmatter) error {
	if metadata.Title == "" || metadata.Description == "" || metadata.Date == "" || metadata.Slug == "" {
		return fmt.Errorf("parse %q: title, description, date, and slug are required", name)
	}
	if !articleSlugPattern.MatchString(metadata.Slug) {
		return fmt.Errorf("parse %q: invalid slug %q", name, metadata.Slug)
	}
	if filename := strings.TrimSuffix(path.Base(name), path.Ext(name)); filename != metadata.Slug {
		return fmt.Errorf("parse %q: filename must match slug %q", name, metadata.Slug)
	}
	// canonical hands ranking to another site; syndicated only records where a
	// copy also lives. Both must be absolute HTTPS, and canonical must not point
	// back here — a self-canonical would silently drop the article from the sitemap.
	for field, value := range map[string]string{"canonical": metadata.Canonical, "syndicated": metadata.Syndicated} {
		if value == "" {
			continue
		}
		parsed, err := url.ParseRequestURI(value)
		if err != nil || parsed.Scheme != "https" || parsed.Host == "" {
			return fmt.Errorf("parse %q: %s must be an absolute HTTPS URL", name, field)
		}
		if field == "canonical" && strings.HasPrefix(value, templates.METADATA.SiteURL) {
			return fmt.Errorf("parse %q: canonical must not point at this site (omit it instead)", name)
		}
	}
	if len(metadata.Tags) == 0 {
		return fmt.Errorf("parse %q: at least one tag is required", name)
	}
	// The tag vocabulary is closed: an unknown label would silently add a chip to
	// the article filter and a color the stylesheet has no rule for, so it fails
	// the build here instead.
	for _, tag := range metadata.Tags {
		if !templates.IsTag(tag) {
			return fmt.Errorf("parse %q: unknown tag %q (allowed: %s)", name, tag, strings.Join(templates.TagNames(), ", "))
		}
	}
	return nil
}

func articleCover(assets fs.FS, slug string) (string, error) {
	directory := "static/img/articles/" + slug
	for _, extension := range []string{".webp", ".gif", ".png", ".jpg"} {
		name := directory + "/cover" + extension
		if _, err := fs.Stat(assets, name); err == nil {
			return name, nil
		}
	}
	return "", fmt.Errorf("missing article cover under %q", directory)
}

// articleCardCover resolves the downscaled cover that article cards load. It is
// generated by `mise run build:images` and committed alongside the original, so a
// missing derivative fails startup rather than silently pushing a full-width
// image into every card.
func articleCardCover(assets fs.FS, slug string) (string, error) {
	name := fmt.Sprintf("static/img/articles/%s/cover-%d.webp", slug, templates.CardCoverWidth)
	if _, err := fs.Stat(assets, name); err != nil {
		return "", fmt.Errorf("missing card cover %q: run `mise run build:images`", name)
	}
	return name, nil
}

func visibleArticles(articles []templates.Article, includeDrafts bool) []templates.Article {
	visible := make([]templates.Article, 0, len(articles))
	for _, article := range articles {
		if article.Draft && !includeDrafts {
			continue
		}
		visible = append(visible, article)
	}
	return visible
}

func articleSummaries(articles []templates.Article) []templates.ArticleSummary {
	summaries := make([]templates.ArticleSummary, len(articles))
	for i, article := range articles {
		summaries[i] = article.Summary()
	}
	return summaries
}
