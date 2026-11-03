"""The news preparation script, with every network read replaced by a fake."""

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from scripts import news

ARTICLE = (
    '<html><head><meta property="og:title" content="A &amp; B"><meta name="description" content=\'It "works".\'>'
    "<title>Ignored</title></head><body><nav><p>menu</p></nav><article>"
    + "<p>word </p>" * 100
    + "</article></body></html>"
)


class FakeWeb:
    """Answer known URLs, record every request, and fail like urllib on anything else."""

    def __init__(self, pages: Mapping[str, str | tuple[str, str]]) -> None:
        self.pages = pages
        self.requests: list[str] = []

    def __call__(self, url: str) -> tuple[str, str]:
        self.requests.append(url)
        if url not in self.pages:
            raise OSError(f"no route to {url}")
        page = self.pages[url]
        return page if isinstance(page, tuple) else (url, page)


def write_edition(directory: Path, slug: str, *urls: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    lines = (f"- Title {index}: {url} - About it." for index, url in enumerate(urls))
    (directory / f"{slug}.txt").write_text("\n".join(lines), encoding="utf-8")
    return directory


def test_prepare_skips_published_repeated_and_invalid_links(tmp_path: Path) -> None:
    directory = write_edition(tmp_path / "news", "2026-11-02", "https://example.com/old")
    write_edition(directory, "2026-11-03", "https://example.com/today")
    web = FakeWeb({"https://example.com/new": ARTICLE, "https://example.com/today": ARTICLE})

    results = news.prepare(
        [
            "https://example.com/old/?utm_source=mail",
            "https://example.com/new?fbclid=1",
            "https://example.com/new",
            "https://example.com/today",
            "ftp://example.com/file",
        ],
        "2026-11-03",
        directory,
        web,
    )

    by_status = [(result["status"], result["url"]) for result in results]
    assert by_status == [
        ("duplicate", "https://example.com/old"),
        ("duplicate", "https://example.com/new"),
        ("invalid", "ftp://example.com/file"),
        ("ok", "https://example.com/new"),
        ("ok", "https://example.com/today"),
    ]
    assert results[0]["edition"] == "2026-11-02"
    assert results[1]["edition"] == "this batch"
    assert "unsupported or invalid URL" in results[2]["error"]
    assert web.requests == ["https://example.com/new", "https://example.com/today"]


def test_prepare_resolves_shorteners_before_deduplicating(tmp_path: Path) -> None:
    directory = write_edition(tmp_path / "news", "2026-11-02", "https://example.com/old")
    web = FakeWeb({"https://bit.ly/abc": ("https://example.com/old?utm_campaign=x", "")})

    [result] = news.prepare(["https://bit.ly/abc"], "2026-11-03", directory, web)

    assert result == {"status": "duplicate", "url": "https://example.com/old", "edition": "2026-11-02"}


def test_prepare_reports_unreachable_shorteners_as_invalid(tmp_path: Path) -> None:
    [result] = news.prepare(["https://t.co/gone"], "2026-11-03", tmp_path, FakeWeb({}))

    assert result["status"] == "invalid"
    assert result["error"] == "OSError: no route to https://t.co/gone"


def test_page_facts_read_open_graph_and_body_length() -> None:
    facts = news.source_facts("https://example.com/new", FakeWeb({"https://example.com/new": ARTICLE}))

    assert facts["status"] == "ok"
    assert facts["title"] == "A & B"
    assert facts["description"] == 'It "works".'
    assert facts["excerpt"].startswith("word word")
    assert "menu" not in facts["excerpt"]
    assert facts["duration"] == "1m read"


def test_fetch_errors_are_reported_not_swallowed() -> None:
    facts = news.source_facts("https://example.com/down", FakeWeb({}))

    assert facts["status"] == "fetch_error"
    assert facts["error"] == "OSError: no route to https://example.com/down"


def test_youtube_facts_use_oembed_and_watch_page() -> None:
    url = "https://www.youtube.com/watch?v=abc"
    web = FakeWeb(
        {
            "https://www.youtube.com/oembed?url=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3Dabc&format=json": json.dumps(
                {"title": "Talk", "author_name": "Speaker"}
            ),
            url: '"lengthSeconds":"3720","shortDescription":"Line one\\nLine two"',
        }
    )

    facts = news.source_facts(url, web)

    assert (facts["title"], facts["description"], facts["duration"]) == ("Talk", "Line one Line two", "1h 2m")


def test_github_facts_combine_api_license_topics_and_readme() -> None:
    web = FakeWeb(
        {
            "https://api.github.com/repos/org/tool": json.dumps(
                {"full_name": "org/tool", "description": "A tool.", "license": {"spdx_id": "MIT"}, "topics": ["ai"]}
            ),
            "https://raw.githubusercontent.com/org/tool/HEAD/README.md": "# Tool\n```sh\nsecret\n```\n[Docs](x) ![logo](y)",
        }
    )

    facts = news.source_facts("https://github.com/org/tool", web)

    assert facts["title"] == "org/tool"
    assert facts["description"] == "A tool."
    assert facts["excerpt"] == "License: MIT. Topics: ai. # Tool Docs"


def test_github_owner_pages_fall_back_to_page_facts() -> None:
    web = FakeWeb({"https://github.com/org": ARTICLE})

    assert news.source_facts("https://github.com/org", web)["title"] == "A & B"


def test_arxiv_and_x_facts() -> None:
    arxiv = FakeWeb(
        {
            "https://export.arxiv.org/api/query?id_list=2601.00001": (
                '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Paper</title>'
                "<summary> Finds  things. </summary></entry></feed>"
            )
        }
    )
    post = FakeWeb(
        {
            "https://publish.twitter.com/oembed?url=https%3A%2F%2Fx.com%2Fa%2Fstatus%2F1": json.dumps(
                {"author_name": "A", "html": "<p>Shipped <a>v2</a></p>"}
            )
        }
    )

    paper = news.source_facts("https://arxiv.org/abs/2601.00001", arxiv)
    tweet = news.source_facts("https://x.com/a/status/1", post)

    assert (paper["title"], paper["description"]) == ("Paper", "Finds things.")
    assert (tweet["title"], tweet["description"]) == ("A on X", "Shipped v2")


def test_empty_arxiv_feed_is_a_fetch_error() -> None:
    web = FakeWeb({"https://export.arxiv.org/api/query?id_list=0": '<feed xmlns="http://www.w3.org/2005/Atom"/>'})

    assert news.source_facts("https://arxiv.org/abs/0", web)["status"] == "fetch_error"


def test_fetch_text_refuses_plain_http() -> None:
    with pytest.raises(ValueError, match="refusing non-HTTPS URL"):
        news.fetch_text("http://example.com/")


def test_main_prints_json_and_names_invalid_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    write_edition(tmp_path / "content" / "news", "2026-11-02", "https://example.com/old")

    assert news.main(["prepare", "--date", "2026-11-03", "https://example.com/old"]) == 0
    assert json.loads(capsys.readouterr().out) == [
        {"status": "duplicate", "url": "https://example.com/old", "edition": "2026-11-02"}
    ]

    (tmp_path / "content" / "news" / "2026-11-04.txt").write_text("broken", encoding="utf-8")
    assert news.main(["prepare", "https://example.com/new"]) == 1
    assert "2026-11-04:1: expected" in capsys.readouterr().err
