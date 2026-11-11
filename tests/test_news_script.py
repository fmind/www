"""The news preparation script, with every network read replaced by a fake."""

import base64
import http.client
import io
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from collections.abc import Mapping
from datetime import date
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
    lines = (f"- [Title {index}]({url}): About it." for index, url in enumerate(urls[:3]))
    (directory / f"{slug}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return directory


def test_prepare_skips_published_repeated_and_invalid_links(tmp_path: Path) -> None:
    directory = write_edition(tmp_path / "news", "2026-11-02", "https://example.com/old")
    write_edition(directory, "2026-11-03", "https://example.com/today")
    web = FakeWeb({"https://example.com/new": ARTICLE})

    results = news.prepare(
        [
            "https://example.com/old/?utm_source=mail",
            "https://example.com/new?fbclid=1",
            "https://example.com/new",
            "https://example.com/today",
            "ftp://example.com/file",
        ],
        directory,
        web,
    )

    by_status = [(result["status"], result["url"]) for result in results]
    # A link already in the edition being extended is a duplicate too.
    assert by_status == [
        ("duplicate", "https://example.com/old"),
        ("duplicate", "https://example.com/new"),
        ("duplicate", "https://example.com/today"),
        ("invalid", "ftp://example.com/file"),
        ("ok", "https://example.com/new"),
    ]
    assert results[0]["edition"] == "2026-11-02"
    assert results[1]["edition"] == "this batch"
    assert results[2]["edition"] == "2026-11-03"
    assert "unsupported or invalid URL" in results[3]["error"]
    assert web.requests == ["https://example.com/new"]


def test_prepare_resolves_shorteners_before_deduplicating(tmp_path: Path) -> None:
    directory = write_edition(tmp_path / "news", "2026-11-02", "https://example.com/old")
    web = FakeWeb({"https://bit.ly/abc": ("https://example.com/old?utm_campaign=x", "")})

    [result] = news.prepare(["https://bit.ly/abc"], directory, web)

    assert result == {"status": "duplicate", "url": "https://example.com/old", "edition": "2026-11-02"}


def test_prepare_reports_unreachable_shorteners_as_invalid(tmp_path: Path) -> None:
    [result] = news.prepare(["https://t.co/gone"], tmp_path, FakeWeb({}))

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


def test_youtube_requires_watch_page_description_instead_of_guessing_from_author() -> None:
    url = "https://www.youtube.com/watch?v=abc"
    oembed = "https://www.youtube.com/oembed?url=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3Dabc&format=json"
    meta = json.dumps({"title": "Talk", "author_name": "Speaker"})

    failed_watch = news.source_facts(url, FakeWeb({oembed: meta}))
    empty_watch = news.source_facts(url, FakeWeb({oembed: meta, url: '"lengthSeconds":"120"'}))

    assert (failed_watch["status"], failed_watch["title"], failed_watch["description"]) == ("fetch_error", "Talk", "")
    assert failed_watch["error"] == f"watch page: OSError: no route to {url}"
    assert (empty_watch["status"], empty_watch["title"], empty_watch["duration"]) == ("fetch_error", "Talk", "2m")


def test_github_facts_combine_api_license_topics_and_readme() -> None:
    web = FakeWeb(
        {
            "https://api.github.com/repos/org/tool": json.dumps(
                {"full_name": "org/tool", "description": "A tool.", "license": {"spdx_id": "MIT"}, "topics": ["ai"]}
            ),
            "https://api.github.com/repos/org/tool/readme": json.dumps(
                {"content": base64.b64encode(b"# Tool\n```sh\nsecret\n```\n[Docs](x) ![logo](y)").decode()}
            ),
        }
    )

    facts = news.source_facts("https://github.com/org/tool", web)

    assert facts["title"] == "org/tool"
    assert facts["description"] == "A tool."
    assert facts["excerpt"] == "License: MIT. Topics: ai. # Tool Docs"
    assert "error" not in facts


def test_github_keeps_repository_facts_without_a_readme_only_when_described() -> None:
    described = FakeWeb(
        {
            "https://api.github.com/repos/org/tool": json.dumps(
                {"full_name": "org/tool", "description": "A tool.", "license": {"spdx_id": "MIT"}}
            )
        }
    )
    undescribed = FakeWeb(
        {"https://api.github.com/repos/org/tool": json.dumps({"full_name": "org/tool", "license": {"spdx_id": "MIT"}})}
    )

    ok_facts = news.source_facts("https://github.com/org/tool", described)
    empty_facts = news.source_facts("https://github.com/org/tool", undescribed)

    assert (ok_facts["status"], ok_facts["title"], ok_facts["description"], ok_facts["excerpt"]) == (
        "ok",
        "org/tool",
        "A tool.",
        "License: MIT.",
    )
    assert ok_facts["error"] == "README: OSError: no route to https://api.github.com/repos/org/tool/readme"
    assert (empty_facts["status"], empty_facts["title"], empty_facts["excerpt"]) == ("fetch_error", "org/tool", "")


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/org",
        "https://github.com/blog/ship-it",
        "https://github.com/org/tool/releases/tag/v1.0",
        "https://github.com/org/tool",
    ],
)
def test_github_non_repo_paths_and_api_outages_fall_back_to_page_facts(url: str) -> None:
    web = FakeWeb({url: ARTICLE})

    facts = news.source_facts(url, web)

    assert (facts["status"], facts["title"]) == ("ok", "A & B")


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


@pytest.mark.parametrize(
    "payload",
    [
        '<!DOCTYPE feed [<!ENTITY x "boom">]><feed xmlns="http://www.w3.org/2005/Atom"/>',
        '<?xml version="1.0"?><!ENTITY x "boom"><feed xmlns="http://www.w3.org/2005/Atom"/>',
    ],
)
def test_arxiv_rejects_xml_dtd_and_entity_declarations(payload: str) -> None:
    web = FakeWeb({"https://export.arxiv.org/api/query?id_list=0": payload})
    facts = news.source_facts("https://arxiv.org/abs/0", web)

    assert facts["status"] == "fetch_error"
    assert "disallowed XML declarations" in facts["error"]


@pytest.mark.parametrize("address", ["127.0.0.1", "::1", "169.254.169.254", "100.64.0.1", "10.0.0.5"])
def test_public_https_connection_rejects_non_global_addresses(monkeypatch: pytest.MonkeyPatch, address: str) -> None:
    family = news.socket.AF_INET6 if ":" in address else news.socket.AF_INET
    sockaddr = (address, 443, 0, 0) if ":" in address else (address, 443)
    monkeypatch.setattr(
        news.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(family, news.socket.SOCK_STREAM, 6, "", sockaddr)],
    )
    connection = news.PublicHTTPSConnection("rebind.example", 443, timeout=2.0)

    with pytest.raises(ValueError, match="refusing non-global address"):
        connection.connect()


def test_public_https_connection_binds_verified_global_socket_and_sni(monkeypatch: pytest.MonkeyPatch) -> None:
    connected: list[tuple[object, ...]] = []
    wrapped: list[tuple[object, str]] = []

    class FakeSocket:
        def __init__(self, *_args: object) -> None:
            self.timeout: float | None = None

        def settimeout(self, value: float) -> None:
            self.timeout = value

        def connect(self, sockaddr: tuple[object, ...]) -> None:
            connected.append(sockaddr)

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        news.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(news.socket.AF_INET, news.socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )
    monkeypatch.setattr(news.socket, "socket", FakeSocket)
    monkeypatch.setattr(
        news._TLS_CONTEXT,  # noqa: SLF001
        "wrap_socket",
        lambda raw, *, server_hostname: wrapped.append((raw, server_hostname)) or "tls-socket",
    )
    connection = news.PublicHTTPSConnection("example.com", 443, timeout=3.0)
    connection.connect()

    assert connected == [("93.184.216.34", 443)]
    assert len(wrapped) == 1
    assert wrapped[0][1] == "example.com"
    assert connection.sock == "tls-socket"


def test_fetch_text_refuses_plain_http() -> None:
    with pytest.raises(ValueError, match="refusing non-HTTPS URL"):
        news.fetch_text("http://example.com/")


@pytest.mark.parametrize("target", ["http://127.0.0.1:8080/admin", "ftp://example.com/file"])
def test_redirects_off_https_are_refused_before_the_next_request(target: str) -> None:
    handler = news.HttpsOnlyRedirect()
    request = urllib.request.Request("https://example.com/start")
    response = io.BytesIO(b"moved")

    with pytest.raises(ValueError, match="redirected to non-HTTPS"):
        handler.redirect_request(request, response, 302, "Found", http.client.HTTPMessage(), target)
    assert response.closed
    followed = handler.redirect_request(
        request, io.BytesIO(), 302, "Found", http.client.HTTPMessage(), "https://example.com/next"
    )
    assert followed is not None
    assert followed.full_url == "https://example.com/next"


class FakeResponse:
    """Stand in for an HTTPResponse that streams chunks or fails mid-body."""

    def __init__(self, *chunks: bytes | Exception) -> None:
        self.chunks = list(chunks)

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        pass

    def read1(self, size: int) -> bytes:
        chunk = self.chunks.pop(0) if self.chunks else b""
        if isinstance(chunk, Exception):
            raise chunk
        return chunk[:size]

    def geturl(self) -> str:
        return "https://example.com/final"


def test_fetch_text_reads_a_bounded_body_through_the_https_only_opener(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(news.OPENER, "open", lambda *_args, **_kwargs: FakeResponse(b"abc", b"def", b"ghi"))

    assert news.fetch_text("https://example.com/", max_bytes=5) == ("https://example.com/final", "abcde")


def test_fetch_text_enforces_a_total_deadline_on_trickling_bodies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(news, "DEADLINE_SECONDS", -1.0)  # already past after the first chunk
    monkeypatch.setattr(news.OPENER, "open", lambda *_args, **_kwargs: FakeResponse(b"a", b"b", b"c"))

    with pytest.raises(TimeoutError, match="read exceeded"):
        news.fetch_text("https://example.com/")


@pytest.mark.parametrize(
    "failure",
    [http.client.IncompleteRead(b"partial"), http.client.BadStatusLine("HTTP/9"), http.client.LineTooLong("header")],
    ids=("incomplete", "status-line", "line-too-long"),
)
def test_malformed_http_responses_are_fetch_errors(
    monkeypatch: pytest.MonkeyPatch, failure: http.client.HTTPException
) -> None:
    monkeypatch.setattr(news.OPENER, "open", lambda *_args, **_kwargs: FakeResponse(b"<p>", failure))

    facts = news.source_facts("https://example.com/broken")

    assert facts["status"] == "fetch_error"
    assert facts["error"].startswith(f"OSError: https://example.com/broken: {type(failure).__name__}")


@pytest.mark.parametrize(
    ("url", "api"),
    [
        ("https://github.com/org/tool", "https://api.github.com/repos/org/tool"),
        (
            "https://www.youtube.com/watch?v=abc",
            "https://www.youtube.com/oembed?url=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3Dabc&format=json",
        ),
        ("https://x.com/a/status/1", "https://publish.twitter.com/oembed?url=https%3A%2F%2Fx.com%2Fa%2Fstatus%2F1"),
    ],
    ids=("github", "youtube", "x"),
)
@pytest.mark.parametrize("body", ["[]", "null"])
def test_non_object_api_bodies_are_fetch_errors(url: str, api: str, body: str) -> None:
    facts = news.source_facts(url, FakeWeb({api: body}))

    assert facts["status"] == "fetch_error"
    assert facts["error"].startswith("ValueError: expected a JSON object")


@pytest.mark.parametrize(
    ("record", "kind"),
    [
        ({"description": 5}, "TypeError"),
        ({"full_name": 5, "description": "A tool."}, "TypeError"),
        ({"description": "A tool.", "license": "MIT"}, "AttributeError"),
        ({"description": "A tool.", "topics": {"a": 1}}, "KeyError"),
    ],
    ids=("numeric-description", "numeric-full-name", "text-license", "dict-topics"),
)
def test_one_api_record_with_a_wrongly_typed_field_does_not_abort_the_batch(
    tmp_path: Path, record: dict[str, object], kind: str
) -> None:
    bad = "https://github.com/org/tool"
    web = FakeWeb({"https://api.github.com/repos/org/tool": json.dumps(record), "https://example.com/new": ARTICLE})

    broken, good = news.prepare([bad, "https://example.com/new"], tmp_path, web)

    assert (good["status"], good["title"]) == ("ok", "A & B")
    assert (broken["status"], broken["url"]) == ("fetch_error", bad)
    assert broken["error"].startswith(f"{kind}: {bad} returned a field of an unexpected type: ")


def test_page_keeps_custom_elements_that_share_a_boilerplate_prefix() -> None:
    page = (
        "<main-content><p>outside</p></main-content><article>"
        "<p>Hello <nav-menu>menu</nav-menu> world</p><formatted-text>kept</formatted-text>"
        "<nav class='site'>dropped</nav ><p>more</p></article><nav>z</nav>"
    )

    facts = news.source_facts("https://example.com/a", FakeWeb({"https://example.com/a": page}))

    assert facts["excerpt"] == "Hello menu world more"


def test_page_searches_each_unclosed_tag_for_a_closer_only_once(monkeypatch: pytest.MonkeyPatch) -> None:
    # Each unclosed opener used to rescan to the end of the page: about 20 minutes for 70,000 repeats.
    # Counting the closer searches checks that bound without a wall clock.
    page = "<svg><main><nav>" * 1_000 + "<article><p>body text</p></article>"
    compile_pattern = re.compile
    closers: list[str] = []

    def recording_compile(pattern: str, flags: int = 0) -> re.Pattern[str]:
        if pattern.startswith("</"):
            closers.append(pattern)
        return compile_pattern(pattern, flags)

    monkeypatch.setattr(news.re, "compile", recording_compile)

    facts = news.source_facts("https://example.com/a", FakeWeb({"https://example.com/a": page}))

    assert facts["excerpt"] == "body text"
    assert closers == [r"</svg\s*>", r"</nav\s*>", r"</main\s*>", r"</article\s*>"]


def test_main_prints_json_and_names_invalid_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    write_edition(tmp_path / "content" / "news", "2026-11-02", "https://example.com/old")

    assert news.main(["prepare", "https://example.com/old"]) == 0
    assert json.loads(capsys.readouterr().out) == [
        {"status": "duplicate", "url": "https://example.com/old", "edition": "2026-11-02"}
    ]

    (tmp_path / "content" / "news" / "2026-11-04.md").write_text("broken\n", encoding="utf-8")
    assert news.main(["prepare", "https://example.com/new"]) == 1
    assert "2026-11-04:1: expected" in capsys.readouterr().err


# Draft and publish run against a local bare remote, with a fake writer and fake web.
TODAY = date(2026, 11, 7)
NEW_URL = "https://example.com/new"


def run_git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout  # noqa: S603, S607


class FakeWriter:
    """Return queued answers in turn and record every prompt."""

    def __init__(self, *answers: list[dict[str, str]] | Mapping[str, object]) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> Mapping[str, object]:
        self.prompts.append(prompt)
        answer = self.answers.pop(0)
        return answer if isinstance(answer, Mapping) else {"items": answer}


def line(url: str, description: str = "Ships a tested change.") -> dict[str, str]:
    return {"url": url, "title": f"Title of {url.rsplit('/', 1)[-1]}", "description": description}


@pytest.fixture(scope="module")
def _site_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("news_site")
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(
        {
            "GIT_CONFIG_GLOBAL": str(root / "gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.test",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.test",
        }
    )
    for cwd, args in (
        (root, ("init", "--quiet", "--bare", "--initial-branch=main", "remote.git")),
        (root, ("clone", "--quiet", str(root / "remote.git"), "repo")),
    ):
        subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True)  # noqa: S603, S607
    repo = root / "repo"
    write_edition(repo / "content" / "news", "2026-11-06", "https://example.com/old")
    skill = repo / news.SKILL
    skill.parent.mkdir(parents=True)
    skill.write_text(news.SKILL.read_text(encoding="utf-8"), encoding="utf-8")
    for args in (
        ("add", "."),
        ("commit", "--quiet", "-m", "init"),
        ("push", "--quiet", "origin", "HEAD:main"),
    ):
        subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True, text=True)  # noqa: S603, S607
    return root


@pytest.fixture
def site(tmp_path: Path, _site_template: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A checkout whose origin/main holds one older edition and the real news skill."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for key in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{key}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{key}_EMAIL", "test@example.test")
    shutil.copytree(_site_template / "remote.git", tmp_path / "remote.git")
    repo = shutil.copytree(_site_template / "repo", tmp_path / "repo")
    config = repo / ".git" / "config"
    config.write_text(
        config.read_text(encoding="utf-8").replace(str(_site_template / "remote.git"), str(tmp_path / "remote.git")),
        encoding="utf-8",
    )
    return repo


def draft(site: Path, writer: FakeWriter, *urls: str, feedback: str = "") -> str:
    web = FakeWeb({NEW_URL: ARTICLE, "https://example.com/second": ARTICLE})
    return news.draft(
        urls, day=TODAY, repo=site, drafts=site / "tmp" / "drafts", fetch=web, writer=writer, feedback=feedback
    )


def draft_id(preview: str) -> str:
    match = re.search(r"Draft ([0-9a-f]{12}) ", preview)
    assert match, preview
    return match[1]


def test_draft_and_publish_push_only_the_edition_on_top_of_origin(site: Path) -> None:
    writer = FakeWriter([line("https://example.com/second"), line(NEW_URL)])

    preview = draft(
        site, writer, NEW_URL, "https://example.com/old", "https://docs.google.com/d/1", "https://example.com/second"
    )

    assert "2 links (2 new)" in preview
    assert "1. Title of second (example.com): Ships a tested change." in preview
    assert "https://example.com/old: already in 2026-11-06" in preview
    assert "https://docs.google.com/d/1: link-shared document" in preview
    assert "untrusted data" in writer.prompts[0]
    assert "NVIDIA/auto-ontology" in writer.prompts[0]  # the format rules come from the news skill
    assert not (site / "content" / "news" / "2026-11-07.md").exists()
    # Local work that is not on origin/main must never ride along with the edition.
    (site / "README.md").write_text("local change", encoding="utf-8")
    run_git(site, "add", "README.md")
    run_git(site, "commit", "--quiet", "-m", "local work")

    summary = news.publish(draft_id(preview), repo=site, drafts=site / "tmp" / "drafts")

    remote = site.parent / "remote.git"
    assert run_git(remote, "log", "-1", "--format=%s", "main") == "feat(news): add 2026-11-07 edition\n"
    assert run_git(remote, "diff-tree", "--no-commit-id", "--name-only", "-r", "main").split() == [
        "content/news/2026-11-07.md"
    ]
    assert "README.md" not in run_git(remote, "ls-tree", "--name-only", "main")
    published = run_git(remote, "show", "main:content/news/2026-11-07.md")
    assert published.startswith("- [Title of second](https://example.com/second): ")
    assert "Published the 2026-11-07 edition (2 links)" in summary
    assert "https://www.fmind.dev/news/2026-11-07/" in summary
    with pytest.raises(news.NewsError, match="already published"):
        news.publish(draft_id(preview), repo=site, drafts=site / "tmp" / "drafts")


def test_draft_keeps_published_lines_and_retries_a_rejected_answer(site: Path) -> None:
    write_edition(site / "content" / "news", "2026-11-07", "https://example.com/today")
    run_git(site, "add", ".")
    run_git(site, "commit", "--quiet", "-m", "today")
    run_git(site, "push", "--quiet", "origin", "HEAD:main")
    too_long = " ".join(["word"] * 31)
    writer = FakeWriter(
        [line(NEW_URL, too_long), line("https://example.com/today")],
        [line(NEW_URL), line("https://example.com/today", "Rewritten by the model.")],
    )

    preview = draft(site, writer, NEW_URL, feedback="Put the new link first.")

    assert "has 31 words" in writer.prompts[1]
    assert "Put the new link first." in writer.prompts[0]
    assert "2 links (1 new)" in preview
    assert "2. Title 0 (example.com): About it." in preview  # the published line stays verbatim

    summary = news.publish(draft_id(preview), repo=site, drafts=site / "tmp" / "drafts")

    assert "(2 links)" in summary
    remote = site.parent / "remote.git"
    subject = run_git(remote, "log", "-1", "--format=%s", "main")
    assert subject == "feat(news): add links to the 2026-11-07 edition\n"
    # Added links move the feed entry so readers fetch the edition again the same day.
    edition = news.parse_edition("2026-11-07", run_git(remote, "show", "main:content/news/2026-11-07.md"))
    assert edition.modified() > edition.published()


def test_publish_refuses_an_edition_changed_on_main_since_the_draft(site: Path, tmp_path: Path) -> None:
    preview = draft(site, FakeWriter([line(NEW_URL)]), NEW_URL)
    run_git(tmp_path, "clone", "--quiet", str(tmp_path / "remote.git"), "other")
    write_edition(tmp_path / "other" / "content" / "news", "2026-11-07", "https://example.com/elsewhere")
    run_git(tmp_path / "other", "add", ".")
    run_git(tmp_path / "other", "commit", "--quiet", "-m", "concurrent edition")
    run_git(tmp_path / "other", "push", "--quiet", "origin", "HEAD:main")

    with pytest.raises(news.NewsError, match="changed on main since draft"):
        news.publish(draft_id(preview), repo=site, drafts=site / "tmp" / "drafts")


def test_draft_refuses_links_with_nothing_new_and_bad_writer_answers(site: Path) -> None:
    with pytest.raises(news.NewsError, match=r"(?s)no new link.*already in 2026-11-06"):
        draft(site, FakeWriter(), "https://example.com/old")
    with pytest.raises(news.NewsError, match="failed validation twice: the answer leaves out"):
        draft(site, FakeWriter([], []), NEW_URL)
    with pytest.raises(news.NewsError, match=r"(?s)no new link.*insufficient facts \(sponsor links only\)"):
        draft(
            site, FakeWriter({"items": [], "unverified": [{"url": NEW_URL, "reason": "sponsor links only"}]}), NEW_URL
        )
    preview = draft(
        site,
        FakeWriter(
            {
                "items": [line(NEW_URL)],
                "unverified": [{"url": "https://example.com/second", "reason": "sponsor links only"}],
            }
        ),
        NEW_URL,
        "https://example.com/second",
    )
    assert "1 links (1 new)" in preview
    assert "https://example.com/second: insufficient facts (sponsor links only)" in preview
    with pytest.raises(news.NewsError, match="not one of the listed links"):
        news.ordered_items({"items": [line("https://example.com/other")]}, (), [NEW_URL])
    with pytest.raises(news.NewsError, match="`unverified` must be a list"):
        news.ordered_items({"items": [line(NEW_URL)], "unverified": "bad"}, (), [NEW_URL])
    with pytest.raises(news.NewsError, match="each unverified entry needs string url and reason fields"):
        news.ordered_items({"items": [line(NEW_URL)], "unverified": [{}]}, (), [NEW_URL])
    with pytest.raises(news.NewsError, match="cannot be held back as unverified"):
        news.ordered_items({"items": [], "unverified": [{"url": NEW_URL, "reason": "   "}]}, (), [NEW_URL])
    with pytest.raises(news.NewsError, match="not a draft ID"):
        news.publish("../../etc", repo=site)


@pytest.mark.parametrize(
    "title",
    [
        # Each title closes the link early and re-opens it, so the line would re-parse to another URL.
        "Real](https://evil.example/x): Releases a tool. [Real",
        # A newline would add a second link line that nobody submitted.
        "A](https://evil.example/): Releases X.\n- [B",
    ],
)
def test_draft_rejects_titles_that_reparse_into_other_links(site: Path, title: str) -> None:
    answer = [{**line(NEW_URL), "title": title}]

    with pytest.raises(news.NewsError, match="failed validation twice"):
        draft(site, FakeWriter(answer, answer), NEW_URL)

    assert not (site / "tmp" / "drafts").exists()


def test_publish_refuses_an_incomplete_draft_record(site: Path) -> None:
    drafts = site / "tmp" / "drafts"
    drafts.mkdir(parents=True)
    for bad in (
        '{"slug": "2026-11-07"}',
        '{"slug": "../evil", "markdown": "- [A](https://example.com/a): B.\\n", "base": ""}',
        '{"slug": "2026-11-07", "markdown": 123, "base": ""}',
    ):
        (drafts / "0123456789ab.json").write_text(bad, encoding="utf-8")
        with pytest.raises(news.NewsError, match="unreadable or incomplete"):
            news.publish("0123456789ab", repo=site, drafts=drafts)


def test_agy_writer_denies_every_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        output = {"structured_output": {"items": []}} if len(calls) == 1 else {"response": "no schema"}
        return subprocess.CompletedProcess(command, 0, json.dumps(output), "")

    monkeypatch.setattr(news.subprocess, "run", fake_run)

    assert news.agy_writer("prompt") == {"items": []}
    command = calls[0]
    assert "--dangerously-skip-permissions" not in command
    denied = json.loads(command[command.index("--settings") + 1])["permissions"]["deny"]
    assert set(denied) == {
        f"{kind}(*)" for kind in ("read_file", "write_file", "command", "read_url", "execute_url", "mcp")
    }
    assert command[-1] == "-p=prompt"
    with pytest.raises(news.NewsError, match="no structured output"):
        news.agy_writer("prompt")


def test_publish_tests_never_touch_the_repository_running_them(tmp_path: Path) -> None:
    """A hook exports GIT_DIR; the news fixtures must still commit and push only inside their own temp repos."""
    outer = tmp_path / "outer"
    run_git(tmp_path, "init", "--quiet", "--bare", "--initial-branch=main", "outer.git")
    run_git(tmp_path, "clone", "--quiet", str(tmp_path / "outer.git"), "outer")
    run_git(
        outer, "-c", "user.name=T", "-c", "user.email=t@example.test", "commit", "--quiet", "--allow-empty", "-m", "x"
    )
    run_git(outer, "push", "--quiet", "origin", "HEAD:main")
    before = run_git(tmp_path / "outer.git", "rev-parse", "main")
    environment = {**os.environ, "GIT_DIR": str(outer / ".git"), "GIT_WORK_TREE": str(outer)}

    subprocess.run(  # noqa: S603 - fixed interpreter and test selection
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--no-cov",
            "-o",
            "addopts=",
            f"{Path(__file__)}::test_draft_and_publish_push_only_the_edition_on_top_of_origin",
        ],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert run_git(tmp_path / "outer.git", "rev-parse", "main") == before
    assert run_git(outer, "log", "--format=%s") == "x\n"


def test_git_never_prompts_and_names_a_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The alias prints what Git's children see, and `cat` returns at once on the closed stdin.
    assert news.git(tmp_path, "-c", "alias.probe=!printenv GIT_TERMINAL_PROMPT && cat", "probe") == "0\n"

    def hang(command: list[str], **options: float) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, options["timeout"])

    monkeypatch.setattr(news.subprocess, "run", hang)

    with pytest.raises(news.NewsError, match=r"git fetch timed out after 120 s; check the network") as failure:
        news.fetch_main(tmp_path)
    assert isinstance(failure.value.__cause__, subprocess.TimeoutExpired)
    with pytest.raises(news.NewsError, match=r"git archive timed out after 120 s"):
        news.snapshot(tmp_path, "HEAD", tmp_path)
