"""Immutable view and publication models shared by every delivery surface."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

CARD_COVER_WIDTH = 800
DERIVATIVE_WIDTHS = (CARD_COVER_WIDTH, 1280)
_ZERO_DATE = datetime.min.replace(tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class SocialLink:
    name: str
    url: str
    icon: str
    header: bool = False


@dataclass(frozen=True, slots=True)
class LeadershipRole:
    role: str
    organization: str
    description: str
    url: str


@dataclass(frozen=True, slots=True)
class Metadata:
    name: str
    alternate_name: str
    site_name: str
    title: str
    job_title: str
    headline_primary: str
    headline_secondary: str
    description: str
    keywords: tuple[str, ...]
    email: str
    calendar_url: str
    site_url: str
    twitter_handle: str
    socials: tuple[SocialLink, ...]


@dataclass(frozen=True, slots=True)
class CertificationBadge:
    url: str
    logo: str
    title: str
    issuer: str
    cert_id: str
    active: bool


@dataclass(frozen=True, slots=True)
class CertificationEntry:
    url: str
    logo: str
    title: str
    issuer_details: str


@dataclass(frozen=True, slots=True)
class WorkExperience:
    company: str
    logo: str
    title: str
    brand_color: str
    description: str
    tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Project:
    title: str
    href: str
    description: str
    repo: str = ""


@dataclass(frozen=True, slots=True)
class Playlist:
    title: str
    url: str
    description: str
    cta: str


@dataclass(frozen=True, slots=True)
class ThesisLink:
    label: str
    url: str


@dataclass(frozen=True, slots=True)
class Thesis:
    title: str
    url: str
    institution_details: str
    description: str
    links: tuple[ThesisLink, ...]


@dataclass(frozen=True, slots=True)
class ResearchPaper:
    title: str
    url: str
    venue: str
    code: str
    code_label: str


@dataclass(frozen=True, slots=True)
class Article:
    """One validated Markdown publication and its safe startup-rendered HTML."""

    date: datetime = _ZERO_DATE
    updated: datetime | None = None
    markdown: str = ""
    description: str = ""
    title: str = ""
    slug: str = ""
    canonical: str = ""
    syndicated: str = ""
    html: str = ""
    url: str = ""
    image_url: str = ""
    card_image_url: str = ""
    cover_srcset: str = ""
    cover_sizes: str = ""
    image_alt: str = ""
    tags: tuple[str, ...] = ()
    reading_minutes: int = 0
    draft: bool = False

    def summary(self) -> ArticleSummary:
        return ArticleSummary(
            date=self.date,
            updated=self.updated or self.date,
            title=self.title,
            description=self.description,
            slug=self.slug,
            canonical=self.canonical,
            syndicated=self.syndicated,
            url=self.url,
            image_url=self.image_url,
            image_alt=self.image_alt,
            tags=self.tags,
            reading_minutes=self.reading_minutes,
        )

    def image_path(self) -> str:
        from www.data import METADATA

        return self.image_url.removeprefix(METADATA.site_url)

    def card_image_path(self) -> str:
        from www.data import METADATA

        return self.card_image_url.removeprefix(METADATA.site_url)

    def markdown_path(self) -> str:
        return f"/articles/{self.slug}.md"

    def markdown_url(self) -> str:
        from www.data import METADATA

        return METADATA.site_url + self.markdown_path()

    def canonical_url(self) -> str:
        return self.canonical or self.url

    def modified_date(self) -> datetime:
        return self.updated or self.date


@dataclass(frozen=True, slots=True, kw_only=True)
class ArticleSummary:
    date: datetime
    updated: datetime
    title: str
    description: str
    slug: str
    canonical: str = ""
    syndicated: str = ""
    url: str
    image_url: str
    image_alt: str
    tags: tuple[str, ...]
    reading_minutes: int


@dataclass(frozen=True, slots=True)
class ArticleYear:
    articles: tuple[Article, ...] = ()
    year: int = 0


@dataclass(frozen=True, slots=True)
class ArticleIndexView:
    query: str = ""
    active_tag: str = ""
    tags: tuple[str, ...] = ()
    years: tuple[ArticleYear, ...] = ()
    results: tuple[Article, ...] = ()

    def searching(self) -> bool:
        return bool(self.query)


@dataclass(frozen=True, slots=True)
class PageMetadata:
    article: Article | None = None
    title: str = ""
    description: str = ""
    canonical: str = ""
    image_url: str = ""
    image_alt: str = ""
    kind: str = ""
    structured_data: str = ""
    preload_image: str = ""
    preload_image_srcset: str = ""
    preload_image_sizes: str = ""
    no_index: bool = False
    is_home: bool = False
    instant_scroll: bool = False


@dataclass(frozen=True, slots=True)
class Service:
    icon: str
    title: str
    description: str
    badge: str
    badge_type: str
    cta_text: str
    cta_url: str


@dataclass(frozen=True, slots=True)
class ExpertiseCard:
    title: str
    emoji: str
    description: str


@dataclass(frozen=True, slots=True)
class Tag:
    name: str
    description: str


@dataclass(frozen=True, slots=True)
class SitePage:
    slug: str
    title: str
    description: str
    audience: str
    url: str
    article_slugs: tuple[str, ...] = field(default_factory=tuple, repr=False)

    def relates_to(self, slug: str) -> bool:
        return slug in self.article_slugs


@dataclass(frozen=True, slots=True)
class Portfolio:
    metadata: Metadata
    biography: tuple[str, ...]
    leadership: tuple[LeadershipRole, ...]
    expertise: tuple[ExpertiseCard, ...]
    experience: tuple[WorkExperience, ...]
    certifications: tuple[CertificationBadge, ...]
    specializations: tuple[CertificationEntry, ...]
    thesis: Thesis
    papers: tuple[ResearchPaper, ...]
    tags: tuple[Tag, ...]
    articles: tuple[ArticleSummary, ...]
    site_pages: tuple[SitePage, ...]
    open_source: tuple[Project, ...]
    youtube_series: tuple[Playlist, ...]
    services: tuple[Service, ...]
