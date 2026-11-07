"""The news preparation script, with every network read replaced by a fake."""

import base64
import json
import re
import subprocess
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
    (directory / f"{slug}.md").write_text("## Highlights\n\n" + "\n".join(lines), encoding="utf-8")
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


def test_youtube_keeps_oembed_facts_when_the_watch_page_fails() -> None:
    url = "https://www.youtube.com/watch?v=abc"
    oembed = "https://www.youtube.com/oembed?url=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3Dabc&format=json"
    web = FakeWeb({oembed: json.dumps({"title": "Talk", "author_name": "Speaker"})})

    facts = news.source_facts(url, web)

    assert (facts["status"], facts["title"], facts["description"]) == ("ok", "Talk", "Video by Speaker")
    assert facts["error"] == f"watch page: OSError: no route to {url}"


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


def test_github_keeps_repository_facts_without_a_readme() -> None:
    web = FakeWeb(
        {"https://api.github.com/repos/org/tool": json.dumps({"full_name": "org/tool", "license": {"spdx_id": "MIT"}})}
    )

    facts = news.source_facts("https://github.com/org/tool", web)

    assert (facts["status"], facts["title"], facts["excerpt"]) == ("ok", "org/tool", "License: MIT.")
    assert facts["error"] == "README: OSError: no route to https://api.github.com/repos/org/tool/readme"


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

    assert news.main(["prepare", "https://example.com/old"]) == 0
    assert json.loads(capsys.readouterr().out) == [
        {"status": "duplicate", "url": "https://example.com/old", "edition": "2026-11-02"}
    ]

    (tmp_path / "content" / "news" / "2026-11-04.md").write_text("## Highlights\nbroken", encoding="utf-8")
    assert news.main(["prepare", "https://example.com/new"]) == 1
    assert "2026-11-04:2: expected" in capsys.readouterr().err


# Draft and publish run against a local bare remote, with a fake writer and fake web.
TODAY = date(2026, 11, 7)
NEW_URL = "https://example.com/new"


def run_git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout  # noqa: S603, S607


class FakeWriter:
    """Return queued answers in turn and record every prompt."""

    def __init__(self, *answers: list[dict[str, str]]) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> Mapping[str, object]:
        self.prompts.append(prompt)
        return {"items": self.answers.pop(0)}


def line(url: str, description: str = "Ships a tested change.") -> dict[str, str]:
    return {"url": url, "title": f"Title of {url.rsplit('/', 1)[-1]}", "description": description}


@pytest.fixture
def site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A checkout whose origin/main holds one older edition and the real news skill."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for key in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{key}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{key}_EMAIL", "test@example.test")
    run_git(tmp_path, "init", "--quiet", "--bare", "--initial-branch=main", "remote.git")
    run_git(tmp_path, "clone", "--quiet", str(tmp_path / "remote.git"), "repo")
    repo = tmp_path / "repo"
    write_edition(repo / "content" / "news", "2026-11-06", "https://example.com/old")
    skill = repo / news.SKILL
    skill.parent.mkdir(parents=True)
    skill.write_text(news.SKILL.read_text(encoding="utf-8"), encoding="utf-8")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "--quiet", "-m", "init")
    run_git(repo, "push", "--quiet", "origin", "HEAD:main")
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
    assert "## Highlights" in writer.prompts[0]  # the format rules come from the news skill
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
    assert published.startswith("## Highlights\n\n- [Title of second](https://example.com/second): ")
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
    with pytest.raises(news.NewsError, match="not one of the listed links"):
        news.ordered_items({"items": [line("https://example.com/other")]}, (), [NEW_URL])
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
    (drafts / "0123456789ab.json").write_text('{"slug": "2026-11-07"}', encoding="utf-8")

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
