package templates

import (
	"strings"
	"time"
)

// CardCoverWidth is the derivative article cards load, by name. Cards paint it
// at ~378-683 CSS px, and it doubles as the smallest candidate in every body
// figure's srcset.
const CardCoverWidth = 800

// DerivativeWidths is the responsive ladder generated for every article image
// and offered to the browser, smallest first. Two rungs rather than one,
// because the source is now a ~2.4MP original: a 390 CSS px phone at DPR 3
// resolves 1170px, and with only an 800px rung below it the browser correctly
// but expensively reaches past it for the full-resolution source. 1280 covers
// that case and is also the exact width a DPR 1 desktop figure renders at.
//
// Widths above a source are skipped rather than upscaled, so a small archive
// image simply ships fewer rungs.
var DerivativeWidths = []int{CardCoverWidth, 1280}

// Data Models

type SocialLink struct {
	Name   string `json:"name"`
	URL    string `json:"url"`
	Icon   string `json:"icon"`
	Header bool   `json:"header"`
}

type LeadershipRole struct {
	Role         string `json:"role"`
	Organization string `json:"organization"`
	Description  string `json:"description"`
	URL          string `json:"url"`
}

type Metadata struct {
	Name          string `json:"name"`
	AlternateName string `json:"alternate_name"`
	// SiteName is the brand shown in the header, social cards, and structured
	// data. The domain is where the site lives, not what it is called.
	SiteName          string       `json:"site_name"`
	Title             string       `json:"title"`
	JobTitle          string       `json:"job_title"`
	HeadlinePrimary   string       `json:"headline_primary"`
	HeadlineSecondary string       `json:"headline_secondary"`
	Description       string       `json:"description"`
	Keywords          []string     `json:"keywords"`
	Email             string       `json:"email"`
	CalendarURL       string       `json:"calendar_url"`
	SiteURL           string       `json:"site_url"`
	TwitterHandle     string       `json:"twitter_handle"`
	Socials           []SocialLink `json:"socials"`
}

type CertificationBadge struct {
	URL    string `json:"url"`
	Logo   string `json:"logo"`
	Title  string `json:"title"`
	Issuer string `json:"issuer"`
	CertID string `json:"cert_id"`
	Active bool   `json:"active"`
}

type CertificationEntry struct {
	URL           string `json:"url"`
	Logo          string `json:"logo"`
	Title         string `json:"title"`
	IssuerDetails string `json:"issuer_details"`
}

type WorkExperience struct {
	Company     string   `json:"company"`
	Logo        string   `json:"logo"`
	Title       string   `json:"title"`
	BrandColor  string   `json:"brand_color"`
	Description string   `json:"description"`
	Tags        []string `json:"tags"`
}

type Project struct {
	Title       string `json:"title"`
	Href        string `json:"href"`
	Repo        string `json:"repo,omitzero"`
	Description string `json:"description"`
}

type Playlist struct {
	Title       string `json:"title"`
	URL         string `json:"url"`
	Description string `json:"description"`
	CTA         string `json:"cta"`
}

type ThesisLink struct {
	Label string `json:"label"`
	URL   string `json:"url"`
}

type Thesis struct {
	Title              string       `json:"title"`
	URL                string       `json:"url"`
	InstitutionDetails string       `json:"institution_details"`
	Description        string       `json:"description"`
	Links              []ThesisLink `json:"links"`
}

type ResearchPaper struct {
	Title     string `json:"title"`
	URL       string `json:"url"`
	Venue     string `json:"venue"`
	Code      string `json:"code"`
	CodeLabel string `json:"code_label"`
}

// Article is one validated Markdown publication plus its pre-rendered safe HTML.
// Runtime handlers only read this immutable startup snapshot.
type Article struct {
	Date        time.Time `json:"date"`
	Updated     time.Time `json:"updated"`
	Markdown    string    `json:"content"`
	Description string    `json:"description"`
	Title       string    `json:"title"`
	Slug        string    `json:"slug"`
	Canonical   string    `json:"canonical,omitzero"`
	// Syndicated records a copy published elsewhere (Medium, DEV). It is
	// provenance only: this site is the canonical home of every article.
	Syndicated string `json:"syndicated,omitzero"`
	HTML       string `json:"-"`
	URL        string `json:"url"`
	ImageURL   string `json:"image_url"`
	// CardImageURL is the downscaled cover teasers load. Feeds, social metadata,
	// and JSON-LD keep ImageURL so external consumers still get the full asset.
	CardImageURL string `json:"-"`
	// CoverSrcset and CoverSizes are the rendered cover's responsive candidates.
	// The <head> preload reuses them so the preload scanner resolves to the same
	// file the layout paints instead of fetching the full-size cover alongside it.
	CoverSrcset    string   `json:"-"`
	CoverSizes     string   `json:"-"`
	ImageAlt       string   `json:"image_alt"`
	Tags           []string `json:"tags"`
	ReadingMinutes int      `json:"reading_minutes"`
	Draft          bool     `json:"draft"`
}

// ArticleSummary is the compact publication representation exposed through
// lists, JSON, llms.txt, and MCP so discovery does not duplicate full bodies.
type ArticleSummary struct {
	Date           time.Time `json:"date"`
	Updated        time.Time `json:"updated"`
	Title          string    `json:"title"`
	Description    string    `json:"description"`
	Slug           string    `json:"slug"`
	Canonical      string    `json:"canonical,omitzero"`
	Syndicated     string    `json:"syndicated,omitzero"`
	URL            string    `json:"url"`
	ImageURL       string    `json:"image_url"`
	ImageAlt       string    `json:"image_alt"`
	Tags           []string  `json:"tags"`
	ReadingMinutes int       `json:"reading_minutes"`
}

func (article Article) Summary() ArticleSummary {
	return ArticleSummary{
		Title:          article.Title,
		Description:    article.Description,
		Date:           article.Date,
		Updated:        article.Updated,
		Tags:           article.Tags,
		Slug:           article.Slug,
		Canonical:      article.Canonical,
		Syndicated:     article.Syndicated,
		URL:            article.URL,
		ImageURL:       article.ImageURL,
		ImageAlt:       article.ImageAlt,
		ReadingMinutes: article.ReadingMinutes,
	}
}

// ImagePath returns the same-origin asset path used by rendered HTML. ImageURL
// stays absolute for feeds, JSON-LD, social metadata, JSON, and MCP clients.
func (article Article) ImagePath() string {
	return strings.TrimPrefix(article.ImageURL, METADATA.SiteURL)
}

// CardImagePath is the same-origin path of the teaser-sized cover. Cards never
// render wider than ~700 CSS px in any breakpoint, so one derivative covers every
// layout at 2× density and no srcset is warranted.
func (article Article) CardImagePath() string {
	return strings.TrimPrefix(article.CardImageURL, METADATA.SiteURL)
}

// MarkdownPath is the same-origin path of an article's raw Markdown source, and
// MarkdownURL its absolute form for machine-readable surfaces.
func (article Article) MarkdownPath() string {
	return "/articles/" + article.Slug + ".md"
}

func (article Article) MarkdownURL() string {
	return METADATA.SiteURL + article.MarkdownPath()
}

// CanonicalURL returns the externally declared canonical when present and the
// hosted article URL otherwise.
func (article Article) CanonicalURL() string {
	if article.Canonical != "" {
		return article.Canonical
	}
	return article.URL
}

// ModifiedDate falls back to publication for articles without updated
// frontmatter and for compact fixtures that only set Date.
func (article Article) ModifiedDate() time.Time {
	if article.Updated.IsZero() {
		return article.Date
	}
	return article.Updated
}

// ArticleYear groups the reverse-chronological index without client-side state.
type ArticleYear struct {
	Articles []Article
	Year     int
}

// ArticleIndexView is one render of the article index. The archive is grouped by
// year; a search replaces those groups with a single relevance-ranked list,
// because ordering by date would throw away the ranking the reader asked for.
type ArticleIndexView struct {
	Query     string
	ActiveTag string
	Tags      []string
	Years     []ArticleYear
	Results   []Article
}

// Searching reports whether this view renders ranked results instead of the
// year-grouped archive.
func (view ArticleIndexView) Searching() bool { return view.Query != "" }

// PageMetadata drives one shared document head for home, article, and error pages.
type PageMetadata struct {
	Article     *Article
	Title       string
	Description string
	Canonical   string
	ImageURL    string
	ImageAlt    string
	Kind        string
	// StructuredData is precomputed during application construction so rendering
	// cannot hide a JSON encoding error behind an already-started response.
	StructuredData string
	// PreloadImage is the same-origin path of this page's Largest Contentful Paint
	// image, preloaded in <head> so the browser starts it before parsing the body.
	PreloadImage string
	// PreloadImageSrcset and PreloadImageSizes mirror the candidates on the image
	// the page actually renders. When the LCP image is responsive they must be set,
	// or the preload names one candidate while the layout paints another and the
	// browser downloads both.
	PreloadImageSrcset string
	PreloadImageSizes  string
	NoIndex            bool
	IsHome             bool
	InstantScroll      bool
}

type Service struct {
	Icon        string `json:"icon"`
	Title       string `json:"title"`
	Description string `json:"description"`
	Badge       string `json:"badge"`
	BadgeType   string `json:"badge_type"`
	CTAText     string `json:"cta_text"`
	CTAURL      string `json:"cta_url"`
}

type ExpertiseCard struct {
	Title       string `json:"title"`
	Emoji       string `json:"emoji"`
	Description string `json:"description"`
}
