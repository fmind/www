"""Prepare pasted links for a news edition: clean URLs, skip published ones, and fetch source facts.

Usage: uv run --locked python -m scripts.news prepare [--date YYYY-MM-DD] URL...

Prints one JSON object per URL. `status` is `ok`, `duplicate` (already in an edition, named by
`edition`), `invalid`, or `fetch_error` (the source gave no title, description, or text, so an agent
must find the primary source before describing it). Descriptions are written only from these facts.
"""

import argparse
import html
import json
import re
import sys
import urllib.request
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.parse import quote, urlparse
from xml.etree import ElementTree

from www.news import NewsError, canonicalize_url, load_news

EXCERPT_LIMIT = 1500
MAX_BYTES = 1_200_000
TIMEOUT_SECONDS = 8.0
WORKERS = 8
SHORTENERS = frozenset({"t.co", "bit.ly", "tinyurl.com", "lnkd.in", "buff.ly"})
USER_AGENT = "Mozilla/5.0 (compatible; fmind-news; +https://www.fmind.dev/news/)"

type Fetch = Callable[[str], tuple[str, str]]


def fetch_text(url: str, max_bytes: int = MAX_BYTES) -> tuple[str, str]:
    """Return the final URL and decoded body of one bounded public HTTPS read."""
    if urlparse(url).scheme != "https":
        raise ValueError(f"refusing non-HTTPS URL {url!r}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})  # noqa: S310
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
        final_url = response.geturl() or url
        if urlparse(final_url).scheme != "https":
            raise ValueError(f"{url} redirected to non-HTTPS {final_url}")
        return final_url, response.read(max_bytes).decode("utf-8", errors="replace")


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _first(patterns: Sequence[str], text: str) -> str:
    for pattern in patterns:
        if match := re.search(pattern, text, re.IGNORECASE | re.DOTALL):
            value = _clean(next((group for group in match.groups() if group), ""))
            if value:
                return value
    return ""


def _meta(name: str) -> tuple[str, str]:
    attribute = "property" if name.startswith("og:") else "name"
    return (
        rf"<meta[^>]+{attribute}=[\"']{name}[\"'][^>]+content=(?:\"([^\"]+)\"|'([^']+)')",
        rf"<meta[^>]+content=(?:\"([^\"]+)\"|'([^']+)')[^>]+{attribute}=[\"']{name}[\"']",
    )


def _minutes(seconds: int) -> str:
    minutes = max(1, round(seconds / 60))
    hours, rest = divmod(minutes, 60)
    if not hours:
        return f"{minutes}m"
    return f"{hours}h {rest}m" if rest else f"{hours}h"


def _youtube(url: str, fetch: Fetch) -> dict[str, str]:
    _, oembed = fetch(f"https://www.youtube.com/oembed?url={quote(url, safe='')}&format=json")
    data = json.loads(oembed)
    author = _clean(data.get("author_name", ""))
    facts = {"title": _clean(data.get("title", "")), "description": f"Video by {author}" if author else ""}
    _, page = fetch(url)
    if seconds := re.search(r'"lengthSeconds":"(\d+)"', page):
        facts["duration"] = _minutes(int(seconds[1]))
    if short := re.search(r'"shortDescription":"((?:[^"\\]|\\.)*)"', page):
        text = _clean(json.loads(f'"{short[1]}"'))
        facts["description"] = text[:600] or facts["description"]
        facts["excerpt"] = text[:EXCERPT_LIMIT]
    return facts


def _x(url: str, fetch: Fetch) -> dict[str, str]:
    _, oembed = fetch(f"https://publish.twitter.com/oembed?url={quote(url, safe='')}")
    data = json.loads(oembed)
    author = _clean(data.get("author_name", ""))
    text = _clean(re.sub(r"<[^>]+>", " ", data.get("html", "")))
    return {"title": f"{author} on X" if author else "X post", "description": text[:600], "excerpt": text}


def _github(url: str, fetch: Fetch) -> dict[str, str]:
    parts = [part for part in urlparse(url).path.split("/") if part]
    if len(parts) < 2:
        return _page(url, fetch)
    owner, repo = parts[0], parts[1]
    _, body = fetch(f"https://api.github.com/repos/{quote(owner)}/{quote(repo)}")
    data = json.loads(body)
    facts = [
        f"License: {spdx}."
        for spdx in [(data.get("license") or {}).get("spdx_id")]
        if spdx not in (None, "NOASSERTION")
    ]
    if topics := data.get("topics"):
        facts.append(f"Topics: {', '.join(topics[:8])}.")
    _, readme = fetch(f"https://raw.githubusercontent.com/{quote(owner)}/{quote(repo)}/HEAD/README.md")
    readme = re.sub(r"```.*?```", " ", readme, flags=re.DOTALL)
    readme = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", readme)
    readme = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", readme)
    facts.append(_clean(re.sub(r"<[^>]+>", " ", readme)))
    return {
        "title": data.get("full_name") or f"{owner}/{repo}",
        "description": _clean(data.get("description") or ""),
        "excerpt": _clean(" ".join(facts)),
    }


def _arxiv(url: str, fetch: Fetch) -> dict[str, str]:
    paper = urlparse(url).path.split("/abs/")[-1].strip("/")
    _, body = fetch(f"https://export.arxiv.org/api/query?id_list={quote(paper)}")
    namespace = {"a": "http://www.w3.org/2005/Atom"}
    entry = ElementTree.fromstring(body).find("a:entry", namespace)  # noqa: S314 - arXiv's own API, no DTD use
    if entry is None:
        return {}
    summary = _clean(entry.findtext("a:summary", default="", namespaces=namespace))
    return {
        "title": _clean(entry.findtext("a:title", default="", namespaces=namespace)),
        "description": summary[:600],
        "excerpt": summary,
    }


def _page(url: str, fetch: Fetch) -> dict[str, str]:
    _, page = fetch(url)
    title = _first((*_meta("og:title"), r"<title[^>]*>(.*?)</title>"), page)
    description = _first((*_meta("og:description"), *_meta("description")), page)
    body = re.sub(
        r"<(script|style|noscript|nav|header|footer|aside|svg|form)[^>]*>.*?</\1>",
        " ",
        page,
        flags=re.IGNORECASE | re.DOTALL,
    )
    scope = (
        match[2]
        if (match := re.search(r"<(article|main)\b[^>]*>(.*?)</\1>", body, re.IGNORECASE | re.DOTALL))
        else body
    )
    paragraphs = " ".join(re.findall(r"<p\b[^>]*>(.*?)</p>", scope, re.IGNORECASE | re.DOTALL))
    text = _clean(re.sub(r"<[^>]+>", " ", paragraphs or scope))
    words = len(text.split())
    facts = {"title": title, "description": description, "excerpt": text}
    if words >= 80:
        facts["duration"] = f"{max(1, round(words / 220))}m read"
    return facts


def source_facts(url: str, fetch: Fetch = fetch_text) -> dict[str, str]:
    """Collect the title, description, text excerpt, and duration that ground an edition line."""
    host = urlparse(url).netloc
    reader = _page
    if host == "www.youtube.com":
        reader = _youtube
    elif host == "x.com":
        reader = _x
    elif host == "github.com":
        reader = _github
    elif host == "arxiv.org" and "/abs/" in url:
        reader = _arxiv
    result = {"url": url, "title": "", "description": "", "excerpt": "", "duration": ""}
    try:
        result.update(reader(url, fetch))
    except (OSError, ValueError, ElementTree.ParseError) as error:
        result["error"] = f"{type(error).__name__}: {error}"
    result["excerpt"] = result["excerpt"][:EXCERPT_LIMIT]
    has_facts = any(result[key] for key in ("title", "description", "excerpt"))
    return {"status": "ok" if has_facts else "fetch_error", **result}


def prepare(
    urls: Sequence[str], edition: str, news_dir: Path = Path("content/news"), fetch: Fetch = fetch_text
) -> list[dict[str, str]]:
    """Canonicalize each URL, skip those already published or repeated, and fetch facts for the rest."""
    published = {
        canonicalize_url(item.url): other.slug
        for other in load_news(news_dir)
        if other.slug != edition
        for item in other.items
    }
    results: list[dict[str, str]] = []
    pending: list[str] = []
    for raw in urls:
        try:
            url = canonicalize_url(raw)
            if urlparse(url).netloc in SHORTENERS:
                url = canonicalize_url(fetch(url)[0])
        except (OSError, ValueError) as error:
            results.append({"status": "invalid", "url": raw, "error": f"{type(error).__name__}: {error}"})
            continue
        if url in published:
            results.append({"status": "duplicate", "url": url, "edition": published[url]})
        elif url in pending:
            results.append({"status": "duplicate", "url": url, "edition": "this batch"})
        else:
            pending.append(url)
    if pending:
        with ThreadPoolExecutor(max_workers=min(WORKERS, len(pending))) as pool:
            results.extend(pool.map(lambda url: source_facts(url, fetch), pending))
    return results


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("prepare", help="clean, deduplicate, and fetch facts for pasted URLs")
    command.add_argument("--date", default=date.today().isoformat(), help="edition slug (default: today)")
    command.add_argument("urls", nargs="+", metavar="URL")
    arguments = parser.parse_args(argv)
    try:
        results = prepare(arguments.urls, arguments.date)
    except NewsError as error:
        print(f"error: {error}; fix content/news before preparing new links", file=sys.stderr)  # noqa: T201
        return 1
    print(json.dumps(results, indent=2, ensure_ascii=False))  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
